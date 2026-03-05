import json as _json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

RECORDING_CARD_WINDOW = timedelta(minutes=60)


def _parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _extract_card_urls_te(node) -> list:
    urls = []
    if not node:
        return urls
    if isinstance(node, str):
        return urls
    if isinstance(node, list):
        for item in node:
            urls.extend(_extract_card_urls_te(item))
        return urls
    if not isinstance(node, dict):
        return urls
    url = node.get("url", "")
    if url:
        urls.append(url)
    for key in ("actions", "body", "items", "columns", "facts", "rows", "cells"):
        urls.extend(_extract_card_urls_te(node.get(key)))
    return urls


def _is_recording_url_te(url: str) -> bool:
    url_lower = url.lower()
    recording_patterns = (
        "sharepoint.com", "sharepoint.us",
        "1drv.ms", "onedrive.live.com",
        "microsoftstream.com", "web.microsoftstream.com",
    )
    if any(p in url_lower for p in recording_patterns):
        return True
    if any(url_lower.endswith(ext) for ext in (".mp4", ".m4v", ".webm", ".mov")):
        return True
    return False


def _is_recording_card_message(msg: dict) -> bool:
    for att in msg.get("attachments", []):
        content_url = att.get("content_url") or ""
        if content_url and _is_recording_url_te(content_url):
            return True
        card_raw = att.get("card_content") or ""
        if card_raw:
            try:
                card = _json.loads(card_raw)
                for url in _extract_card_urls_te(card):
                    if url and _is_recording_url_te(url):
                        return True
            except Exception:
                pass
    return False


def build_meeting_threads(messages: list) -> tuple:
    sorted_msgs = sorted(
        messages,
        key=lambda m: _parse_dt(m.get("created_at", "")) or datetime.min.replace(tzinfo=timezone.utc)
    )

    event_msgs = []
    card_msgs = []
    remaining_ids = set()

    for msg in sorted_msgs:
        if msg.get("message_type") == "meeting_event":
            event_msgs.append(msg)
        elif _is_recording_card_message(msg):
            card_msgs.append(msg)
        else:
            remaining_ids.add(id(msg))

    recording_card_ids_used = set()
    meeting_threads = []

    for event_msg in event_msgs:
        event_time = _parse_dt(event_msg.get("created_at", ""))
        associated_cards = []

        for card_msg in card_msgs:
            if id(card_msg) in recording_card_ids_used:
                continue
            card_time = _parse_dt(card_msg.get("created_at", ""))
            if event_time and card_time:
                diff = card_time - event_time
                if timedelta(0) <= diff <= RECORDING_CARD_WINDOW:
                    associated_cards.append((diff, card_msg))

        associated_cards.sort(key=lambda x: x[0])

        thread_msgs = [event_msg]
        for diff, card_msg in associated_cards:
            thread_msgs.append(card_msg)
            recording_card_ids_used.add(id(card_msg))
            minutes = diff.total_seconds() / 60
            logger.info(f"[Thread] Recording card matched to meeting event (time diff={minutes:.1f} minutes)")

        sender = event_msg.get("sender", "Unknown")
        event_time_parsed = _parse_dt(event_msg.get("created_at", ""))
        last_time = event_time_parsed
        if thread_msgs:
            times = [_parse_dt(m.get("created_at", "")) for m in thread_msgs]
            last_time = max((t for t in times if t), default=event_time_parsed)

        logger.info(f"[Thread] Meeting event has {len(associated_cards)} recording card(s) attached")

        meeting_threads.append({
            "id": str(uuid.uuid4()),
            "messages": thread_msgs,
            "participants": {sender},
            "started_at": event_time_parsed,
            "last_message_at": last_time,
            "has_audio": False,
            "has_video": False,
            "is_meeting": True,
        })

    remaining_chat = [
        m for m in sorted_msgs
        if id(m) in remaining_ids or (
            _is_recording_card_message(m) and id(m) not in recording_card_ids_used
        )
    ]

    logger.info(
        f"[Thread] build_meeting_threads: {len(event_msgs)} meeting event(s), "
        f"{len(card_msgs)} recording card(s), "
        f"{len(recording_card_ids_used)} card(s) matched, "
        f"{len(remaining_chat)} chat message(s) remaining"
    )

    return meeting_threads, remaining_chat


def _thread_summary(thread: dict, max_chars: int = 300) -> str:
    msgs = thread.get("messages", [])
    parts = []
    for m in msgs[:5]:
        sender = m.get("sender", "?")
        content = (m.get("content") or "")[:100]
        if content:
            parts.append(f"{sender}: {content}")
    return " | ".join(parts)[:max_chars]


class ThreadEngine:
    def __init__(self, time_window_minutes: int = 60, lookback_count: int = 10, openai_client=None):
        self.time_window = timedelta(minutes=time_window_minutes)
        self.lookback_count = lookback_count
        self.openai_client = openai_client

    def _check_relatedness(self, message: dict, candidate_threads: list) -> Optional[int]:
        if not self.openai_client or not candidate_threads:
            return None

        content = (message.get("content") or "").strip()
        if not content or len(content) < 5:
            return None

        summaries = []
        for i, t in enumerate(candidate_threads):
            summaries.append(f"Thread {i + 1}: {_thread_summary(t)}")

        prompt = (
            f"New message: '{content[:300]}'\n\n"
            f"Recent threads:\n" + "\n".join(summaries) + "\n\n"
            "Which thread number does this new message most likely belong to? "
            "Reply with just the number (e.g. '2') if it clearly relates to a thread, "
            "or 'new' if it is a completely different topic."
        )

        try:
            resp = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a conversation analyst. Answer with only a number or 'new'."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=5,
                temperature=0,
            )
            answer = resp.choices[0].message.content.strip().lower()
            if answer == "new":
                return None
            idx = int(answer) - 1
            if 0 <= idx < len(candidate_threads):
                return idx
        except Exception as e:
            logger.warning(f"[Thread] Relatedness check failed: {e}")

        return None

    def group_messages(self, messages: list) -> list:
        if not messages:
            return []

        sorted_msgs = sorted(
            messages,
            key=lambda m: _parse_dt(m.get("created_at", "")) or datetime.min.replace(tzinfo=timezone.utc)
        )

        threads = []
        msg_id_to_thread_idx = {}

        for msg in sorted_msgs:
            msg_id = msg.get("id", "")
            parent_id = msg.get("parent_message_id")
            msg_time = _parse_dt(msg.get("created_at", ""))
            content = (msg.get("content") or "").strip()
            sender = msg.get("sender", "Unknown")
            has_audio = bool(msg.get("has_audio", False))
            has_video = bool(msg.get("has_video", False))

            placed = False

            if parent_id and parent_id in msg_id_to_thread_idx:
                idx = msg_id_to_thread_idx[parent_id]
                threads[idx]["messages"].append(msg)
                threads[idx]["participants"].add(sender)
                if msg_time:
                    threads[idx]["last_message_at"] = msg_time
                if msg_id:
                    msg_id_to_thread_idx[msg_id] = idx
                if has_audio:
                    threads[idx]["has_audio"] = True
                if has_video:
                    threads[idx]["has_video"] = True
                placed = True

            if not placed and threads:
                last_thread = threads[-1]
                last_time = last_thread.get("last_message_at")
                if last_time and msg_time and (msg_time - last_time) <= self.time_window:
                    last_thread["messages"].append(msg)
                    last_thread["participants"].add(sender)
                    last_thread["last_message_at"] = msg_time
                    if msg_id:
                        msg_id_to_thread_idx[msg_id] = len(threads) - 1
                    if has_audio:
                        last_thread["has_audio"] = True
                    if has_video:
                        last_thread["has_video"] = True
                    placed = True

            if not placed and threads and self.openai_client:
                lookback = threads[-self.lookback_count:]
                rel_idx = self._check_relatedness(msg, lookback)
                if rel_idx is not None:
                    actual_idx = len(threads) - self.lookback_count + rel_idx
                    if actual_idx < 0:
                        actual_idx = rel_idx
                    threads[actual_idx]["messages"].append(msg)
                    threads[actual_idx]["participants"].add(sender)
                    if msg_time:
                        threads[actual_idx]["last_message_at"] = msg_time
                    if msg_id:
                        msg_id_to_thread_idx[msg_id] = actual_idx
                    if has_audio:
                        threads[actual_idx]["has_audio"] = True
                    if has_video:
                        threads[actual_idx]["has_video"] = True
                    placed = True

            if not placed:
                new_thread = {
                    "id": str(uuid.uuid4()),
                    "messages": [msg],
                    "participants": {sender},
                    "started_at": msg_time,
                    "last_message_at": msg_time,
                    "has_audio": has_audio,
                    "has_video": has_video,
                }
                threads.append(new_thread)
                if msg_id:
                    msg_id_to_thread_idx[msg_id] = len(threads) - 1

        for t in threads:
            t["participants"] = sorted(t["participants"])
            t["message_count"] = len(t["messages"])

        logger.info(f"[Thread] Grouped {len(sorted_msgs)} messages into {len(threads)} threads")
        return threads
