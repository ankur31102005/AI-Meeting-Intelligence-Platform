"""RAG + chat models: EmbeddingChunk, ChatSession, ChatMessage.

EmbeddingChunk is the Postgres-side TWIN of each ChromaDB vector. Postgres
owns the relational truth (which meeting, which time range); Chroma owns the
math (vector similarity). `chroma_id` is the bridge — meeting deletion uses
these rows to clean up Chroma, preventing orphaned vectors from leaking
deleted meetings into future chat answers.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONVariant, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ChatRole, enum_column

if TYPE_CHECKING:
    from app.models.meeting import Meeting
    from app.models.user import User


class EmbeddingChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "embedding_chunks"
    __table_args__ = (
        UniqueConstraint("meeting_id", "chunk_index", name="chunk_position"),
    )

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The document ID inside ChromaDB — the cross-store link.
    chroma_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # Chunk text duplicated here deliberately: citations render from Postgres
    # in one query, no Chroma round-trip on every chat message.
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    meeting: Mapped["Meeting"] = relationship(back_populates="embedding_chunks")


class ChatSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL meeting_id = cross-meeting chat ("search all my meetings").
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="New chat")

    user: Mapped["User"] = relationship()
    meeting: Mapped["Meeting | None"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        passive_deletes=True,
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[ChatRole] = mapped_column(enum_column(ChatRole, "chat_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Citations as JSON (display-only, never queried relationally):
    # [{"meeting_id": "...", "segment_id": "...", "timestamp": 734.2, "text": "..."}]
    citations: Mapped[list | None] = mapped_column(JSONVariant, nullable=True)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
