"""
Meeting intelligence: run the LLM over a transcript and persist the results.

Split from the pipeline task so it's independently testable (fake LLM, real
DB) and reusable (a future "regenerate insights" endpoint calls the same
analyze_and_store). READ paths live in MeetingService (no LLM needed there).

Persistence maps the single MeetingIntelligence object onto three tables:
    full/executive_summary -> Summary rows
    discussion/decision/risk/open_question/follow_up -> Insight rows
    action_items -> ActionItem rows
and is IDEMPOTENT — a re-run deletes the prior analysis first, so reprocessing
replaces rather than duplicates.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.ai.intelligence.base import LLMProvider
from app.ai.intelligence.schema import MeetingIntelligence
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import ActionItem, Insight, Meeting, Summary
from app.models.enums import (
    ActionItemPriority,
    InsightType,
    SummaryType,
)
from app.repositories.intelligence_repository import (
    ActionItemRepository,
    InsightRepository,
    SummaryRepository,
)
from app.repositories.transcript_repository import TranscriptRepository
from app.services.transcript_formatter import format_transcript

logger = get_logger(__name__)

# Which MeetingIntelligence list-field maps to which InsightType.
_INSIGHT_MAP: list[tuple[str, InsightType]] = [
    ("discussion_points", InsightType.DISCUSSION_POINT),
    ("decisions", InsightType.DECISION),
    ("risks", InsightType.RISK),
    ("open_questions", InsightType.OPEN_QUESTION),
    ("follow_ups", InsightType.FOLLOW_UP),
]


class IntelligenceService:
    def __init__(self, db: Session, llm: LLMProvider) -> None:
        self.db = db
        self.llm = llm
        self.transcripts = TranscriptRepository(db)
        self.summaries = SummaryRepository(db)
        self.insights = InsightRepository(db)
        self.action_items = ActionItemRepository(db)
        self.settings = get_settings()

    def analyze_and_store(self, meeting: Meeting) -> MeetingIntelligence:
        segments = self.transcripts.list_for_meeting(meeting.id, with_speaker=True)
        transcript_text = format_transcript(
            segments, max_chars=self.settings.LLM_MAX_TRANSCRIPT_CHARS
        )
        intel = self.llm.generate_intelligence(transcript_text)
        self._persist(meeting, intel)
        return intel

    # ------------------------------------------------------------------
    def _persist(self, meeting: Meeting, intel: MeetingIntelligence) -> None:
        model_name = self.settings.OPENAI_MODEL if self.settings.LLM_PROVIDER == "openai" else self.settings.LLM_PROVIDER

        # Idempotent: clear any prior analysis first.
        self.summaries.delete_for_meeting(meeting.id)
        self.insights.delete_for_meeting(meeting.id)
        self.action_items.delete_for_meeting(meeting.id)
        self.db.flush()

        self.db.add_all(
            [
                Summary(
                    meeting_id=meeting.id,
                    summary_type=SummaryType.FULL,
                    content=intel.full_summary,
                    model_used=model_name,
                ),
                Summary(
                    meeting_id=meeting.id,
                    summary_type=SummaryType.EXECUTIVE,
                    content=intel.executive_summary,
                    model_used=model_name,
                ),
            ]
        )

        for field_name, insight_type in _INSIGHT_MAP:
            for content in getattr(intel, field_name):
                self.db.add(
                    Insight(
                        meeting_id=meeting.id,
                        insight_type=insight_type,
                        content=content,
                    )
                )

        for item in intel.action_items:
            self.db.add(
                ActionItem(
                    meeting_id=meeting.id,
                    description=item.description,
                    assignee_name=item.assignee_name,
                    due_date=self._parse_date(item.due_date),
                    priority=ActionItemPriority(item.priority),
                )
            )

        self.db.flush()
        logger.info(
            "intelligence_persisted",
            meeting_id=str(meeting.id),
            insights=sum(len(getattr(intel, f)) for f, _ in _INSIGHT_MAP),
            action_items=len(intel.action_items),
        )

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        """Best-effort ISO date parse. A malformed date from the LLM must not
        crash the pipeline — we drop it to null rather than fail the meeting."""
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            logger.warning("action_item_bad_date", value=value)
            return None
