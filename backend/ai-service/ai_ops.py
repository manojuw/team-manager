import os
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

AI_INTEGRATIONS_OPENAI_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")
AI_INTEGRATIONS_OPENAI_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")

openai_client = OpenAI(
    api_key=AI_INTEGRATIONS_OPENAI_API_KEY,
    base_url=AI_INTEGRATIONS_OPENAI_BASE_URL,
)


def is_rate_limit_error(exception: BaseException) -> bool:
    error_msg = str(exception)
    return (
        "429" in error_msg
        or "RATELIMIT_EXCEEDED" in error_msg
        or "quota" in error_msg.lower()
        or "rate limit" in error_msg.lower()
        or (hasattr(exception, "status_code") and exception.status_code == 429)
    )


SYSTEM_PROMPT = """You are an AI assistant that answers questions about project knowledge including Microsoft Teams conversations, Azure DevOps work items, and meeting transcripts.

You have access to relevant context from multiple sources:
- **Conversation threads**: Groups of related messages from Teams channels and group chats, already translated into clear English. Each thread represents a focused discussion between team members.
- **Azure DevOps work items**: User stories, tasks, bugs, features, and their comments/discussions.
- **Meeting transcripts**: Parsed transcripts from recorded meetings.

Guidelines:
- Answer based ONLY on the provided context. If the information is not in the context, say so clearly.
- When referencing team members, use their names as they appear in the conversations.
- When discussing commitments or promises, quote the relevant exchange and attribute it to the person who said it.
- Include dates and timestamps when relevant to show when things were discussed.
- If asked about project status, combine insights from both conversation threads and work items.
- When work items and conversations discuss the same topic, cross-reference them for a complete picture.
- For work items, reference the work item ID (e.g., #12345) and its current state.
- Be specific and cite your sources (which thread, which work item, which date).
- Format your response clearly with sections if the answer covers multiple points.
"""


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=64),
    retry=retry_if_exception(is_rate_limit_error),
    reraise=True,
)
def ask_question_ai(question: str, context_results: list, chat_history: list = None) -> str:
    context_parts = []
    for r in context_results:
        meta = r.get("metadata", {})
        source_type = meta.get("source_type", "")
        result_type = meta.get("result_type", "message")

        if source_type == "azure_devops":
            header = f"--- DevOps Work Item (Relevance: {r['relevance']:.2f}) ---"
        elif result_type == "thread":
            participants = ", ".join(meta.get("participants", [])) or "Unknown"
            started = str(meta.get("created_at", ""))[:16]
            msg_count = meta.get("message_count", "?")
            team = meta.get("team", "") or meta.get("source_identifier", {}).get("chat_name", "")
            channel = meta.get("channel", "")
            location = f"Channel: {channel}" if channel else (f"Chat: {team}" if team else "")
            header = (
                f"--- Conversation Thread ({location}, {started}, "
                f"{msg_count} messages, Participants: {participants}, "
                f"Relevance: {r['relevance']:.2f}) ---"
            )
        else:
            header = (
                f"--- Message (Team: {meta.get('team', 'N/A')}, "
                f"Channel: {meta.get('channel', 'N/A')}, "
                f"Relevance: {r['relevance']:.2f}) ---"
            )
        context_parts.append(f"{header}\n{r['content']}")
    context_text = "\n\n".join(context_parts)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if chat_history:
        for entry in chat_history[-10:]:
            messages.append({"role": entry["role"], "content": entry["content"]})

    user_message = f"""Based on the following context (conversations, work items, and transcripts), please answer this question:

**Question:** {question}

**Relevant Context:**
{context_text}

Please provide a comprehensive answer based on the context above."""

    messages.append({"role": "user", "content": user_message})

    response = openai_client.chat.completions.create(
        model="gpt-5.2",
        messages=messages,
        max_completion_tokens=8192,
    )

    return response.choices[0].message.content or "I couldn't generate a response."


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=64),
    retry=retry_if_exception(is_rate_limit_error),
    reraise=True,
)
def summarize_ai(context_results: list) -> str:
    context_text = "\n\n".join(
        [f"--- Message ---\n{r['content']}" for r in context_results]
    )

    messages = [
        {
            "role": "system",
            "content": "You are an AI assistant that summarizes Microsoft Teams channel conversations. "
            "Provide a clear summary of the current work, ongoing discussions, key decisions, "
            "and any commitments made by team members.",
        },
        {
            "role": "user",
            "content": f"Please summarize the following Teams channel conversations:\n\n{context_text}",
        },
    ]

    response = openai_client.chat.completions.create(
        model="gpt-5.2",
        messages=messages,
        max_completion_tokens=8192,
    )

    return response.choices[0].message.content or "I couldn't generate a summary."
