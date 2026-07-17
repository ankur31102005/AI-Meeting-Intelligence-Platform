"""
Transcript -> retrieval chunks (pure functions).

Segments are too small to embed well individually (a 3-second utterance has
little context). So consecutive segments are PACKED into ~CHUNK_TARGET_CHARS
chunks, each keeping the time span [first_seg.start, last_seg.end] for
citations ("jump to 12:34"). A small character OVERLAP between chunks keeps
context from being lost exactly at a boundary.

Pure + data-only, so the packing logic is exhaustively unit-testable without a
DB or models.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentInput:
    text: str
    start: float
    end: float
    speaker_label: str | None = None


@dataclass(frozen=True)
class Chunk:
    text: str
    start: float
    end: float
    index: int


def chunk_segments(
    segments: list[SegmentInput], *, target_chars: int, overlap_chars: int
) -> list[Chunk]:
    """Pack consecutive segments into chunks near `target_chars`.

    A speaker prefix is included so the embedded text carries attribution
    ("Ankur: ..."). `overlap_chars` of the previous chunk's tail is prepended
    to the next chunk to preserve cross-boundary context.
    """
    if not segments:
        return []

    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_len = 0
    start_time = segments[0].start
    end_time = segments[0].end
    carry = ""  # overlap text carried from the previous chunk

    def emit() -> None:
        nonlocal carry
        if not buf:
            return
        body = " ".join(buf)
        text = f"{carry}{body}".strip()
        chunks.append(Chunk(text=text, start=start_time, end=end_time, index=len(chunks)))
        # Carry the tail of THIS chunk into the next one.
        carry = (body[-overlap_chars:] + " ") if overlap_chars and len(body) > overlap_chars else ""

    for seg in segments:
        piece = seg.text.strip()
        if seg.speaker_label:
            piece = f"{seg.speaker_label}: {piece}"

        if buf and buf_len + len(piece) > target_chars:
            emit()
            buf = []
            buf_len = 0
            start_time = seg.start
        if not buf:
            start_time = seg.start
        buf.append(piece)
        buf_len += len(piece) + 1
        end_time = seg.end

    emit()
    return chunks
