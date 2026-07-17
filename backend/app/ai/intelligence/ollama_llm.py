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

import json
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


def _schema_instruction() -> str:
    schema = json.dumps(MeetingIntelligence.model_json_schema())
    return (
        "Return ONLY a JSON object (no prose, no markdown fences) that conforms "
        f"exactly to this JSON schema:\n{schema}"
    )


class OllamaLLMProvider:
    def generate_intelligence(self, transcript_text: str) -> MeetingIntelligence:
        settings = get_settings()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + _schema_instruction()},
            {"role": "user", "content": build_user_prompt(transcript_text)},
        ]
        content = self._chat(settings.OLLAMA_MODEL, messages, json_mode=True)

        try:
            return MeetingIntelligence.model_validate_json(content)
        except Exception:
            # One stricter retry — small local models occasionally wrap JSON
            # in prose or fences.
            logger.warning("ollama_json_retry")
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {"role": "user", "content": "That was not valid JSON. Return ONLY the JSON object."}
            )
            content = self._chat(settings.OLLAMA_MODEL, messages, json_mode=True)
            try:
                return MeetingIntelligence.model_validate_json(content)
            except Exception as exc:
                raise UnprocessableError(
                    "The local model did not return valid structured output. "
                    "Try a larger Ollama model (e.g. llama3.1)."
                ) from exc

    def answer_with_context(self, *, question: str, context: str) -> str:
        settings = get_settings()
        messages = [
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": build_rag_user_prompt(question, context)},
        ]
        return self._chat(settings.OLLAMA_MODEL, messages, json_mode=False)

    # ------------------------------------------------------------------
    def _chat(self, model: str, messages: list[dict], *, json_mode: bool) -> str:
        from openai import OpenAIError

        kwargs = {"model": model, "messages": messages, "temperature": 0.2}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            completion = _client().chat.completions.create(**kwargs)
        except OpenAIError as exc:
            raise ServiceUnavailableError(
                "Could not reach Ollama. Is it installed and running "
                "(ollama serve), and the model pulled?"
            ) from exc
        return (completion.choices[0].message.content or "").strip()
