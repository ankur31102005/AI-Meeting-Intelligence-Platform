"""Transcription via the OpenAI Whisper API.

`verbose_json` returns per-segment timings. The API has no local model to
load, but it DOES upload the audio to OpenAI — a data-residency tradeoff the
operator opts into via TRANSCRIPTION_PROVIDER=openai.
"""

from app.ai.transcription.base import TranscriptionResult, TranscriptSegmentData
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


class OpenAIWhisperTranscriber:
    def __init__(self) -> None:
        from openai import OpenAI  # lazy import

        settings = get_settings()
        if not settings.OPENAI_API_KEY:
            raise ServiceUnavailableError(
                "OPENAI_API_KEY is not configured; cannot use the OpenAI "
                "transcription provider."
            )
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        from openai import OpenAIError  # lazy import

        try:
            with open(audio_path, "rb") as audio_file:
                resp = self._client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
        except OpenAIError as exc:
            raise ServiceUnavailableError(
                "OpenAI transcription request failed."
            ) from exc

        segments = [
            TranscriptSegmentData(
                text=seg["text"].strip(),
                start=round(seg["start"], 3),
                end=round(seg["end"], 3),
                # Whisper API returns avg_logprob; leave confidence None if
                # absent rather than inventing a number.
                confidence=None,
            )
            for seg in (resp.segments or [])
            if seg["text"].strip()
        ]
        logger.info("openai_transcribe_done", segments=len(segments))
        return TranscriptionResult(
            segments=segments,
            language=getattr(resp, "language", None),
            duration=getattr(resp, "duration", None),
        )
