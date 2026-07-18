"""
Chat (RAG) + semantic search endpoints.

Thin adapters over RAGService. The service is built via DI from the embedding
provider, vector store, and LLM — all overridable in tests with fakes, so
these endpoints are exercised end-to-end without ChromaDB or an API key.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.ai.embeddings import EmbeddingProvider, get_embedding_provider
from app.ai.intelligence import get_llm_provider
from app.ai.intelligence.base import LLMProvider
from app.ai.vectorstore import VectorStore, get_vector_store
from app.core.dependencies import CurrentUser, DbSession
from app.schemas.chat import (
    AskRequest,
    ChatMessageResponse,
    ChatSessionDetailResponse,
    ChatSessionResponse,
    CreateSessionRequest,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from app.schemas.common import APIResponse
from app.services.rag_service import RAGService

router = APIRouter(tags=["Chat & Search"])


def get_rag_service(
    db: DbSession,
    embedder: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    vector_store: Annotated[VectorStore, Depends(get_vector_store)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> RAGService:
    return RAGService(db, embedder, vector_store, llm)


RagSvc = Annotated[RAGService, Depends(get_rag_service)]


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
@router.post("/search", summary="Semantic search across meetings")
def semantic_search(
    body: SearchRequest, svc: RagSvc, user: CurrentUser
) -> APIResponse[SearchResponse]:
    matches = svc.search(
        organization_id=user.organization_id,
        query=body.query,
        meeting_id=body.meeting_id,
        top_k=body.top_k,
    )
    results = [
        SearchResult(
            meeting_id=m.metadata.get("meeting_id"),
            chunk_index=m.metadata.get("chunk_index"),
            start_time=m.metadata.get("start_time"),
            end_time=m.metadata.get("end_time"),
            score=round(m.score, 4),
            text=m.document,
        )
        for m in matches
    ]
    return APIResponse(data=SearchResponse(query=body.query, results=results))


# ---------------------------------------------------------------------------
# Chat sessions
# ---------------------------------------------------------------------------
@router.post(
    "/chat/sessions",
    status_code=status.HTTP_201_CREATED,
    summary="Start a chat session (optionally scoped to one meeting)",
)
def create_session(
    body: CreateSessionRequest, svc: RagSvc, user: CurrentUser
) -> APIResponse[ChatSessionResponse]:
    session = svc.create_session(
        user_id=user.id,
        organization_id=user.organization_id,
        meeting_id=body.meeting_id,
        title=body.title,
    )
    return APIResponse(data=ChatSessionResponse.model_validate(session))


@router.get("/chat/sessions", summary="List your chat sessions")
def list_sessions(svc: RagSvc, user: CurrentUser) -> APIResponse[list[ChatSessionResponse]]:
    sessions = svc.list_sessions(user_id=user.id)
    return APIResponse(data=[ChatSessionResponse.model_validate(s) for s in sessions])


@router.get("/chat/sessions/{session_id}", summary="Session with full history")
def get_session(
    session_id: uuid.UUID, svc: RagSvc, user: CurrentUser
) -> APIResponse[ChatSessionDetailResponse]:
    session, messages = svc.get_session_with_messages(
        session_id=session_id, user_id=user.id
    )
    return APIResponse(
        data=ChatSessionDetailResponse(
            id=session.id,
            title=session.title,
            meeting_id=session.meeting_id,
            created_at=session.created_at,
            messages=[ChatMessageResponse.model_validate(m) for m in messages],
        )
    )


@router.delete("/chat/sessions/{session_id}", summary="Delete a chat session")
def delete_session(
    session_id: uuid.UUID, svc: RagSvc, user: CurrentUser
) -> APIResponse[dict]:
    svc.delete_session(session_id=session_id, user_id=user.id)
    return APIResponse(data={"message": "Conversation deleted"})


@router.post(
    "/chat/sessions/{session_id}/messages",
    summary="Ask a question (RAG answer with citations)",
)
def ask(
    session_id: uuid.UUID, body: AskRequest, svc: RagSvc, user: CurrentUser
) -> APIResponse[ChatMessageResponse]:
    answer = svc.ask(
        session_id=session_id,
        user_id=user.id,
        organization_id=user.organization_id,
        question=body.question,
    )
    return APIResponse(data=ChatMessageResponse.model_validate(answer))
