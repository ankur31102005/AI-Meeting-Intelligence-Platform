"""Generic repository base — shared plumbing for all repositories."""

import uuid

from sqlalchemy.orm import Session

from app.core.database import Base


class BaseRepository[ModelT: Base]:
    """Minimal common surface. Subclasses set `model` and add intent-named
    query methods; they inherit the boring parts.

    Deliberately small: a fat generic base (filter_by anything, update
    anything) would turn repositories back into leaky query builders —
    the opposite of the pattern's point.
    """

    model: type[ModelT]

    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return self.db.get(self.model, entity_id)

    def add(self, entity: ModelT) -> ModelT:
        """Stage + flush (assigns defaults/IDs). Commit stays with the service."""
        self.db.add(entity)
        self.db.flush()
        return entity

    def delete(self, entity: ModelT) -> None:
        """HARD delete — reserved for admin/cleanup paths. User-facing
        deletion goes through each model's soft_delete()."""
        self.db.delete(entity)
        self.db.flush()
