"""
Meeting processing state machine.

Centralizing the allowed transitions here (instead of scattering status
assignments across tasks) means an illegal jump — e.g. COMPLETED straight back
to TRANSCRIBING, or advancing a FAILED meeting — is caught in ONE place. Each
pipeline stage calls `advance_to()`, which validates before mutating.

Allowed graph (M5 scope; diarize/analyze/embed stages slot in later):

    UPLOADED ─▶ EXTRACTING ─▶ TRANSCRIBING ─▶ COMPLETED
        │            │              │
        └────────────┴──────────────┴────────▶ FAILED   (from any active stage)

    FAILED / COMPLETED ─▶ EXTRACTING   (only via an explicit reprocess)
"""

from app.core.exceptions import ConflictError
from app.models.enums import MeetingStatus

# What each state is allowed to move to.
_ALLOWED: dict[MeetingStatus, set[MeetingStatus]] = {
    MeetingStatus.UPLOADED: {MeetingStatus.EXTRACTING, MeetingStatus.FAILED},
    MeetingStatus.EXTRACTING: {MeetingStatus.TRANSCRIBING, MeetingStatus.FAILED},
    # After transcription the pipeline goes to DIARIZING (M6). COMPLETED stays
    # reachable directly so a future config could skip diarization entirely.
    MeetingStatus.TRANSCRIBING: {
        MeetingStatus.DIARIZING,
        MeetingStatus.COMPLETED,
        MeetingStatus.FAILED,
    },
    # After diarization the pipeline runs LLM analysis (M7).
    MeetingStatus.DIARIZING: {
        MeetingStatus.ANALYZING,
        MeetingStatus.COMPLETED,
        MeetingStatus.FAILED,
    },
    # ANALYZING -> COMPLETED for now; M8 will insert EMBEDDING before COMPLETED.
    MeetingStatus.ANALYZING: {
        MeetingStatus.EMBEDDING,
        MeetingStatus.COMPLETED,
        MeetingStatus.FAILED,
    },
    MeetingStatus.EMBEDDING: {MeetingStatus.COMPLETED, MeetingStatus.FAILED},
    # Terminal states can only re-enter the pipeline through a reprocess.
    MeetingStatus.COMPLETED: {MeetingStatus.EXTRACTING},
    MeetingStatus.FAILED: {MeetingStatus.EXTRACTING},
}


def can_transition(current: MeetingStatus, target: MeetingStatus) -> bool:
    return target in _ALLOWED.get(current, set())


def assert_transition(current: MeetingStatus, target: MeetingStatus) -> None:
    """Raise ConflictError if `current -> target` is not permitted."""
    if not can_transition(current, target):
        raise ConflictError(
            f"Illegal meeting status transition: {current.value} -> {target.value}"
        )
