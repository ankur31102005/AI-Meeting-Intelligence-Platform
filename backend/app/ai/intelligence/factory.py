"""LLM backend selection (cached per process)."""

from functools import lru_cache

from app.ai.intelligence.base import LLMProvider
from app.core.config import get_settings


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Return the configured LLM provider. Local imports keep heavy/optional
    SDKs out of processes that don't use them."""
    provider = get_settings().LLM_PROVIDER

    if provider == "stub":
        from app.ai.intelligence.stub_llm import StubLLMProvider

        return StubLLMProvider()

    if provider == "ollama":
        from app.ai.intelligence.ollama_llm import OllamaLLMProvider

        return OllamaLLMProvider()

    from app.ai.intelligence.openai_llm import OpenAILLMProvider

    return OpenAILLMProvider()
