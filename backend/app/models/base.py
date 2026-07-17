"""
Shared model building blocks: mixins + portable column types.

Mixins follow composition-over-inheritance: each model declares exactly the
behaviors it needs (UUID PK, timestamps, soft delete) instead of inheriting
a fat "BaseModel" with columns half the tables don't want.

Portability note: columns use PostgreSQL-native types in production (JSONB)
via `with_variant`, while remaining creatable on SQLite — which is what lets
the model test-suite run in-memory without Docker.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# JSONB on PostgreSQL (binary, indexable with GIN), plain JSON elsewhere.
JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class UUIDPrimaryKeyMixin:
    """UUID primary key, generated app-side (in Python, at flush time).

    App-side (not DB-side) generation means no database round-trip or
    server extension is needed to mint IDs — after a flush (even before
    commit) the ID is usable, e.g. as a Celery task argument. UUIDs also
    aren't enumerable (/meetings/1, /2, ...), unlike serial integers.
    """

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """created_at / updated_at maintained by the database server.

    `server_default=func.now()` (not a Python default): the DB clock is the
    single source of truth, so rows inserted by raw SQL, other services, or
    migrations still get correct timestamps.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Soft delete: rows are flagged, not destroyed.

    SaaS reality — users delete things by accident, auditors want history,
    and hard deletes cascade destructively. Repositories filter
    `deleted_at IS NULL` by default; hard deletion stays an explicit,
    admin-only operation.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = datetime.now(UTC)

    def restore(self) -> None:
        self.deleted_at = None
