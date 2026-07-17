"""Meeting intelligence via LLM (Provider Pattern).

`get_llm_provider()` returns the configured backend:
    openai -> OpenAI structured outputs (paid, high quality)
    stub   -> deterministic fake (tests / CI / smoke checks, no API key)
    ollama -> reserved for a future local-LLM provider

Everything upstream depends only on the `LLMProvider` interface and the
`MeetingIntelligence` schema — swapping models never touches business logic.
"""

from app.ai.intelligence.base import LLMProvider
from app.ai.intelligence.factory import get_llm_provider
from app.ai.intelligence.schema import (
    ActionItemData,
    MeetingIntelligence,
)

__all__ = [
    "ActionItemData",
    "LLMProvider",
    "MeetingIntelligence",
    "get_llm_provider",
]
