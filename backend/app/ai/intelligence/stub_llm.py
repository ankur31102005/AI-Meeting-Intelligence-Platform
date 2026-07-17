"""Deterministic fake LLM — drives the analyze stage in tests/CI without an
API key or cost. Returns a believable, fixed MeetingIntelligence so
assertions are stable."""

from app.ai.intelligence.base import MeetingIntelligence
from app.ai.intelligence.schema import ActionItemData
from app.core.logging import get_logger

logger = get_logger(__name__)


class StubLLMProvider:
    def generate_intelligence(self, transcript_text: str) -> MeetingIntelligence:
        logger.info("stub_intelligence_done", transcript_chars=len(transcript_text))
        return MeetingIntelligence(
            full_summary=(
                "The team met to plan the quarterly release. They aligned on a "
                "Friday ship date and assigned backend ownership."
            ),
            executive_summary="Team agreed to ship the release on Friday; Ankur owns the backend.",
            discussion_points=[
                "Quarterly release plan",
                "Backend ownership and responsibilities",
            ],
            decisions=["Ship the release on Friday"],
            risks=["Tight timeline before the Friday deadline"],
            open_questions=["Who will handle the frontend deployment?"],
            follow_ups=["Schedule a pre-release review on Thursday"],
            action_items=[
                ActionItemData(
                    description="Prepare and finalize the backend for release",
                    assignee_name="Ankur",
                    due_date="2026-07-24",
                    priority="high",
                ),
                ActionItemData(
                    description="Draft the release notes",
                    assignee_name=None,
                    due_date=None,
                    priority="medium",
                ),
            ],
        )

    def answer_with_context(self, *, question: str, context: str) -> str:
        # Deterministic, and clearly grounded in the provided context so tests
        # can assert the RAG plumbing (retrieval -> context -> answer) works.
        logger.info("stub_answer_done", question_chars=len(question))
        if not context.strip():
            return "I don't have that information from the meeting."
        first_line = context.strip().splitlines()[0]
        return f"Based on the meeting: {first_line}"
