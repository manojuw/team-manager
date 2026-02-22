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


SYSTEM_PROMPT = """You are an AI assistant that answers questions about Microsoft Teams conversations and project discussions.

You have access to relevant conversation excerpts from Microsoft Teams channels. Use them to answer questions accurately.

Guidelines:
- Answer based ONLY on the provided context. If the information is not in the context, say so clearly.
- When referencing team members, use their names as they appear in the messages.
- When discussing commitments or promises, quote the relevant message and attribute it to the person who said it.
- Include dates and timestamps when relevant to show when things were discussed.
- If asked about project status, summarize the most recent relevant discussions.
- Be specific and cite the conversations you're referencing.
- If multiple people discussed the same topic, summarize all perspectives.
- Format your response clearly with sections if the answer covers multiple points.
"""


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=64),
    retry=retry_if_exception(is_rate_limit_error),
    reraise=True,
)
def ask_question_ai(question: str, context_results: list, chat_history: list = None) -> str:
    context_text = "\n\n".join(
        [
            f"--- Message (Team: {r['metadata'].get('team', 'N/A')}, "
            f"Channel: {r['metadata'].get('channel', 'N/A')}, "
            f"Relevance: {r['relevance']:.2f}) ---\n{r['content']}"
            for r in context_results
        ]
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if chat_history:
        for entry in chat_history[-10:]:
            messages.append({"role": entry["role"], "content": entry["content"]})

    user_message = f"""Based on the following Teams conversations, please answer this question:

**Question:** {question}

**Relevant Conversations:**
{context_text}

Please provide a comprehensive answer based on the conversations above."""

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
