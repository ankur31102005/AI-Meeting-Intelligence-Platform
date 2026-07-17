"""
RAG service: semantic search + "chat with your meetings".

Retrieval-Augmented Generation flow for a question:
    1. embed the question,
    2. retrieve the top-K most similar chunks from the vector store,
       ALWAYS filtered by organization_id (tenant isolation) and optionally
       by meeting_id (chat scoped to one meeting),
    3. build a context block from those chunks,
    4. ask the LLM to answer using ONLY that context,
    5. persist the Q + answer, attaching CITATIONS (which chunk / meeting /
       timestamp each answer drew from) so the UI can link back to the moment.

The model never sees the whole corpus — only the retrieved slice — which is
what makes RAG cheap, current, and grounded.
"""

import uuid

from sqlalchemy.orm import Session

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.intelligence.base import LLMProvider
from app.ai.vectorstore.base import VectorMatch, VectorStore
from app.core.config import get_settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.models import ChatMessage, ChatSession
from app.models.enums import ChatRole
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.rag_repository import (
    ChatMessageRepository,
    ChatSessionRepository,
)

logger = get_logger(__name__)


class RAGService:
    def __init__(
        self,
        db: Session,
        embedder: EmbeddingProvider,
        vector_store: VectorStore,
        llm: LLMProvider,
    ) -> None:
        self.db = db
        self.embedder = embedder
        self.vector_store = vector_store
        self.llm = llm
        self.meetings = MeetingRepository(db)
        self.sessions = ChatSessionRepository(db)
        self.messages = ChatMessageRepository(db)
        self.settings = get_settings()

    # ------------------------------------------------------------------
    # Semantic search
    # ------------------------------------------------------------------
    def search(
        self,
        *,
        organization_id: uuid.UUID,
        query: str,
        meeting_id: uuid.UUID | None = None,
        top_k: int | None = None,
    ) -> list[VectorMatch]:
        """Org-scoped semantic search over meeting chunks."""
        where: dict = {"organization_id": str(organization_id)}
        if meeting_id is not None:
            where["meeting_id"] = str(meeting_id)
        embedding = self.embedder.embed_query(query)
        return self.vector_store.query(
            embedding=embedding, top_k=top_k or self.settings.RAG_TOP_K, where=where
        )

    # ------------------------------------------------------------------
    # Chat sessions
    # ------------------------------------------------------------------
    def create_session(
        self,
        *,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        meeting_id: uuid.UUID | None,
        title: str | None,
    ) -> ChatSession:
        # A meeting-scoped session must reference a meeting the caller owns.
        if meeting_id is not None:
            if self.meetings.get_for_org(meeting_id, organization_id) is None:
                raise NotFoundError("Meeting not found")
        session = ChatSession(
            user_id=user_id,
            meeting_id=meeting_id,
            title=title or "New chat",
        )
        self.db.add(session)
        self.db.commit()
        return session

    def list_sessions(self, *, user_id: uuid.UUID) -> list[ChatSession]:
        return self.sessions.list_for_user(user_id)

    def get_session_with_messages(
        self, *, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[ChatSession, list[ChatMessage]]:
        session = self.sessions.get_for_user(session_id, user_id)
        if session is None:
            raise NotFoundError("Chat session not found")
        return session, self.messages.list_for_session(session_id)

    # ------------------------------------------------------------------
    # Ask (the RAG loop)
    # ------------------------------------------------------------------
    def ask(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        question: str,
    ) -> ChatMessage:
        session = self.sessions.get_for_user(session_id, user_id)
        if session is None:
            raise NotFoundError("Chat session not found")
        if not question.strip():
            raise BadRequestError("Question cannot be empty")

        # 1-2. Retrieve context (scoped to the session's meeting if any).
        matches = self.search(
            organization_id=organization_id,
            query=question,
            meeting_id=session.meeting_id,
        )

        # 3. Build the context block + citation list from the matches.
        context, citations = self._build_context_and_citations(matches)

        # 4. Generate a grounded answer.
        answer = self.llm.answer_with_context(question=question, context=context)

        # 5. Persist the exchange (user turn, then assistant turn w/ citations).
        self.db.add(
            ChatMessage(session_id=session.id, role=ChatRole.USER, content=question)
        )
        assistant_msg = ChatMessage(
            session_id=session.id,
            role=ChatRole.ASSISTANT,
            content=answer,
            citations=citations or None,
        )
        self.db.add(assistant_msg)
        # First user question becomes the session title (nice UX default).
        if session.title == "New chat":
            session.title = question[:80]
        self.db.commit()

        logger.info(
            "rag_answer",
            session_id=str(session.id),
            retrieved=len(matches),
            citations=len(citations),
        )
        return assistant_msg

    # ------------------------------------------------------------------
    @staticmethod
    def _build_context_and_citations(
        matches: list[VectorMatch],
    ) -> tuple[str, list[dict]]:
        """Format retrieved chunks into an LLM context block, and a parallel
        citation list the UI renders as 'jump to 12:34' links."""
        context_lines: list[str] = []
        citations: list[dict] = []
        for i, m in enumerate(matches, start=1):
            start = m.metadata.get("start_time")
            context_lines.append(f"[Excerpt {i}] {m.document}")
            citations.append(
                {
                    "excerpt": i,
                    "meeting_id": m.metadata.get("meeting_id"),
                    "chunk_index": m.metadata.get("chunk_index"),
                    "start_time": start,
                    "end_time": m.metadata.get("end_time"),
                    "score": round(m.score, 4),
                    "text": m.document,
                }
            )
        return "\n\n".join(context_lines), citations
