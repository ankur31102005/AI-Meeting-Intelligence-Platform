"""Intelligence (summary / insight / action item) response contracts."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ActionItemPriority,
    ActionItemStatus,
    InsightType,
    SummaryType,
)


class SummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary_type: SummaryType
    content: str
    model_used: str


class InsightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    insight_type: InsightType
    content: str
    timestamp_reference: float | None


class ActionItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    assignee_name: str | None
    assignee_user_id: uuid.UUID | None
    due_date: date | None
    priority: ActionItemPriority
    status: ActionItemStatus
    created_at: datetime


class ActionItemUpdateRequest(BaseModel):
    """PATCH semantics — only sent fields change."""

    status: ActionItemStatus | None = None
    assignee_user_id: uuid.UUID | None = None
    priority: ActionItemPriority | None = None
    description: str | None = Field(default=None, min_length=1, max_length=2000)


class IntelligenceResponse(BaseModel):
    """Combined view: everything the LLM produced for a meeting."""

    meeting_id: uuid.UUID
    summaries: list[SummaryResponse]
    insights: list[InsightResponse]
    action_items: list[ActionItemResponse]
