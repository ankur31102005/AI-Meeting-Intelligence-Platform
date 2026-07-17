"""OpenAI meeting-intelligence provider (structured outputs).

Uses the SDK's structured-output parsing: we hand OpenAI our Pydantic schema
and it is GUARANTEED to return JSON matching it (no brittle text parsing, no
"model forgot a field"). The client is built once and reused.
"""

from functools import lru_cache

from app.ai.intelligence.base import MeetingIntelligence
from app.ai.intelligence.prompts import (
    RAG_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_rag_user_prompt,
    build_user_prompt,
)
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def _client():
    from openai import OpenAI  # lazy import

    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        raise ServiceUnavailableError(
            "OPENAI_API_KEY is not configured; cannot use the OpenAI LLM provider."
        )
    return OpenAI(api_key=settings.OPENAI_API_KEY)


class OpenAILLMProvider:
    def generate_intelligence(self, transcript_text: str) -> MeetingIntelligence:
        from openai import OpenAIError  # lazy import

        settings = get_settings()
        try:
            completion = _client().beta.chat.completions.parse(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(transcript_text)},
                ],
                response_format=MeetingIntelligence,  # structured output guarantee
                temperature=0.2,  # low -> factual, less creative drift
            )
        except OpenAIError as exc:
            raise ServiceUnavailableError("OpenAI intelligence request failed.") from exc

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            # Extremely rare (refusal); treat as a transient failure to retry.
            raise ServiceUnavailableError("OpenAI returned no parsable intelligence.")
        logger.info(
            "openai_intelligence_done",
            decisions=len(parsed.decisions),
            action_items=len(parsed.action_items),
        )
        return parsed

    def answer_with_context(self, *, question: str, context: str) -> str:
        from openai import OpenAIError  # lazy import

        settings = get_settings()
        try:
            completion = _client().chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": RAG_SYSTEM_PROMPT},
                    {"role": "user", "content": build_rag_user_prompt(question, context)},
                ],
                temperature=0.2,
            )
        except OpenAIError as exc:
            raise ServiceUnavailableError("OpenAI chat request failed.") from exc

        answer = completion.choices[0].message.content or ""
        logger.info("openai_answer_done", answer_chars=len(answer))
        return answer.strip()
