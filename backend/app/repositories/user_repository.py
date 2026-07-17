"""User + Organization data access."""

from sqlalchemy import func, select

from app.models import Organization, User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        """Case-insensitive lookup — 'Ankur@x.com' and 'ankur@x.com' are the
        same account. Soft-deleted users are invisible to auth."""
        stmt = select(User).where(
            func.lower(User.email) == email.lower(),
            User.deleted_at.is_(None),
        )
        return self.db.scalars(stmt).first()

    def email_exists(self, email: str) -> bool:
        stmt = select(User.id).where(func.lower(User.email) == email.lower())
        return self.db.scalars(stmt).first() is not None


class OrganizationRepository(BaseRepository[Organization]):
    model = Organization
