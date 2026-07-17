"""Speaker diarization providers (Strategy Pattern + graceful degradation).

"Who spoke when" is an OPTIONAL enrichment: the platform is fully usable
without it (transcript still works). `get_diarization_provider()` returns:
    auto     -> PyannoteDiarizer if HF_TOKEN set, else NullDiarizer
    stub     -> StubDiarizer (tests / smoke checks)
    disabled -> NullDiarizer (no-op)

NullDiarizer returns zero speakers, so downstream code has ONE code path:
it always gets a DiarizationResult, sometimes empty.
"""

from app.ai.diarization.base import (
    DiarizationProvider,
    DiarizationResult,
    SpeakerTurn,
)
from app.ai.diarization.factory import get_diarization_provider

__all__ = [
    "DiarizationProvider",
    "DiarizationResult",
    "SpeakerTurn",
    "get_diarization_provider",
]
