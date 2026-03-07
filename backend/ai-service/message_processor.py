import hashlib
import logging
import os
from typing import Optional
from openai import OpenAI as _OpenAI

logger = logging.getLogger(__name__)


class AudioTranscriptionRequired(Exception):
    pass


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

    @staticmethod
    def _extract_card_urls(card_json: dict) -> list:
        import json as _json
        urls = []

        def _walk(node):
            if not node:
                return
            if isinstance(node, str):
                return
            if isinstance(node, list):
                for item in node:
                    _walk(item)
                return
            if not isinstance(node, dict):
                return
            url = node.get("url", "")
            if url:
                urls.append(url)
            for key in ("actions", "body", "items", "columns", "facts", "rows", "cells"):
                _walk(node.get(key))

        _walk(card_json)
        return urls

    @staticmethod
    def _is_recording_url(url: str) -> bool:
        url_lower = url.lower()
        recording_patterns = (
            "sharepoint.com",
            "sharepoint.us",
            "1drv.ms",
            "onedrive.live.com",
            "microsoftstream.com",
            "web.microsoftstream.com",
        )
        if any(p in url_lower for p in recording_patterns):
            return True
        if any(url_lower.endswith(ext) for ext in (".mp4", ".m4v", ".webm", ".mov")):
            return True
        return False

    def _try_download_and_transcribe_recording(self, url: str, label: str) -> Optional[str]:
        if not self.audio_processor or not self.teams_client:
            return None
        try:
            logger.info(f"[Processor] Trying recording download: {label} ({url[:80]})")
            if url.startswith("https://graph.microsoft.com"):
                video_bytes = self.teams_client._get_raw(url)
            else:
                video_bytes = self.teams_client.get_recording_from_sharing_url(url)
            if not video_bytes:
                logger.warning(f"[Processor] No bytes from recording URL: {label}")
                return None
            logger.info(f"[Processor] Downloaded {len(video_bytes)} bytes for {label}, converting to MP3")
            mp3_bytes = self.audio_processor.video_to_mp3(video_bytes, "recording.mp4")
            cache_key = hashlib.md5(url.encode()).hexdigest()
            transcript = self.audio_processor.transcribe_audio(mp3_bytes, "recording.mp3", cache_key=cache_key)
            if transcript:
                logger.info(f"[Processor] Recording transcribed: {len(transcript)} chars")
                return transcript
            logger.warning(f"[Processor] Sarvam AI returned empty transcript for: {label}")
            return None
        except Exception as e:
            logger.warning(f"[Processor] Recording transcription failed for {label}: {e}")
            return None

    def _collect_meeting_content(self, thread: dict) -> str:
        import json as _json
        messages = thread.get("messages", [])
        parts = []

        logger.info(f"[Processor] Meeting thread has {len(messages)} message(s):")
        for i, msg in enumerate(messages):
            msg_type = msg.get("message_type", "message")
            event_detail = msg.get("event_detail", {})
            event_type = event_detail.get("@odata.type", "") if event_detail else ""
            atts = msg.get("attachments", [])
            att_summary = ", ".join(
                f"{a.get('name') or '?'}[{a.get('content_type') or '?'}|url={bool(a.get('content_url'))}|card={bool(a.get('card_content'))}]"
                for a in atts
            ) if atts else "none"
            logger.info(f"[Processor]   msg[{i}] type={msg_type} event={event_type or 'N/A'} attachments=[{att_summary}]")

        recording_transcribed = False

        for status_priority in ("success", "chunkFinished"):
            if recording_transcribed:
                break
            for msg in messages:
                if recording_transcribed:
                    break
                event_detail = msg.get("event_detail") or {}
                odata_type = event_detail.get("@odata.type", "")
                if "callRecording" not in odata_type:
                    continue
                if event_detail.get("callRecordingStatus") != status_priority:
                    continue
                rec_url = event_detail.get("callRecordingUrl") or ""
                if not rec_url:
                    continue
                display_name = event_detail.get("callRecordingDisplayName") or "Recording"
                logger.info(
                    f"[Processor] Found callRecordingUrl in event detail: {display_name} "
                    f"(status={status_priority})"
                )
                transcript = self._try_download_and_transcribe_recording(rec_url, display_name)
                if transcript:
                    parts.append(f"Meeting Recording Transcript:\n{transcript}")
                    msg["has_video"] = True
                    thread["has_video"] = True
                    recording_transcribed = True

        for msg in messages:
            atts = msg.get("attachments", [])
            if not atts or recording_transcribed:
                continue
            for att in atts:
                content_type_att = (att.get("content_type") or "").lower()
                card_content_raw = att.get("card_content") or ""
                att_name = att.get("name") or ""
                content_url = att.get("content_url") or ""

                candidate_urls = []

                if content_url and self._is_recording_url(content_url):
                    candidate_urls.append(("content_url", content_url))

                if card_content_raw and ("adaptive" in content_type_att or "card" in content_type_att or not content_type_att):
                    try:
                        card = _json.loads(card_content_raw)
                        for url in self._extract_card_urls(card):
                            if url and self._is_recording_url(url):
                                candidate_urls.append(("card_action", url))
                    except Exception as _e:
                        logger.warning(f"[Processor] Could not parse card_content for recording URLs: {_e} | raw={card_content_raw[:100]}")

                for label, url in candidate_urls:
                    transcript = self._try_download_and_transcribe_recording(url, f"{att_name or label}")
                    if transcript:
                        parts.append(f"Meeting Recording Transcript:\n{transcript}")
                        msg["has_video"] = True
                        thread["has_video"] = True
                        recording_transcribed = True
                        break
                if recording_transcribed:
                    break

        if not recording_transcribed and self.audio_processor and self.teams_client:
            logger.info("[Processor] No recording card found in any message — will rely on audio/video attachments and event metadata")

        for msg in messages:
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

            event_type = event_detail.get("@odata.type", "") if event_detail else ""
            recording_name = event_detail.get("callRecordingDisplayName", "") if event_detail else ""
            recording_status = event_detail.get("callRecordingStatus", "") if event_detail else ""
            initiator_user = ((event_detail or {}).get("initiator") or {}).get("user", {}) or {}
            initiator = initiator_user.get("displayName", sender)
            join_url = (event_detail or {}).get("joinWebUrl", "")

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
            elif event_type:
                header = f"{timestamp} Meeting Event ({event_type.rsplit('.', 1)[-1]})"
                if sender and sender != "Unknown":
                    header += f" — {sender}"
            else:
                content = (msg.get("content") or "").strip()
                if content:
                    header = f"{timestamp} {sender}: {content}"
                else:
                    header = f"{timestamp} Meeting Event — {sender}"

            if join_url:
                header += f"\nMeeting URL: {join_url}"

            parts.append(header)

            attachments = msg.get("attachments", [])
            for att in attachments:
                att_name = att.get("name") or att.get("content_type", "attachment")
                content_url = att.get("content_url") or ""
                if self.audio_processor and self.teams_client:
                    def _download_media(att=att, content_url=content_url, msg=msg):
                        if content_url and not self._is_recording_url(content_url):
                            return self.teams_client.download_attachment_content(content_url)
                        card_content = att.get("card_content") or ""
                        if card_content:
                            try:
                                import json as _j
                                card = _j.loads(card_content)
                                media_url = card.get("media", [{}])[0].get("url", "")
                                if media_url:
                                    logger.info("[Processor] Downloading audio card via AMS URL from card_content")
                                    return self.teams_client.download_attachment_content(media_url)
                            except Exception as _e:
                                logger.warning(f"[Processor] Failed to parse card_content for media URL: {_e}")
                        source_base_url = msg.get("source_base_url", "")
                        msg_id = msg.get("id", "")
                        if source_base_url and msg_id:
                            hosted = self.teams_client.list_message_hosted_contents(source_base_url, msg_id)
                            logger.info(f"[Processor] Found {len(hosted)} hosted content(s) for message {msg_id}")
                            for item in hosted:
                                blob_id = item.get("id", "")
                                if blob_id:
                                    data = self.teams_client.download_hosted_content(source_base_url, msg_id, blob_id)
                                    if data:
                                        return data
                        return b""

                    if self.audio_processor.is_audio_attachment(att):
                        try:
                            effective_name = att_name if att_name and att_name != att.get("content_type", "") else "voice_note.ogg"
                            logger.info(f"[Processor] Audio attachment: {effective_name}")
                            audio_bytes = _download_media()
                            transcript = self.audio_processor.transcribe_audio(audio_bytes, effective_name)
                            if transcript:
                                parts.append(f"Meeting Audio Transcript:\n{transcript}")
                                msg["has_audio"] = True
                                thread["has_audio"] = True
                        except Exception as e:
                            logger.warning(f"[Processor] Meeting audio transcription failed: {e}")
                    elif self.audio_processor.is_video_attachment(att):
                        try:
                            effective_name = att_name if att_name and att_name != att.get("content_type", "") else "voice_note.mp4"
                            logger.info(f"[Processor] Video attachment: {effective_name}")
                            video_bytes = _download_media()
                            mp3_bytes = self.audio_processor.video_to_mp3(video_bytes, effective_name)
                            mp3_name = effective_name.rsplit(".", 1)[0] + ".mp3"
                            transcript = self.audio_processor.transcribe_audio(mp3_bytes, mp3_name)
                            if transcript:
                                parts.append(f"Meeting Video Transcript:\n{transcript}")
                                msg["has_video"] = True
                                thread["has_video"] = True
                        except Exception as e:
                            logger.warning(f"[Processor] Meeting video transcription failed: {e}")

        has_transcript = any(
            p.startswith("Meeting Recording Transcript:")
            or p.startswith("Meeting Audio Transcript:")
            or p.startswith("Meeting Video Transcript:")
            for p in parts
        )
        if not has_transcript:
            logger.info(
                f"[Processor] Meeting thread has no transcript content — skipping "
                f"(only event metadata: {len(parts)} part(s))"
            )
            return ""

        return "\n".join(parts)

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
                        source_base_url = msg.get("source_base_url", "")
                        msg_id = msg.get("id", "")
                        if source_base_url and msg_id:
                            hosted = self.teams_client.list_message_hosted_contents(source_base_url, msg_id)
                            logger.info(f"[Processor] Found {len(hosted)} hosted content(s) for message {msg_id}, trying each")
                            for item in hosted:
                                blob_id = item.get("id", "")
                                if blob_id:
                                    data = self.teams_client.download_hosted_content(source_base_url, msg_id, blob_id)
                                    if data:
                                        return data
                        return b""

                    if self.audio_processor.is_audio_attachment(att):
                        effective_name = att_name if att_name and att_name != att.get("content_type", "") else "voice_note.ogg"
                        logger.info(f"[Processor] Audio card attachment: content_type={att.get('content_type')}, has_content_url={bool(content_url)}, has_card_content={bool(att.get('card_content'))}, att_id={att.get('id')}")
                        try:
                            audio_bytes = _download_media()
                            transcript = self.audio_processor.transcribe_audio(audio_bytes, effective_name)
                            if transcript:
                                parts.append(f"{timestamp} {sender} [voice note]: {transcript}")
                                msg["has_audio"] = True
                            else:
                                logger.info(f"[Processor] Audio transcription returned empty for {effective_name}, skipping thread")
                                raise AudioTranscriptionRequired(effective_name)
                        except AudioTranscriptionRequired:
                            raise
                        except Exception as e:
                            logger.warning(f"[Processor] Failed to transcribe audio {effective_name}: {e}")
                            raise AudioTranscriptionRequired(effective_name)
                    elif self.audio_processor.is_video_attachment(att):
                        effective_name = att_name if att_name and att_name != att.get("content_type", "") else "voice_note.mp4"
                        logger.info(f"[Processor] Video card attachment: content_type={att.get('content_type')}, has_content_url={bool(content_url)}, has_card_content={bool(att.get('card_content'))}, att_id={att.get('id')}")
                        try:
                            video_bytes = _download_media()
                            mp3_bytes = self.audio_processor.video_to_mp3(video_bytes, effective_name)
                            mp3_name = effective_name.rsplit(".", 1)[0] + ".mp3"
                            transcript = self.audio_processor.transcribe_audio(mp3_bytes, mp3_name)
                            if transcript:
                                parts.append(f"{timestamp} {sender} [video audio]: {transcript}")
                                msg["has_video"] = True
                            else:
                                logger.info(f"[Processor] Video transcription returned empty for {effective_name}, skipping thread")
                                raise AudioTranscriptionRequired(effective_name)
                        except AudioTranscriptionRequired:
                            raise
                        except Exception as e:
                            logger.warning(f"[Processor] Failed to process video {effective_name}: {e}")
                            raise AudioTranscriptionRequired(effective_name)
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

    def _generate_thread_plan(self, clarified_content: str) -> dict:
        if not clarified_content or len(clarified_content.strip()) < 30:
            return {"summary": "", "task_planning": ""}
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You analyze translated Teams conversation threads and produce a structured summary and task plan. "
                            "Be concise and accurate. Respond with JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Conversation:\n{clarified_content[:3000]}\n\n"
                            "Produce JSON with two fields:\n"
                            "1. \"summary\": 2-3 sentences describing what this conversation is about and its main outcome.\n"
                            "2. \"task_planning\": A Markdown-formatted plan with these sections (omit any section that has no content):\n"
                            "   ## Action Items\n"
                            "   - [ ] **Person** — what needs to be done\n"
                            "   ## Decisions Made\n"
                            "   - decision\n"
                            "   ## Open Questions\n"
                            "   - question\n\n"
                            "Return JSON only: {\"summary\": \"...\", \"task_planning\": \"...\"}"
                        ),
                    },
                ],
                temperature=0,
                max_tokens=1000,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            import json as _json
            data = _json.loads(raw)
            task_planning_raw = data.get("task_planning", "")
            if isinstance(task_planning_raw, dict):
                md_parts = []
                for section, items in task_planning_raw.items():
                    md_parts.append(section)
                    if isinstance(items, list):
                        for item in items:
                            md_parts.append(str(item))
                    else:
                        md_parts.append(str(items))
                task_planning_str = "\n".join(md_parts)
            else:
                task_planning_str = str(task_planning_raw)
            result = {
                "summary": str(data.get("summary", "")),
                "task_planning": task_planning_str,
            }
            logger.info(f"[Processor] Generated thread plan: summary={len(result['summary'])} chars, plan={len(result['task_planning'])} chars")
            return result
        except Exception as e:
            logger.warning(f"[Processor] _generate_thread_plan failed: {e}")
            return {"summary": "", "task_planning": ""}

    def process_thread(self, thread: dict):
        try:
            raw_text = self._collect_thread_content(thread)
        except AudioTranscriptionRequired as e:
            logger.info(f"[Processor] Dropping thread — audio transcription failed for: {e}")
            return None

        if thread.get("is_meeting") and not raw_text.strip():
            logger.info("[Processor] Dropping meeting thread — no transcript could be extracted")
            return None

        clarified = self.clarify_thread(raw_text)
        embedding = self.embed_text(clarified) if clarified else []
        plan = self._generate_thread_plan(clarified) if clarified else {"summary": "", "task_planning": ""}

        return {
            **thread,
            "raw_text": raw_text,
            "clarified_content": clarified,
            "embedding": embedding,
            "summary": plan["summary"],
            "task_planning": plan["task_planning"],
        }
