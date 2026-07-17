"""Organization — the multi-tenancy root.

Every user and meeting hangs off an organization, so converting this
single-org deployment into a true multi-tenant SaaS later is a query-filter
change, not a schema migration.
"""

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:  # imports for type hints only — avoids circular imports
    from app.models.meeting import Meeting
    from app.models.user import User


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Children. passive_deletes=True: the DATABASE cascades (ON DELETE
    # CASCADE on the FK), SQLAlchemy doesn't emit per-row DELETEs.
    users: Mapped[list["User"]] = relationship(
        back_populates="organization", passive_deletes=True
    )
    meetings: Mapped[list["Meeting"]] = relationship(
        back_populates="organization", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"<Organization {self.id} name={self.name!r}>"
