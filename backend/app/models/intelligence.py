"""LLM-generated outputs: Summary, Insight, ActionItem.

Every row records `model_used` (where relevant) so output quality is
auditable — "which model wrote this summary?" is answerable forever.
"""

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    ActionItemPriority,
    ActionItemStatus,
    InsightType,
    SummaryType,
    enum_column,
)

if TYPE_CHECKING:
    from app.models.meeting import Meeting
    from app.models.user import User


class Summary(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "summaries"
    __table_args__ = (
        # One summary per type per meeting — reprocessing REPLACES, never
        # duplicates (upsert in the service layer).
        UniqueConstraint("meeting_id", "summary_type", name="one_per_type"),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary_type: Mapped[SummaryType] = mapped_column(
        enum_column(SummaryType, "summary_type"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)

    meeting: Mapped["Meeting"] = relationship(back_populates="summaries")


class Insight(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "insights"
    __table_args__ = (
        # "Show me all DECISIONS from meeting X" — the standard query.
        Index("ix_insights_meeting_type", "meeting_id", "insight_type"),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    insight_type: Mapped[InsightType] = mapped_column(
        enum_column(InsightType, "insight_type"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Seconds into the meeting where this was said — powers "jump to moment".
    timestamp_reference: Mapped[float | None] = mapped_column(Float, nullable=True)

    meeting: Mapped["Meeting"] = relationship(back_populates="insights")


class ActionItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "action_items"
    __table_args__ = (
        Index("ix_action_items_assignee_status", "assignee_user_id", "status"),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Two-phase assignee: the LLM extracts a NAME from the transcript
    # ("Ankur will fix the deploy"); a human later maps it to a real account.
    # Kept separate because LLM name-matching is fuzzy, humans are accountable.
    assignee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[ActionItemPriority] = mapped_column(
        enum_column(ActionItemPriority, "action_item_priority"),
        nullable=False,
        default=ActionItemPriority.MEDIUM,
    )
    status: Mapped[ActionItemStatus] = mapped_column(
        enum_column(ActionItemStatus, "action_item_status"),
        nullable=False,
        default=ActionItemStatus.OPEN,
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="action_items")
    assignee: Mapped["User | None"] = relationship()
