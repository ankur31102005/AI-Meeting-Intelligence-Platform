"""
Format transcript segments into speaker-attributed plain text for the LLM.

Turning rows into "Ankur: ...\nSPEAKER_01: ..." gives the model the
attribution it needs to assign action items to the right person. Consecutive
segments from the SAME speaker are merged into one line so the model sees
coherent turns instead of choppy fragments.

Truncation: transcripts beyond `max_chars` are cut with a marker (cost +
context-window guard). Proper long-meeting handling (map-reduce) is a later
enhancement — the truncation is explicit, never silent.
"""

from collections.abc import Sequence


class _HasSpeakerAndText:
    """Structural hint: a TranscriptSegment with .text and .speaker.label."""

    text: str
    speaker: object | None


def format_transcript(segments: Sequence, *, max_chars: int) -> str:
    lines: list[str] = []
    current_label: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            speaker = current_label or "Unknown"
            lines.append(f"{speaker}: {' '.join(buffer)}")

    for seg in segments:
        label = seg.speaker.label if seg.speaker is not None else "Unknown"
        if label != current_label:
            flush()
            buffer = []
            current_label = label
        buffer.append(seg.text.strip())
    flush()

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[... transcript truncated ...]"
    return text
