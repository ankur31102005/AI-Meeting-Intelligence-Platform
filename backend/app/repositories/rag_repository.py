"""RAG data access: embedding chunks (Postgres twin of Chroma) + chat."""

import uuid

from sqlalchemy import delete, select

from app.models import ChatMessage, ChatSession, EmbeddingChunk
from app.repositories.base import BaseRepository


class EmbeddingChunkRepository(BaseRepository[EmbeddingChunk]):
    model = EmbeddingChunk

    def delete_for_meeting(self, meeting_id: uuid.UUID) -> None:
        self.db.execute(
            delete(EmbeddingChunk).where(EmbeddingChunk.meeting_id == meeting_id)
        )

    def bulk_add(self, chunks: list[EmbeddingChunk]) -> None:
        self.db.bulk_save_objects(chunks)
        self.db.flush()

    def get_many_by_chroma_ids(self, chroma_ids: list[str]) -> dict[str, EmbeddingChunk]:
        """Fetch chunks by their Chroma ids, keyed for O(1) citation lookup."""
        if not chroma_ids:
            return {}
        rows = self.db.scalars(
            select(EmbeddingChunk).where(EmbeddingChunk.chroma_id.in_(chroma_ids))
        ).all()
        return {row.chroma_id: row for row in rows}


class ChatSessionRepository(BaseRepository[ChatSession]):
    model = ChatSession

    def get_for_user(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> ChatSession | None:
        return self.db.scalars(
            select(ChatSession).where(
                ChatSession.id == session_id, ChatSession.user_id == user_id
            )
        ).first()

    def list_for_user(self, user_id: uuid.UUID) -> list[ChatSession]:
        return list(
            self.db.scalars(
                select(ChatSession)
                .where(ChatSession.user_id == user_id)
                .order_by(ChatSession.created_at.desc())
            ).all()
        )


class ChatMessageRepository(BaseRepository[ChatMessage]):
    model = ChatMessage

    def list_for_session(self, session_id: uuid.UUID) -> list[ChatMessage]:
        return list(
            self.db.scalars(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at)
            ).all()
        )
