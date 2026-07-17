"""Unit tests for the overlap-matching logic — the tricky core of M6."""

from app.ai.diarization.base import DiarizationResult, SpeakerTurn
from app.services.speaker_assignment import (
    assign_speaker_label,
    assign_speakers_to_segments,
)


def turn(start, end, label):
    return SpeakerTurn(start=start, end=end, speaker_label=label)


class TestAssignSingleSegment:
    def test_segment_fully_inside_one_turn(self):
        turns = [turn(0, 10, "SPEAKER_00")]
        assert assign_speaker_label(2, 5, turns) == "SPEAKER_00"

    def test_segment_with_no_overlap_is_none(self):
        turns = [turn(0, 3, "SPEAKER_00")]
        assert assign_speaker_label(5, 8, turns) is None

    def test_no_turns_at_all_is_none(self):
        assert assign_speaker_label(0, 5, []) is None

    def test_picks_speaker_with_most_overlap(self):
        # Segment [4, 10]: SPEAKER_00 overlaps [4,5]=1s, SPEAKER_01 [5,10]=5s.
        turns = [turn(0, 5, "SPEAKER_00"), turn(5, 12, "SPEAKER_01")]
        assert assign_speaker_label(4, 10, turns) == "SPEAKER_01"

    def test_accumulates_overlap_across_multiple_turns_of_same_speaker(self):
        # SPEAKER_00 has two short turns (total 4s) vs SPEAKER_01 one 3s turn.
        turns = [
            turn(0, 2, "SPEAKER_00"),
            turn(2, 5, "SPEAKER_01"),
            turn(5, 7, "SPEAKER_00"),
        ]
        # Segment [0, 7]: S00 = 2+2 = 4s, S01 = 3s -> S00 wins.
        assert assign_speaker_label(0, 7, turns) == "SPEAKER_00"

    def test_tie_broken_deterministically_by_label(self):
        # Equal 2s overlap each; lexicographically larger label wins (stable).
        turns = [turn(0, 2, "SPEAKER_00"), turn(2, 4, "SPEAKER_01")]
        result = assign_speaker_label(0, 4, turns)
        assert result == "SPEAKER_01"
        # Deterministic across repeated calls.
        assert all(assign_speaker_label(0, 4, turns) == result for _ in range(5))

    def test_touching_boundaries_do_not_count_as_overlap(self):
        # Turn ends exactly where segment starts -> zero overlap.
        turns = [turn(0, 5, "SPEAKER_00")]
        assert assign_speaker_label(5, 8, turns) is None


class TestAssignManySegments:
    def test_maps_each_segment(self):
        turns = [turn(0, 5, "SPEAKER_00"), turn(5, 10, "SPEAKER_01")]
        segments = [(0, 4), (6, 9), (100, 200)]
        assert assign_speakers_to_segments(segments, turns) == [
            "SPEAKER_00",
            "SPEAKER_01",
            None,  # far past all turns
        ]


class TestDiarizationResultHelpers:
    def test_unique_labels_in_first_appearance_order(self):
        result = DiarizationResult(
            turns=[
                turn(0, 2, "SPEAKER_01"),
                turn(2, 4, "SPEAKER_00"),
                turn(4, 6, "SPEAKER_01"),  # repeat
            ]
        )
        assert result.speaker_labels == ["SPEAKER_01", "SPEAKER_00"]

    def test_is_empty(self):
        assert DiarizationResult(turns=[]).is_empty
        assert not DiarizationResult(turns=[turn(0, 1, "S0")]).is_empty
