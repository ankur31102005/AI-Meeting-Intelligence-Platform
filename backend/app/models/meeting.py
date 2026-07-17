"""Meeting (pipeline aggregate root) + File (object-storage pointers).

The `status` column is the pipeline's state machine — Celery tasks advance
it stage by stage, the frontend polls it for progress, and `error_message`
plus FAILED status make every breakdown diagnosable and retryable.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import (
    JSONVariant,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)
from app.models.enums import FileType, MeetingStatus, enum_column

if TYPE_CHECKING:
    from app.models.intelligence import ActionItem, Insight, Summary
    from app.models.organization import Organization
    from app.models.rag import ChatSession, EmbeddingChunk
    from app.models.transcript import Speaker, TranscriptSegment
    from app.models.user import User


class Meeting(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "meetings"
    __table_args__ = (
        # The dashboard's hottest query: "this org's meetings, newest first".
        Index("ix_meetings_org_recent", "organization_id", "meeting_date"),
        CheckConstraint("duration_seconds >= 0", name="duration_non_negative"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    meeting_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[MeetingStatus] = mapped_column(
        enum_column(MeetingStatus, "meeting_status"),
        nullable=False,
        default=MeetingStatus.UPLOADED,
        index=True,
    )
    # Populated only when status=FAILED — the "why" for reprocess decisions.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON array of strings. JSONB + GIN index (added in search module)
    # gives tag containment queries without a join table.
    tags: Mapped[list] = mapped_column(JSONVariant, nullable=False, default=list)

    organization: Mapped["Organization"] = relationship(back_populates="meetings")
    owner: Mapped["User"] = relationship()
    files: Mapped[list["File"]] = relationship(
        back_populates="meeting", passive_deletes=True, cascade="all, delete-orphan"
    )
    speakers: Mapped[list["Speaker"]] = relationship(
        back_populates="meeting", passive_deletes=True, cascade="all, delete-orphan"
    )
    segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="meeting",
        passive_deletes=True,
        cascade="all, delete-orphan",
        order_by="TranscriptSegment.segment_index",
    )
    summaries: Mapped[list["Summary"]] = relationship(
        back_populates="meeting", passive_deletes=True, cascade="all, delete-orphan"
    )
    insights: Mapped[list["Insight"]] = relationship(
        back_populates="meeting", passive_deletes=True, cascade="all, delete-orphan"
    )
    action_items: Mapped[list["ActionItem"]] = relationship(
        back_populates="meeting", passive_deletes=True, cascade="all, delete-orphan"
    )
    embedding_chunks: Mapped[list["EmbeddingChunk"]] = relationship(
        back_populates="meeting", passive_deletes=True, cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="meeting", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Meeting {self.id} title={self.title!r} status={self.status.value}>"


class File(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "files"
    __table_args__ = (CheckConstraint("size_bytes >= 0", name="size_non_negative"),)

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_type: Mapped[FileType] = mapped_column(
        enum_column(FileType, "file_type"), nullable=False
    )
    # Object-storage key (MinIO/S3 path) — bytes NEVER live in Postgres.
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    meeting: Mapped["Meeting"] = relationship(back_populates="files")
