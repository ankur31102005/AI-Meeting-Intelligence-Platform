"""Local transcription via faster-whisper (CTranslate2).

The model is EXPENSIVE to construct (loads weights into RAM), so it is built
once per worker process and cached. `faster_whisper` is imported lazily inside
__init__ so importing this module never forces the dependency on processes
that don't transcribe (the API, the stub-configured worker).

faster-whisper reports an average log-probability per segment; we map it to a
0..1 confidence with exp() so the stored value matches the DB CHECK constraint
and is comparable across providers.
"""

import math
from functools import lru_cache

from app.ai.transcription.base import TranscriptionResult, TranscriptSegmentData
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def _load_model():
    """Build (and cache) the WhisperModel for this process."""
    from faster_whisper import WhisperModel  # lazy: heavy import

    settings = get_settings()
    logger.info(
        "whisper_model_loading",
        size=settings.WHISPER_MODEL_SIZE,
        device=settings.WHISPER_DEVICE,
        compute_type=settings.WHISPER_COMPUTE_TYPE,
    )
    return WhisperModel(
        settings.WHISPER_MODEL_SIZE,
        device=settings.WHISPER_DEVICE,
        compute_type=settings.WHISPER_COMPUTE_TYPE,
    )


class LocalWhisperTranscriber:
    def transcribe(self, audio_path: str) -> TranscriptionResult:
        model = _load_model()
        # segments is a lazy generator — iterating it does the actual work.
        segments_iter, info = model.transcribe(audio_path, beam_size=5)

        segments = [
            TranscriptSegmentData(
                text=seg.text.strip(),
                start=round(seg.start, 3),
                end=round(seg.end, 3),
                confidence=self._to_confidence(seg.avg_logprob),
            )
            for seg in segments_iter
            if seg.text.strip()
        ]
        logger.info(
            "whisper_transcribe_done",
            segments=len(segments),
            language=info.language,
            duration=info.duration,
        )
        return TranscriptionResult(
            segments=segments, language=info.language, duration=info.duration
        )

    @staticmethod
    def _to_confidence(avg_logprob: float | None) -> float | None:
        if avg_logprob is None:
            return None
        # exp(logprob) -> probability, clamped into [0, 1] for the DB check.
        return max(0.0, min(1.0, math.exp(avg_logprob)))
