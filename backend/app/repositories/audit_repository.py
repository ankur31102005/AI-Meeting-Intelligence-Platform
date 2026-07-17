"""Audit log writes — append-only by design (no update/delete methods)."""

import uuid

from app.models import AuditLog
from app.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    model = AuditLog

    def record(
        self,
        *,
        action: str,
        organization_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """One security-relevant event. Rides in the caller's transaction so
        the event commits atomically WITH the action it describes."""
        return self.add(
            AuditLog(
                action=action,
                organization_id=organization_id,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                event_metadata=metadata,
                ip_address=ip_address,
            )
        )
