import json
import logging

logger = logging.getLogger(__name__)


class WorkItemExtractor:
    def __init__(self, openai_client):
        self.openai = openai_client

    def check_message_for_work_item(self, message_text: str, thread_context: str) -> bool:
        if not message_text or len(message_text.strip()) < 10:
            return False
        logger.info(f"[WorkItem] Checking message: '{message_text[:80]}...'")
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You analyze messages from Teams chats (which may be in Hindi, Hinglish, or English) "
                            "to determine if they imply that a work item (bug, feature request, task, or improvement) "
                            "needs to be created. Respond with JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Thread context: {thread_context[:400]}\n\n"
                            f"Message: {message_text[:500]}\n\n"
                            "Does this message explicitly request or clearly imply that a work item (bug, feature, task, "
                            "or improvement) needs to be created or tracked? "
                            "Casual conversation, greetings, status updates, and acknowledgements are NOT work items. "
                            "Respond with JSON only: {\"is_work_item\": true or false}"
                        ),
                    },
                ],
                temperature=0,
                max_tokens=30,
            )
            raw = response.choices[0].message.content.strip()
            data = json.loads(raw)
            result = bool(data.get("is_work_item", False))
            logger.info(f"[WorkItem] → is_work_item={result}")
            return result
        except Exception as e:
            logger.warning(f"[WorkItem] check_message_for_work_item error: {e}")
            return False

    def extract_work_items_from_thread(self, clarified_content: str) -> list:
        if not clarified_content or len(clarified_content.strip()) < 20:
            return []
        logger.info(f"[WorkItem] Extracting work items from thread content ({len(clarified_content)} chars)")
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You analyze translated Teams conversations to identify actionable work items. "
                            "A work item is a clearly implied bug, feature request, task, or improvement. "
                            "Casual chat, greetings, and vague references are NOT work items. "
                            "Be conservative — only flag clear, actionable items. Respond with JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Conversation:\n{clarified_content[:3000]}\n\n"
                            "Does this conversation indicate that one or more work items need to be created or tracked? "
                            "If yes, provide titles (max 80 chars each) and detailed descriptions. "
                            "Return JSON only:\n"
                            "{\"has_work_items\": true or false, "
                            "\"work_items\": [{\"title\": \"...\", \"description\": \"...\"}]}"
                        ),
                    },
                ],
                temperature=0,
                max_tokens=800,
            )
            raw = response.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            has = data.get("has_work_items", False)
            items = data.get("work_items", []) if has else []
            parsed = [
                {"title": str(item.get("title", ""))[:80], "description": str(item.get("description", ""))}
                for item in items
                if item.get("title")
            ]
            logger.info(f"[WorkItem] → has_work_items={has} items={[i['title'] for i in parsed]}")
            return parsed
        except Exception as e:
            logger.warning(f"[WorkItem] extract_work_items_from_thread error: {e}")
            return []

    def analyze_thread(self, processed_thread: dict) -> list:
        thread_id = processed_thread.get("id", "?")
        clarified = processed_thread.get("clarified_content", "")
        messages = processed_thread.get("messages", [])

        logger.info(
            f"[WorkItem] Analyzing thread {thread_id} "
            f"({len(messages)} messages, {len(clarified)} chars clarified)"
        )

        if not clarified:
            logger.info(f"[WorkItem] Thread {thread_id}: no clarified content, skipping")
            return []

        context = clarified[:400]
        all_msg_ids = [m["id"] for m in messages if m.get("id")]

        trigger_message_ids = []
        for msg in messages:
            content = (msg.get("content") or "").strip()
            msg_id = msg.get("id")
            if not msg_id:
                continue
            if self.check_message_for_work_item(content, context):
                trigger_message_ids.append(msg_id)

        logger.info(
            f"[WorkItem] Pass 1 complete: {len(trigger_message_ids)}/{len(messages)} messages triggered"
        )

        if trigger_message_ids:
            work_items = self.extract_work_items_from_thread(clarified)
            for item in work_items:
                item["source_message_ids"] = trigger_message_ids
        else:
            work_items = self.extract_work_items_from_thread(clarified)
            if work_items:
                logger.info(f"[WorkItem] Pass 2 (whole thread) result: {len(work_items)} item(s)")
            for item in work_items:
                item["source_message_ids"] = all_msg_ids

        logger.info(
            f"[WorkItem] Thread {thread_id}: found {len(work_items)} work item(s) "
            f"(trigger msgs: {len(trigger_message_ids)})"
        )
        return work_items
