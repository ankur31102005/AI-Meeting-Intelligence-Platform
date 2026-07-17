"""Speech-to-text providers (Strategy Pattern).

`get_transcription_provider()` returns the backend chosen by settings:
    local  -> faster-whisper (free, offline)
    openai -> OpenAI Whisper API (paid, fast)
    stub   -> deterministic fake (tests / CI / pipeline smoke checks)

Everything upstream depends only on the `TranscriptionProvider` interface.
"""

from app.ai.transcription.base import (
    TranscriptionProvider,
    TranscriptionResult,
    TranscriptSegmentData,
)
from app.ai.transcription.factory import get_transcription_provider

__all__ = [
    "TranscriptionProvider",
    "TranscriptionResult",
    "TranscriptSegmentData",
    "get_transcription_provider",
]
