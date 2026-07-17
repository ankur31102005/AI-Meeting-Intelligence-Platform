"""Speaker + TranscriptSegment — the transcript as queryable rows.

One row per utterance (NOT one giant text blob) because every later feature
needs granularity: speaker attribution, timestamp citations in chat answers,
RAG chunking, and "jump to 12:34" navigation in the UI.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class Speaker(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "speakers"
    __table_args__ = (
        # Pyannote labels are unique within one meeting, not globally.
        UniqueConstraint("meeting_id", "diarization_label", name="speaker_label_per_meeting"),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Raw label from pyannote ("SPEAKER_00") — immutable machine identity.
    diarization_label: Mapped[str] = mapped_column(String(50), nullable=False)
    # Human-assigned name ("Ankur") — NULL until someone renames. Kept
    # separate from the label so renaming never breaks segment linkage.
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    meeting: Mapped["Meeting"] = relationship(back_populates="speakers")
    segments: Mapped[list["TranscriptSegment"]] = relationship(back_populates="speaker")

    @property
    def label(self) -> str:
        """What the UI shows: the human name if set, else the raw label."""
        return self.display_name or self.diarization_label


class TranscriptSegment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        # Exactly one segment per position within a meeting.
        UniqueConstraint("meeting_id", "segment_index", name="segment_position"),
        # Reading a transcript in order is THE access pattern — one composite
        # index serves both the WHERE and the ORDER BY.
        Index("ix_segments_meeting_order", "meeting_id", "segment_index"),
        CheckConstraint("end_time >= start_time", name="times_ordered"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    # SET NULL: deleting/merging a speaker must never destroy transcript text.
    speaker_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("speakers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)  # seconds
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..1
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)

    meeting: Mapped["Meeting"] = relationship(back_populates="segments")
    speaker: Mapped["Speaker | None"] = relationship(back_populates="segments")
