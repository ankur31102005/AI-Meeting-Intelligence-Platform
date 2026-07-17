"""Chat + search request/response contracts."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ChatRole


class CreateSessionRequest(BaseModel):
    # null meeting_id => cross-meeting chat over the whole org.
    meeting_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=500)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class Citation(BaseModel):
    excerpt: int
    meeting_id: str | None
    chunk_index: int | None
    start_time: float | None
    end_time: float | None
    score: float
    text: str


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: ChatRole
    content: str
    citations: list[Citation] | None
    created_at: datetime


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    meeting_id: uuid.UUID | None
    created_at: datetime


class ChatSessionDetailResponse(ChatSessionResponse):
    messages: list[ChatMessageResponse]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    meeting_id: uuid.UUID | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    meeting_id: str | None
    chunk_index: int | None
    start_time: float | None
    end_time: float | None
    score: float
    text: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
