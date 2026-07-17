"""Diarization backend selection (cached per process)."""

from functools import lru_cache

from app.ai.diarization.base import DiarizationProvider
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def get_diarization_provider() -> DiarizationProvider:
    """Resolve the diarizer. 'auto' degrades to disabled when no HF_TOKEN is
    present — the platform never hard-fails just because diarization isn't
    set up."""
    settings = get_settings()
    provider = settings.DIARIZATION_PROVIDER

    if provider == "stub":
        from app.ai.diarization.stub_diarizer import StubDiarizer

        return StubDiarizer()

    if provider == "disabled":
        from app.ai.diarization.null_diarizer import NullDiarizer

        return NullDiarizer()

    # auto
    if settings.HF_TOKEN:
        from app.ai.diarization.pyannote_diarizer import PyannoteDiarizer

        return PyannoteDiarizer()

    logger.info("diarization_auto_disabled", reason="no_hf_token")
    from app.ai.diarization.null_diarizer import NullDiarizer

    return NullDiarizer()
