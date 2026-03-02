import re
import logging

logger = logging.getLogger(__name__)

TIMESTAMP_PATTERN = re.compile(
    r'(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})'
)
SPEAKER_TAG_PATTERN = re.compile(r'<v\s+([^>]+)>(.*?)</v>', re.DOTALL)
SPEAKER_PREFIX_PATTERN = re.compile(r'^([A-Za-z][A-Za-z0-9 .\'-]{1,50}):\s+(.+)', re.DOTALL)
HTML_TAG_PATTERN = re.compile(r'<[^>]+>')


def parse_vtt(content: str) -> list:
    lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')

    segments = []
    i = 0

    while i < len(lines) and not lines[i].strip().startswith('WEBVTT'):
        i += 1
    if i < len(lines):
        i += 1

    while i < len(lines):
        while i < len(lines) and not lines[i].strip():
            i += 1

        if i >= len(lines):
            break

        timestamp_match = TIMESTAMP_PATTERN.search(lines[i])
        if not timestamp_match:
            if i + 1 < len(lines):
                timestamp_match = TIMESTAMP_PATTERN.search(lines[i + 1])
                if timestamp_match:
                    i += 1
                else:
                    i += 1
                    continue
            else:
                i += 1
                continue

        start_time = timestamp_match.group(1).replace(',', '.')
        end_time = timestamp_match.group(2).replace(',', '.')
        i += 1

        text_lines = []
        while i < len(lines) and lines[i].strip():
            text_lines.append(lines[i])
            i += 1

        raw_text = ' '.join(text_lines)

        speaker = "Unknown"
        text = raw_text

        tag_match = SPEAKER_TAG_PATTERN.search(raw_text)
        if tag_match:
            speaker = tag_match.group(1).strip()
            text = tag_match.group(2).strip()
        else:
            cleaned = HTML_TAG_PATTERN.sub('', raw_text).strip()
            prefix_match = SPEAKER_PREFIX_PATTERN.match(cleaned)
            if prefix_match:
                speaker = prefix_match.group(1).strip()
                text = prefix_match.group(2).strip()
            else:
                text = cleaned

        text = HTML_TAG_PATTERN.sub('', text).strip()

        if text:
            segments.append({
                "speaker": speaker,
                "text": text,
                "start_time": start_time,
                "end_time": end_time,
            })

    return segments


def group_segments(segments: list, max_chars: int = 500) -> list:
    if not segments:
        return []

    grouped = []
    current_speaker = segments[0]["speaker"]
    current_texts = [segments[0]["text"]]
    current_start = segments[0]["start_time"]
    current_end = segments[0]["end_time"]
    current_len = len(segments[0]["text"])

    for seg in segments[1:]:
        if seg["speaker"] == current_speaker and current_len + len(seg["text"]) < max_chars:
            current_texts.append(seg["text"])
            current_end = seg["end_time"]
            current_len += len(seg["text"]) + 1
        else:
            grouped.append({
                "speaker": current_speaker,
                "text": " ".join(current_texts),
                "start_time": current_start,
                "end_time": current_end,
            })
            current_speaker = seg["speaker"]
            current_texts = [seg["text"]]
            current_start = seg["start_time"]
            current_end = seg["end_time"]
            current_len = len(seg["text"])

    grouped.append({
        "speaker": current_speaker,
        "text": " ".join(current_texts),
        "start_time": current_start,
        "end_time": current_end,
    })

    return grouped


def vtt_segments_to_messages(segments: list, parent_msg_id: str, created_at: str,
                              source_name: str = "") -> list:
    grouped = group_segments(segments)
    messages = []
    for idx, seg in enumerate(grouped):
        msg_id = f"{parent_msg_id}-transcript-{idx}"
        content = f"[Transcript{' - ' + source_name if source_name else ''}] [{seg['start_time']} - {seg['end_time']}] {seg['speaker']}: {seg['text']}"
        messages.append({
            "id": msg_id,
            "content": content,
            "sender": seg["speaker"],
            "created_at": created_at,
            "attachments": [],
            "message_type": "transcript",
        })
    return messages
