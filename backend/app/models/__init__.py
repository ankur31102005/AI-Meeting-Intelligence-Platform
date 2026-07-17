"""
ORM models package.

Importing THIS package registers every table on `Base.metadata` — which is
exactly what Alembic's env.py and the test suite rely on. If a new model
file is added but not imported here, migrations will silently miss it, so
keep this list exhaustive.
"""

from app.models.audit import AuditLog
from app.models.intelligence import ActionItem, Insight, Summary
from app.models.meeting import File, Meeting
from app.models.organization import Organization
from app.models.rag import ChatMessage, ChatSession, EmbeddingChunk
from app.models.transcript import Speaker, TranscriptSegment
from app.models.user import ApiKey, PasswordResetToken, RefreshToken, User

__all__ = [
    "ActionItem",
    "ApiKey",
    "AuditLog",
    "ChatMessage",
    "ChatSession",
    "EmbeddingChunk",
    "File",
    "Insight",
    "Meeting",
    "Organization",
    "PasswordResetToken",
    "RefreshToken",
    "Speaker",
    "Summary",
    "TranscriptSegment",
    "User",
]
