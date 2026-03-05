import logging
from teams_client import TeamsClient, _is_vtt_attachment
from vtt_parser import parse_vtt, vtt_segments_to_messages

logger = logging.getLogger(__name__)


def process_transcripts(messages: list, client: TeamsClient, chat_or_channel_base_url: str = "") -> list:
    transcript_messages = []

    for msg in messages:
        msg_id = msg.get("id", "")
        created_at = msg.get("created_at", "")

        vtt_attachments = [a for a in msg.get("attachments", []) if a.get("is_vtt")]
        for att in vtt_attachments:
            vtt_content = _download_vtt_attachment(client, att, chat_or_channel_base_url, msg_id)
            if vtt_content:
                segments = parse_vtt(vtt_content)
                if segments:
                    source_name = att.get("name", "transcript.vtt")
                    transcript_msgs = vtt_segments_to_messages(segments, msg_id, created_at, source_name)
                    transcript_messages.extend(transcript_msgs)
                    logger.info(f"Parsed VTT attachment '{source_name}': {len(segments)} segments -> {len(transcript_msgs)} grouped entries")

    return transcript_messages


def _download_vtt_attachment(client: TeamsClient, att: dict, base_url: str, msg_id: str) -> str:
    content_url = att.get("content_url", "")
    att_id = att.get("id", "")
    att_name = att.get("name", "unknown.vtt")

    if content_url:
        try:
            raw = client.download_attachment_content(content_url)
            if raw:
                logger.info(f"Downloaded VTT attachment '{att_name}' ({len(raw)} bytes)")
                return raw.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Failed to download VTT '{att_name}' from content_url: {e}")

    if att_id and base_url:
        try:
            raw = client.download_hosted_content(base_url, msg_id, att_id)
            if raw:
                logger.info(f"Downloaded VTT attachment '{att_name}' via hosted content ({len(raw)} bytes)")
                return raw.decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"Failed to download VTT '{att_name}' from hosted content: {e}")

    logger.warning(f"All download methods failed for VTT attachment '{att_name}'")
    return ""


def _extract_meeting_id(event_detail: dict) -> str:
    meeting_id = event_detail.get("callId", "")
    if not meeting_id:
        meeting_id = event_detail.get("meetingId", "")
    if not meeting_id:
        join_url = event_detail.get("joinWebUrl", "")
        if join_url:
            return join_url
    return meeting_id
