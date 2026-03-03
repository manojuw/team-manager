import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def _parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


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
