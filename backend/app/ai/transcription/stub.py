"""Deterministic fake transcriber.

Purpose: exercise the ENTIRE pipeline (upload -> ffmpeg -> transcribe ->
persist -> status) in tests, CI, and manual smoke checks WITHOUT downloading a
Whisper model or paying for the API. It returns the same believable transcript
for any input, so assertions are stable.
"""

from app.ai.audio import get_media_duration
from app.ai.transcription.base import TranscriptionResult, TranscriptSegmentData
from app.core.logging import get_logger

logger = get_logger(__name__)

_FAKE_SEGMENTS = [
    ("Hello everyone, thanks for joining today's meeting.", 0.0, 3.5),
    ("Let's start with the quarterly release plan.", 3.5, 7.0),
    ("We agreed to ship on Friday and Ankur owns the backend.", 7.0, 11.2),
]


class StubTranscriber:
    def transcribe(self, audio_path: str) -> TranscriptionResult:
        # Probe the real duration when ffmpeg is available (keeps the stubbed
        # run realistic); fall back to the last segment's end otherwise.
        duration = get_media_duration(audio_path) or _FAKE_SEGMENTS[-1][2]
        segments = [
            TranscriptSegmentData(text=text, start=start, end=end, confidence=0.95)
            for text, start, end in _FAKE_SEGMENTS
        ]
        logger.info("stub_transcribe_done", segments=len(segments))
        return TranscriptionResult(segments=segments, language="en", duration=duration)
