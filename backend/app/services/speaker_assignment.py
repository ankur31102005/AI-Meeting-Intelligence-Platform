"""
Map diarization turns onto transcript segments (pure functions, no DB).

Whisper and pyannote segment audio INDEPENDENTLY — their boundaries never line
up. So for each transcript segment we find which speaker was talking during it
by measuring TIME OVERLAP: the speaker whose turns overlap the segment most
wins. A segment with no overlap (silence, music) stays unassigned (None).

Keeping this as plain functions over plain data makes the tricky bit — the
overlap math — exhaustively unit-testable without a database or ML models.
"""

from collections import defaultdict

from app.ai.diarization.base import SpeakerTurn


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """Overlap duration of two intervals (0 if disjoint)."""
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def assign_speaker_label(
    segment_start: float, segment_end: float, turns: list[SpeakerTurn]
) -> str | None:
    """Label whose turns overlap [segment_start, segment_end] the MOST.

    Overlap is accumulated PER LABEL (a speaker may have several short turns
    inside one long segment), then the max wins. None when nothing overlaps.
    """
    totals: dict[str, float] = defaultdict(float)
    for turn in turns:
        ov = _overlap(segment_start, segment_end, turn.start, turn.end)
        if ov > 0:
            totals[turn.speaker_label] += ov
    if not totals:
        return None
    # max by overlap; ties broken by label for determinism.
    return max(totals, key=lambda label: (totals[label], label))


def assign_speakers_to_segments(
    segments: list[tuple[float, float]], turns: list[SpeakerTurn]
) -> list[str | None]:
    """Vectorized convenience: one label (or None) per (start, end) segment."""
    return [assign_speaker_label(start, end, turns) for start, end in segments]
