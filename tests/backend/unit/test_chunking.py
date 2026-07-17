"""Unit tests for transcript chunking (pure logic)."""

from app.services.chunking import SegmentInput, chunk_segments


def seg(text, start, end, label=None):
    return SegmentInput(text=text, start=start, end=end, speaker_label=label)


class TestChunking:
    def test_empty(self):
        assert chunk_segments([], target_chars=100, overlap_chars=10) == []

    def test_single_segment_one_chunk(self):
        chunks = chunk_segments([seg("Hello world", 0, 2)], target_chars=100, overlap_chars=0)
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world"
        assert chunks[0].start == 0
        assert chunks[0].end == 2
        assert chunks[0].index == 0

    def test_packs_until_target(self):
        # Three ~10-char segments, target 25 -> forces a split.
        segs = [seg("aaaaaaaa", 0, 1), seg("bbbbbbbb", 1, 2), seg("cccccccc", 2, 3)]
        chunks = chunk_segments(segs, target_chars=20, overlap_chars=0)
        assert len(chunks) >= 2
        # Time spans are contiguous and cover the input.
        assert chunks[0].start == 0
        assert chunks[-1].end == 3

    def test_speaker_prefix_included(self):
        chunks = chunk_segments(
            [seg("Hello", 0, 1, "Ankur")], target_chars=100, overlap_chars=0
        )
        assert chunks[0].text == "Ankur: Hello"

    def test_chunk_indices_are_sequential(self):
        segs = [seg("x" * 30, i, i + 1) for i in range(5)]
        chunks = chunk_segments(segs, target_chars=40, overlap_chars=0)
        assert [c.index for c in chunks] == list(range(len(chunks)))

    def test_time_spans_never_go_backwards(self):
        segs = [seg("word " * 20, i * 2, i * 2 + 2) for i in range(4)]
        chunks = chunk_segments(segs, target_chars=50, overlap_chars=10)
        for c in chunks:
            assert c.end >= c.start
