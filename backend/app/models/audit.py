"""AuditLog — append-only trail of security-relevant actions.

Deliberate differences from every other table:
  * BIGSERIAL integer PK, not UUID: logs are high-volume and insert-hot;
    sequential ints keep the B-tree index compact and append-friendly.
  * FKs are SET NULL: deleting a user must never destroy the record THAT
    they were deleted (the log outlives its actors).
  * No update/delete paths will ever be written for it in the app.
"""

import uuid

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import JSONVariant, TimestampMixin


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        # "What happened in org X recently?" — the audit UI's main query.
        Index("ix_audit_org_time", "organization_id", "created_at"),
        Index("ix_audit_action", "action"),
    )

    # BigInteger on Postgres; plain Integer variant for SQLite test runs
    # (SQLite only autoincrements INTEGER primary keys).
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Dotted convention: "auth.login", "meeting.delete", "user.role_change"
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Attribute named event_metadata because `metadata` is reserved by
    # SQLAlchemy's Declarative API; the COLUMN is still called "metadata".
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSONVariant, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6-ready
