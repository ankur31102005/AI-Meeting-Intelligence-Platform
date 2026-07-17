"""Transcript + processing-status response contracts."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import MeetingStatus


class TranscriptSegmentResponse(BaseModel):
    id: uuid.UUID
    segment_index: int
    text: str
    start_time: float
    end_time: float
    confidence: float | None
    speaker_id: uuid.UUID | None
    speaker_label: str | None  # "Ankur" / "SPEAKER_00" / None if unassigned

    @classmethod
    def from_segment(cls, segment) -> "TranscriptSegmentResponse":
        return cls(
            id=segment.id,
            segment_index=segment.segment_index,
            text=segment.text,
            start_time=segment.start_time,
            end_time=segment.end_time,
            confidence=segment.confidence,
            speaker_id=segment.speaker_id,
            speaker_label=segment.speaker.label if segment.speaker else None,
        )


class TranscriptResponse(BaseModel):
    meeting_id: uuid.UUID
    status: MeetingStatus
    duration_seconds: int | None
    segment_count: int
    segments: list[TranscriptSegmentResponse]


class ProcessingStatusResponse(BaseModel):
    """Lightweight shape the frontend polls while the pipeline runs."""

    model_config = ConfigDict(from_attributes=True)

    meeting_id: uuid.UUID
    status: MeetingStatus
    error_message: str | None
    duration_seconds: int | None
    updated_at: datetime
