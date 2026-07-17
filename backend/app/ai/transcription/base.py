"""Transcription interface + result value objects.

These dataclasses are the STABLE contract between "how we transcribe" (which
changes: local/openai/future) and "what we do with a transcript" (persist,
diarize, embed). Providers convert their engine-specific output into these
plain types so nothing downstream depends on faster-whisper or OpenAI shapes.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TranscriptSegmentData:
    """One utterance with timing. `confidence` is 0..1 or None when the
    engine doesn't report it."""

    text: str
    start: float          # seconds from the beginning
    end: float
    confidence: float | None = None


@dataclass(frozen=True)
class TranscriptionResult:
    segments: list[TranscriptSegmentData]
    language: str | None
    duration: float | None


@runtime_checkable
class TranscriptionProvider(Protocol):
    def transcribe(self, audio_path: str) -> TranscriptionResult:
        """Transcribe a prepared audio file (16 kHz mono WAV) into segments.
        Implementations may block for minutes — always called from a worker,
        never from a request handler."""
        ...
