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
                            "to determine if they describe a work item that needs to be created or tracked RIGHT NOW. "
                            "A work item qualifies only if it meets AT LEAST ONE of these criteria: "
                            "(a) an active or current bug/problem is being reported, "
                            "(b) someone explicitly requests that a task, ticket, or work item be created, "
                            "(c) someone is explicitly assigned or asked to do something specific, "
                            "(d) someone says to note it down, log it, add it to the plan/sprint/backlog, "
                            "(e) a specific phase, sprint, iteration, date, or time period is mentioned — meaning the item is explicitly scheduled. "
                            "The following do NOT qualify: future ideas with no timeline, vague aspirational wishes "
                            "('it would be nice if...', 'maybe someday...', 'we could consider...'), "
                            "hypothetical discussions, and casual brainstorming with no explicit commitment or schedule. "
                            "Respond with JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Thread context: {thread_context[:400]}\n\n"
                            f"Message: {message_text[:500]}\n\n"
                            "Does this message describe a CURRENT active issue, OR explicitly request/assign/schedule "
                            "something to be created or tracked right now? "
                            "Vague future ideas, casual wishes, and unscheduled aspirations are NOT work items. "
                            "Return JSON only: {\"is_work_item\": true or false, \"reason\": \"brief explanation\"}"
                        ),
                    },
                ],
                temperature=0,
                max_tokens=80,
            )
            raw = response.choices[0].message.content.strip()
            data = json.loads(raw)
            result = bool(data.get("is_work_item", False))
            reason = data.get("reason", "")
            logger.info(f"[WorkItem] → is_work_item={result} reason='{reason}'")
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
                            "Only extract a work item if it meets AT LEAST ONE of these criteria: "
                            "(a) an active/current bug or problem is being reported, "
                            "(b) someone explicitly requests that a task, ticket, or work item be created, "
                            "(c) someone is explicitly assigned or asked to do something specific, "
                            "(d) someone explicitly says to note it down, log it, or add it to the plan/sprint/backlog, "
                            "(e) a specific phase, sprint, iteration, date, month, or time period is mentioned in connection with the item — meaning it is explicitly scheduled. "
                            "Do NOT extract: future unscheduled ideas, vague aspirational wishes ('it would be nice if...', "
                            "'maybe someday...', 'we could consider...'), hypothetical discussions, or casual brainstorming "
                            "with no explicit commitment, assignment, or timeline. "
                            "Be conservative — only flag clear, immediately actionable or explicitly scheduled items. "
                            "Respond with JSON only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Conversation:\n{clarified_content[:3000]}\n\n"
                            "Identify work items that need to be created or tracked. "
                            "For each, set `is_immediate: true` if it is a current active issue, explicitly assigned, "
                            "explicitly asked to be tracked/logged, OR tied to a specific phase/sprint/iteration/date/month/period. "
                            "Set `is_immediate: false` if it is a vague future idea, casual wish, or aspiration with no "
                            "explicit commitment, assignment, or scheduled timeline. "
                            "Return JSON only:\n"
                            "{\"has_work_items\": true or false, "
                            "\"work_items\": [{\"title\": \"...\", \"description\": \"...\", "
                            "\"is_immediate\": true or false, \"reason\": \"brief explanation\"}]}"
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
            data = json.loads(raw)
            has = data.get("has_work_items", False)
            all_items = data.get("work_items", []) if has else []
            parsed = []
            for item in all_items:
                title = str(item.get("title", ""))[:80]
                if not title:
                    continue
                is_immediate = bool(item.get("is_immediate", True))
                reason = item.get("reason", "")
                if is_immediate:
                    logger.info(f"[WorkItem] → keeping '{title}' (immediate: {reason})")
                    parsed.append({
                        "title": title,
                        "description": str(item.get("description", "")),
                    })
                else:
                    logger.info(f"[WorkItem] → skipping '{title}' (not immediate: {reason})")
            logger.info(f"[WorkItem] → has_work_items={has} kept={len(parsed)}/{len(all_items)}")
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
