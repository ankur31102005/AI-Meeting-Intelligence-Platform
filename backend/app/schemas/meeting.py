"""Meeting request/response contracts."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import FileType, MeetingStatus


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_type: FileType
    original_filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime


class MeetingResponse(BaseModel):
    """Summary shape used in list views (no heavy children)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    status: MeetingStatus
    meeting_date: datetime | None
    duration_seconds: int | None
    tags: list[str]
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class MeetingDetailResponse(MeetingResponse):
    """Detail shape — includes attached files."""

    files: list[FileResponse]


class MeetingUpdateRequest(BaseModel):
    """All fields optional — PATCH semantics (only sent fields change)."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=5000)
    tags: list[str] | None = Field(default=None, max_length=50)


class MeetingDownloadResponse(BaseModel):
    """A time-limited link the client uses to fetch the media directly."""

    download_url: str
    expires_in_seconds: int
