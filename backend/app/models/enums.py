"""
Domain enums - the closed vocabularies of the platform.

`enum.StrEnum` (Python 3.11+) means values serialize naturally in JSON
responses and comparisons work against plain strings. Column definitions
store the VALUE ("admin"), not the NAME ("ADMIN"), via `values_callable`
in `enum_column()` - so the database stays readable in raw SQL.
"""

import enum

from sqlalchemy import Enum as SAEnum


def enum_column(enum_cls: type[enum.Enum], type_name: str) -> SAEnum:
    """Build a SQLAlchemy Enum that stores lowercase values.

    On PostgreSQL this creates a native ENUM type (`type_name`); on SQLite it
    falls back to VARCHAR + CHECK - same behavior, test-friendly.
    """
    return SAEnum(
        enum_cls,
        name=type_name,
        values_callable=lambda e: [member.value for member in e],
    )


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    EMPLOYEE = "employee"


class MeetingStatus(enum.StrEnum):
    """Processing pipeline state machine (one status per stage so the
    frontend can render precise progress)."""

    UPLOADED = "uploaded"
    EXTRACTING = "extracting"      # ffmpeg: video -> audio
    TRANSCRIBING = "transcribing"  # whisper
    DIARIZING = "diarizing"        # pyannote (skipped without HF_TOKEN)
    ANALYZING = "analyzing"        # LLM: summary / insights / action items
    EMBEDDING = "embedding"        # chunk + vectorize into ChromaDB
    COMPLETED = "completed"
    FAILED = "failed"


class FileType(enum.StrEnum):
    ORIGINAL = "original"                # as uploaded (mp3/mp4/wav)
    EXTRACTED_AUDIO = "extracted_audio"  # ffmpeg output used by the pipeline
    EXPORT_PDF = "export_pdf"
    EXPORT_DOCX = "export_docx"


class SummaryType(enum.StrEnum):
    FULL = "full"
    EXECUTIVE = "executive"


class InsightType(enum.StrEnum):
    DISCUSSION_POINT = "discussion_point"
    DECISION = "decision"
    RISK = "risk"
    OPEN_QUESTION = "open_question"
    FOLLOW_UP = "follow_up"


class ActionItemPriority(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionItemStatus(enum.StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class ChatRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
