"""
Ollama LLM provider — free, local, no API key.

Reuses the `openai` SDK pointed at Ollama's OpenAI-COMPATIBLE endpoint
(http://<host>:11434/v1), so no new dependency is required. Ollama runs the
model on the user's machine; from the Dockerized worker we reach it via
host.docker.internal.

Structured output: rather than rely on json_schema support (varies by Ollama
version), we use JSON mode + an explicit schema in the prompt, then validate
with Pydantic. A single retry with a stricter instruction covers the
occasional malformed-JSON response small local models produce.
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
from app.core.exceptions import ServiceUnavailableError, UnprocessableError
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def _client():
    from openai import OpenAI  # reuse the OpenAI SDK against Ollama's /v1 API

    settings = get_settings()
    # api_key is required by the SDK but ignored by Ollama.
    return OpenAI(base_url=settings.OLLAMA_BASE_URL, api_key="ollama")


def _extract_json(text: str) -> str:
    """Pull the JSON object out of a model response.

    Small local models often wrap the JSON in prose or ```json fences, or add
    a trailing sentence — all of which break strict parsing. We strip fences
    and, failing that, slice from the first '{' to the last '}'. This recovers
    the payload the model DID produce instead of failing the whole meeting.
    """
    t = text.strip()
    if t.startswith("```"):
        # ```json\n{...}\n```  ->  {...}
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t
        t = t[4:] if t.lstrip().startswith("json") else t
        t = t.strip().strip("`").strip()
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start : end + 1]
    return t


class OllamaLLMProvider:
    def generate_intelligence(self, transcript_text: str) -> MeetingIntelligence:
        settings = get_settings()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(transcript_text)},
        ]
        # Ollama's NATIVE structured output: pass the JSON SCHEMA via
        # response_format, which CONSTRAINS the model to emit a valid instance
        # of the schema. (Putting the schema in the prompt made small models
        # echo the schema back instead of filling it.) A couple of retries
        # cover the rare invalid response.
        schema = MeetingIntelligence.model_json_schema()
        last = ""
        for attempt in range(3):
            last = self._chat(settings.OLLAMA_MODEL, messages, schema=schema)
            try:
                return MeetingIntelligence.model_validate_json(_extract_json(last))
            except Exception:
                logger.warning("ollama_json_retry", attempt=attempt)

        logger.error("ollama_structured_output_failed", sample=last[:300])
        raise UnprocessableError(
            "The local model did not return valid structured output. "
            "Try a larger/stronger Ollama model (e.g. qwen2.5 or llama3.1)."
        )

    def answer_with_context(self, *, question: str, context: str) -> str:
        settings = get_settings()
        messages = [
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": build_rag_user_prompt(question, context)},
        ]
        return self._chat(settings.OLLAMA_MODEL, messages)

    # ------------------------------------------------------------------
    def _chat(self, model: str, messages: list[dict], *, schema: dict | None = None) -> str:
        """Chat completion. When `schema` is given, use Ollama's structured
        output (json_schema response_format) to force valid JSON."""
        from openai import OpenAIError

        kwargs: dict = {"model": model, "messages": messages, "temperature": 0.2}
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "meeting_intelligence", "schema": schema},
            }
        try:
            completion = _client().chat.completions.create(**kwargs)
        except OpenAIError as exc:
            raise ServiceUnavailableError(
                "Could not reach Ollama. Is it installed and running "
                "(ollama serve), and the model pulled?"
            ) from exc
        return (completion.choices[0].message.content or "").strip()
