"""Refresh-token and password-reset-token data access.

Everything is looked up BY HASH — raw tokens never reach this layer.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.models import PasswordResetToken, RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Fetch regardless of state — the SERVICE distinguishes between
        unknown / revoked / expired, because a revoked-token hit is a
        security signal (reuse detection), not a simple miss."""
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return self.db.scalars(stmt).first()

    def revoke(self, token: RefreshToken) -> None:
        token.revoked_at = datetime.now(UTC)
        self.db.flush()

    def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Kill every active session for a user (password reset, theft
        response, admin lock-out). Returns how many were revoked."""
        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        result = self.db.execute(stmt)
        self.db.flush()
        return result.rowcount


class PasswordResetTokenRepository(BaseRepository[PasswordResetToken]):
    model = PasswordResetToken

    def get_valid_by_hash(self, token_hash: str) -> PasswordResetToken | None:
        """Valid = exists, unused, unexpired. Single-use is enforced by the
        used_at filter here plus the stamp in mark_used()."""
        now = datetime.now(UTC)
        stmt = select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        return self.db.scalars(stmt).first()

    def mark_used(self, token: PasswordResetToken) -> None:
        token.used_at = datetime.now(UTC)
        self.db.flush()
