"""No-op diarizer — the graceful-degradation default.

Returned when diarization is disabled or unconfigured (no HF_TOKEN). It lets
the pipeline run the diarization STAGE unconditionally without branching:
the stage always calls diarize(); this one simply yields no speakers.
"""

from app.ai.diarization.base import DiarizationResult
from app.core.logging import get_logger

logger = get_logger(__name__)


class NullDiarizer:
    def diarize(self, audio_path: str) -> DiarizationResult:
        logger.info("diarization_skipped", reason="disabled_or_no_hf_token")
        return DiarizationResult(turns=[])
