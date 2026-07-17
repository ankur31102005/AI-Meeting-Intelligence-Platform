"""Deterministic fake diarizer.

Splits the audio into alternating 2-speaker turns so the whole diarization +
speaker-assignment path can be tested/smoke-checked without pyannote or a GPU.
Turn boundaries are derived from the real audio duration when ffprobe is
available, so assignments line up with actual transcript timings.
"""

from app.ai.audio import get_media_duration
from app.ai.diarization.base import DiarizationResult, SpeakerTurn
from app.core.logging import get_logger

logger = get_logger(__name__)

_TURN_SECONDS = 3.5  # alternate speakers every ~3.5s


class StubDiarizer:
    def diarize(self, audio_path: str) -> DiarizationResult:
        duration = get_media_duration(audio_path) or 11.2
        turns: list[SpeakerTurn] = []
        t = 0.0
        i = 0
        while t < duration:
            end = min(t + _TURN_SECONDS, duration)
            turns.append(
                SpeakerTurn(start=t, end=end, speaker_label=f"SPEAKER_{i % 2:02d}")
            )
            t = end
            i += 1
        logger.info("stub_diarize_done", turns=len(turns))
        return DiarizationResult(turns=turns)
