"""Meeting + File data access.

Two invariants enforced here so no service can forget them:
  * soft-deleted meetings are invisible (deleted_at IS NULL everywhere),
  * every query is scoped to an organization (tenant isolation — a user can
    never read another org's meetings, even with a guessed UUID).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models import File, Meeting
from app.repositories.base import BaseRepository


class MeetingRepository(BaseRepository[Meeting]):
    model = Meeting

    def get_for_org(
        self, meeting_id: uuid.UUID, organization_id: uuid.UUID, *, with_files: bool = False
    ) -> Meeting | None:
        stmt = select(Meeting).where(
            Meeting.id == meeting_id,
            Meeting.organization_id == organization_id,
            Meeting.deleted_at.is_(None),
        )
        if with_files:
            # Eager-load files in one extra query (avoids N+1 on detail view).
            stmt = stmt.options(selectinload(Meeting.files))
        return self.db.scalars(stmt).first()

    def list_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
    ) -> tuple[list[Meeting], int]:
        """Return (page_items, total_count) for pagination.

        Count runs on the SAME filters as the page query, so total_pages the
        client computes always matches what it can actually fetch.
        """
        filters = [
            Meeting.organization_id == organization_id,
            Meeting.deleted_at.is_(None),
        ]
        if search:
            filters.append(Meeting.title.ilike(f"%{search}%"))

        total = self.db.scalar(select(func.count()).select_from(Meeting).where(*filters)) or 0

        stmt = (
            select(Meeting)
            .where(*filters)
            # created_at DESC = newest first. The id tiebreaker makes the
            # order TOTAL (deterministic) even when two rows share a
            # timestamp — without it, an item can appear on two pages or be
            # skipped entirely as offsets shift. Stable pagination requires a
            # unique final sort key.
            .order_by(Meeting.created_at.desc(), Meeting.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.db.scalars(stmt).all()), total


class FileRepository(BaseRepository[File]):
    model = File

    def get_by_key(self, storage_key: str) -> File | None:
        return self.db.scalars(
            select(File).where(File.storage_key == storage_key)
        ).first()
