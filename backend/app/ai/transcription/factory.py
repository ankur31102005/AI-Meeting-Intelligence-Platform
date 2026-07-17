"""Transcription backend selection (one instance per process)."""

from functools import lru_cache

from app.ai.transcription.base import TranscriptionProvider
from app.core.config import get_settings


@lru_cache
def get_transcription_provider() -> TranscriptionProvider:
    """Return the configured transcriber. Imports are local so choosing
    'stub' never imports faster-whisper, and vice versa."""
    provider = get_settings().TRANSCRIPTION_PROVIDER

    if provider == "openai":
        from app.ai.transcription.openai_whisper import OpenAIWhisperTranscriber

        return OpenAIWhisperTranscriber()

    if provider == "stub":
        from app.ai.transcription.stub import StubTranscriber

        return StubTranscriber()

    from app.ai.transcription.local_whisper import LocalWhisperTranscriber

    return LocalWhisperTranscriber()
