"""Real speaker diarization via pyannote.audio.

The pretrained pipeline is EXPENSIVE to build (downloads + loads a neural
model), so it is constructed once per process and cached. `pyannote.audio` and
`torch` are imported lazily inside _load_pipeline so importing this module
never forces the (large) dependency onto processes that don't diarize.
"""

from functools import lru_cache

from app.ai.diarization.base import DiarizationResult, SpeakerTurn
from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def _load_pipeline():
    from pyannote.audio import Pipeline  # lazy: heavy import (torch)

    settings = get_settings()
    if not settings.HF_TOKEN:
        raise ServiceUnavailableError(
            "HF_TOKEN is required for pyannote diarization."
        )
    logger.info("pyannote_pipeline_loading", pipeline=settings.PYANNOTE_PIPELINE)
    pipeline = Pipeline.from_pretrained(
        settings.PYANNOTE_PIPELINE, use_auth_token=settings.HF_TOKEN
    )

    # Use GPU when the whisper config indicates one (shared device policy).
    if settings.WHISPER_DEVICE == "cuda":
        import torch

        pipeline.to(torch.device("cuda"))
    return pipeline


class PyannoteDiarizer:
    def diarize(self, audio_path: str) -> DiarizationResult:
        pipeline = _load_pipeline()
        annotation = pipeline(audio_path)

        turns = [
            SpeakerTurn(
                start=round(segment.start, 3),
                end=round(segment.end, 3),
                speaker_label=str(label),
            )
            for segment, _, label in annotation.itertracks(yield_label=True)
        ]
        logger.info(
            "pyannote_diarize_done",
            turns=len(turns),
            speakers=len({t.speaker_label for t in turns}),
        )
        return DiarizationResult(turns=turns)
