"""Unit tests for the meeting processing state machine."""

import pytest

from app.core.exceptions import ConflictError
from app.models.enums import MeetingStatus as S
from app.services import pipeline_state


class TestAllowedTransitions:
    @pytest.mark.parametrize(
        "current,target",
        [
            (S.UPLOADED, S.EXTRACTING),
            (S.EXTRACTING, S.TRANSCRIBING),
            (S.TRANSCRIBING, S.COMPLETED),
            (S.COMPLETED, S.EXTRACTING),   # reprocess
            (S.FAILED, S.EXTRACTING),      # retry after failure
            (S.EXTRACTING, S.FAILED),      # failure from active stage
        ],
    )
    def test_allowed(self, current, target):
        assert pipeline_state.can_transition(current, target)

    @pytest.mark.parametrize(
        "current,target",
        [
            (S.UPLOADED, S.COMPLETED),      # can't skip stages
            (S.COMPLETED, S.TRANSCRIBING),  # can't jump back mid-pipeline
            (S.TRANSCRIBING, S.UPLOADED),   # no going back to start
            (S.COMPLETED, S.COMPLETED),     # no self-loop
        ],
    )
    def test_forbidden(self, current, target):
        assert not pipeline_state.can_transition(current, target)

    def test_assert_raises_on_illegal(self):
        with pytest.raises(ConflictError, match="Illegal"):
            pipeline_state.assert_transition(S.COMPLETED, S.TRANSCRIBING)

    def test_assert_passes_on_legal(self):
        pipeline_state.assert_transition(S.UPLOADED, S.EXTRACTING)  # no raise
