import logging
import os
from typing import Optional
from openai import OpenAI as _OpenAI

logger = logging.getLogger(__name__)

_embeddings_client = None


def _get_embeddings_client():
    global _embeddings_client
    if _embeddings_client is None:
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
        _embeddings_client = _OpenAI(api_key=api_key)
    return _embeddings_client

CLARIFY_SYSTEM_PROMPT = (
    "You are a professional translator and transcriber. "
    "You will receive a conversation that may be in Hindi, Hinglish (mixed Hindi-English), "
    "casual English, or a mix of languages. "
    "Your task is to rewrite the entire conversation in clear, natural English. "
    "Rules:\n"
    "- Do NOT summarize. Preserve every point, every detail.\n"
    "- Keep the conversational flow and speaker names.\n"
    "- Translate casual/slang terms to their proper English meaning.\n"
    "- If audio or video was transcribed, include that content as part of the conversation.\n"
    "- Output format: 'SpeakerName: <their message>' on each line.\n"
    "- Do not add commentary, headers, or extra text."
)


class MessageProcessor:
    def __init__(self, openai_client, audio_processor=None, teams_client=None):
        self.openai = openai_client
        self.audio_processor = audio_processor
        self.teams_client = teams_client

    def _collect_meeting_content(self, thread: dict) -> str:
        parts = []
        for msg in thread.get("messages", []):
            event_detail = msg.get("event_detail", {})
            created_at = msg.get("created_at", "")
            sender = msg.get("sender", "Unknown")

            timestamp = ""
            if created_at:
                try:
                    from datetime import datetime as _dt
                    dt = _dt.fromisoformat(created_at.replace("Z", "+00:00"))
                    timestamp = dt.strftime("[%Y-%m-%d %H:%M]")
                except Exception:
                    timestamp = f"[{created_at[:16]}]"

            event_type = event_detail.get("@odata.type", "")
            recording_name = event_detail.get("callRecordingDisplayName", "")
            recording_status = event_detail.get("callRecordingStatus", "")
            initiator_user = (event_detail.get("initiator") or {}).get("user", {}) or {}
            initiator = initiator_user.get("displayName", sender)
            join_url = event_detail.get("joinWebUrl", "")

            if "callRecording" in event_type:
                header = f"{timestamp} Meeting Recording: {recording_name or 'Unknown'}"
                if recording_status:
                    header += f" (Status: {recording_status})"
                if initiator:
                    header += f" — Recorded by: {initiator}"
            elif "callTranscription" in event_type:
                header = f"{timestamp} Meeting Transcription Event"
                if initiator:
                    header += f" — Initiated by: {initiator}"
            else:
                header = f"{timestamp} Meeting Event"
                if sender and sender != "Unknown":
                    header += f" — {sender}"

            if join_url:
                header += f"\nMeeting URL: {join_url}"

            parts.append(header)

            attachments = msg.get("attachments", [])
            for att in attachments:
                att_name = att.get("name") or att.get("content_type", "attachment")
                content_url = att.get("content_url") or ""
                if self.audio_processor and self.teams_client:
                    def _download_media(att=att, content_url=content_url, msg=msg):
                        if content_url:
                            return self.teams_client.download_attachment_content(content_url)
                        card_content = att.get("card_content") or ""
                        if card_content:
                            try:
                                import json as _json
                                card = _json.loads(card_content)
                                media_url = card.get("media", [{}])[0].get("url", "")
                                if media_url:
                                    logger.info("[Processor] Downloading audio card via AMS URL from card_content")
                                    return self.teams_client.download_attachment_content(media_url)
                            except Exception as _e:
                                logger.warning(f"[Processor] Failed to parse card_content for media URL: {_e}")
                        att_id = att.get("id", "")
                        source_base_url = msg.get("source_base_url", "")
                        msg_id = msg.get("id", "")
                        if att_id and source_base_url and msg_id:
                            logger.info(f"[Processor] Downloading hosted content: {source_base_url}/messages/{msg_id}/hostedContents/{att_id}")
                            return self.teams_client.download_hosted_content(source_base_url, msg_id, att_id)
                        return b""

                    if self.audio_processor.is_audio_attachment(att):
                        try:
                            effective_name = att_name if att_name and att_name != att.get("content_type", "") else "voice_note.ogg"
                            audio_bytes = _download_media()
                            transcript = self.audio_processor.transcribe_audio(audio_bytes, effective_name)
                            if transcript:
                                parts.append(f"Meeting Audio Transcript:\n{transcript}")
                                msg["has_audio"] = True
                        except Exception as e:
                            logger.warning(f"[Processor] Meeting audio transcription failed: {e}")
                    elif self.audio_processor.is_video_attachment(att):
                        try:
                            effective_name = att_name if att_name and att_name != att.get("content_type", "") else "voice_note.mp4"
                            video_bytes = _download_media()
                            mp3_bytes = self.audio_processor.video_to_mp3(video_bytes, effective_name)
                            mp3_name = effective_name.rsplit(".", 1)[0] + ".mp3"
                            transcript = self.audio_processor.transcribe_audio(mp3_bytes, mp3_name)
                            if transcript:
                                parts.append(f"Meeting Video Transcript:\n{transcript}")
                                msg["has_video"] = True
                        except Exception as e:
                            logger.warning(f"[Processor] Meeting video transcription failed: {e}")

        return "\n".join(parts) if parts else "Meeting event (no details available)"

    def _collect_thread_content(self, thread: dict) -> str:
        if thread.get("is_meeting"):
            return self._collect_meeting_content(thread)

        parts = []
        for msg in thread.get("messages", []):
            sender = msg.get("sender", "Unknown")
            content = (msg.get("content") or "").strip()
            created_at = msg.get("created_at", "")
            attachments = msg.get("attachments", [])

            timestamp = ""
            if created_at:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    timestamp = dt.strftime("[%Y-%m-%d %H:%M]")
                except Exception:
                    timestamp = f"[{created_at[:16]}]"

            if content:
                parts.append(f"{timestamp} {sender}: {content}")

            for att in attachments:
                att_name = att.get("name") or att.get("content_type", "attachment")
                content_url = att.get("content_url") or ""

                if self.audio_processor and self.teams_client:
                    def _download_media(att=att, content_url=content_url, msg=msg):
                        if content_url:
                            return self.teams_client.download_attachment_content(content_url)
                        card_content = att.get("card_content") or ""
                        if card_content:
                            try:
                                import json as _json
                                card = _json.loads(card_content)
                                media_url = card.get("media", [{}])[0].get("url", "")
                                if media_url:
                                    logger.info("[Processor] Downloading audio card via AMS URL from card_content")
                                    return self.teams_client.download_attachment_content(media_url)
                            except Exception as _e:
                                logger.warning(f"[Processor] Failed to parse card_content for media URL: {_e}")
                        att_id = att.get("id", "")
                        source_base_url = msg.get("source_base_url", "")
                        msg_id = msg.get("id", "")
                        if att_id and source_base_url and msg_id:
                            logger.info(f"[Processor] Downloading hosted content: {source_base_url}/messages/{msg_id}/hostedContents/{att_id}")
                            return self.teams_client.download_hosted_content(source_base_url, msg_id, att_id)
                        return b""

                    if self.audio_processor.is_audio_attachment(att):
                        effective_name = att_name if att_name and att_name != att.get("content_type", "") else "voice_note.ogg"
                        try:
                            audio_bytes = _download_media()
                            transcript = self.audio_processor.transcribe_audio(audio_bytes, effective_name)
                            if transcript:
                                parts.append(f"{timestamp} {sender} [voice note]: {transcript}")
                                msg["has_audio"] = True
                            else:
                                parts.append(f"{timestamp} {sender}: [sent a voice note: {effective_name}]")
                        except Exception as e:
                            logger.warning(f"[Processor] Failed to transcribe audio {effective_name}: {e}")
                            parts.append(f"{timestamp} {sender}: [sent a voice note: {effective_name}]")
                    elif self.audio_processor.is_video_attachment(att):
                        effective_name = att_name if att_name and att_name != att.get("content_type", "") else "voice_note.mp4"
                        try:
                            video_bytes = _download_media()
                            mp3_bytes = self.audio_processor.video_to_mp3(video_bytes, effective_name)
                            mp3_name = effective_name.rsplit(".", 1)[0] + ".mp3"
                            transcript = self.audio_processor.transcribe_audio(mp3_bytes, mp3_name)
                            if transcript:
                                parts.append(f"{timestamp} {sender} [video audio]: {transcript}")
                                msg["has_video"] = True
                            else:
                                parts.append(f"{timestamp} {sender}: [sent a video: {effective_name}]")
                        except Exception as e:
                            logger.warning(f"[Processor] Failed to process video {effective_name}: {e}")
                            parts.append(f"{timestamp} {sender}: [sent a video: {effective_name}]")
                    else:
                        parts.append(f"{timestamp} {sender}: [shared a file: {att_name}]")
                else:
                    if not content and att_name:
                        parts.append(f"{timestamp} {sender}: [attachment: {att_name}]")

        return "\n".join(parts)

    def clarify_thread(self, raw_text: str) -> str:
        if not raw_text.strip():
            return raw_text
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": CLARIFY_SYSTEM_PROMPT},
                    {"role": "user", "content": raw_text},
                ],
                temperature=0.2,
                max_tokens=4096,
            )
            clarified = response.choices[0].message.content.strip()
            logger.info(f"[Processor] Clarified thread: {len(raw_text)} chars -> {len(clarified)} chars")
            return clarified
        except Exception as e:
            logger.error(f"[Processor] Clarification failed: {e}")
            return raw_text

    def embed_text(self, text: str) -> list:
        try:
            client = _get_embeddings_client()
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=text[:8000],
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"[Processor] Embedding failed: {e}")
            return []

    def process_thread(self, thread: dict) -> dict:
        raw_text = self._collect_thread_content(thread)
        clarified = self.clarify_thread(raw_text)
        embedding = self.embed_text(clarified) if clarified else []

        return {
            **thread,
            "raw_text": raw_text,
            "clarified_content": clarified,
            "embedding": embedding,
        }
