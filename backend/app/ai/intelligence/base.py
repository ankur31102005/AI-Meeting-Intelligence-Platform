"""LLM provider interface.

A provider turns a plain-text transcript into a validated
`MeetingIntelligence`. The transcript arrives already formatted with speaker
labels (services/transcript_formatter) so the model has attribution context.
"""

from typing import Protocol, runtime_checkable

from app.ai.intelligence.schema import MeetingIntelligence


@runtime_checkable
class LLMProvider(Protocol):
    def generate_intelligence(self, transcript_text: str) -> MeetingIntelligence:
        """Extract structured intelligence from a transcript. Always called
        from a worker (LLM latency is seconds); implementations must return a
        schema-valid object or raise."""
        ...

    def answer_with_context(self, *, question: str, context: str) -> str:
        """RAG generation: answer `question` grounded in `context` (retrieved
        transcript chunks). Implementations must instruct the model to answer
        ONLY from the context and say so when the answer isn't present."""
        ...
