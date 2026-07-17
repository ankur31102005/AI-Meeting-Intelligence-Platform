"""Unit tests for transcript formatting (LLM input prep)."""

from dataclasses import dataclass

from app.services.transcript_formatter import format_transcript


@dataclass
class FakeSpeaker:
    label: str


@dataclass
class FakeSegment:
    text: str
    speaker: FakeSpeaker | None


def seg(text, label=None):
    return FakeSegment(text=text, speaker=FakeSpeaker(label) if label else None)


class TestFormatTranscript:
    def test_speaker_attribution(self):
        segments = [seg("Hello.", "Ankur"), seg("Hi there.", "SPEAKER_01")]
        out = format_transcript(segments, max_chars=10000)
        assert out == "Ankur: Hello.\nSPEAKER_01: Hi there."

    def test_consecutive_same_speaker_merged(self):
        segments = [
            seg("First part.", "Ankur"),
            seg("Second part.", "Ankur"),
            seg("Now me.", "Bob"),
        ]
        out = format_transcript(segments, max_chars=10000)
        # Ankur's two segments merge into one line.
        assert out == "Ankur: First part. Second part.\nBob: Now me."

    def test_unassigned_speaker_labeled_unknown(self):
        out = format_transcript([seg("Mystery voice.", None)], max_chars=10000)
        assert out == "Unknown: Mystery voice."

    def test_truncation_with_marker(self):
        segments = [seg("x" * 100, "A")]
        out = format_transcript(segments, max_chars=50)
        assert out.endswith("[... transcript truncated ...]")
        assert len(out) < 100

    def test_empty_transcript(self):
        assert format_transcript([], max_chars=100) == ""
