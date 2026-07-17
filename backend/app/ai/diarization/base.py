"""Diarization interface + value objects.

A diarizer answers "who spoke when" as a list of SpeakerTurns — time ranges
each tagged with a raw label ("SPEAKER_00"). Mapping those turns onto
transcript segments happens later (services/speaker_assignment.py); providers
only produce the turns.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SpeakerTurn:
    """A continuous stretch of speech attributed to one speaker."""

    start: float          # seconds
    end: float
    speaker_label: str    # raw diarizer label, e.g. "SPEAKER_00"


@dataclass(frozen=True)
class DiarizationResult:
    turns: list[SpeakerTurn]

    @property
    def speaker_labels(self) -> list[str]:
        """Unique labels, in first-appearance order (stable Speaker rows)."""
        seen: dict[str, None] = {}
        for turn in self.turns:
            seen.setdefault(turn.speaker_label, None)
        return list(seen)

    @property
    def is_empty(self) -> bool:
        return not self.turns


@runtime_checkable
class DiarizationProvider(Protocol):
    def diarize(self, audio_path: str) -> DiarizationResult:
        """Analyze a prepared audio file into speaker turns. May return an
        empty result (e.g. the NullDiarizer, or truly single-speaker audio)."""
        ...
