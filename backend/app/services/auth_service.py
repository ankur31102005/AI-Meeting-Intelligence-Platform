"""
Authentication business logic.

Security decisions implemented here (each one is a real-world lesson):
  * Refresh token ROTATION: every /refresh burns the old token and issues a
    new one. A token can therefore be used exactly once.
  * REUSE DETECTION: if a burned (revoked) refresh token shows up again,
    someone is replaying a stolen token — we revoke ALL of the user's
    sessions and force re-login.
  * ANTI-ENUMERATION: login failures return the same message for "no such
    user" and "wrong password"; forgot-password always claims success.
    Attackers learn nothing about which emails exist.
  * One business operation = one transaction (commit here, nowhere else).
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import Organization, PasswordResetToken, RefreshToken, User
from app.models.enums import UserRole
from app.repositories.audit_repository import AuditRepository
from app.repositories.token_repository import (
    PasswordResetTokenRepository,
    RefreshTokenRepository,
)
from app.repositories.user_repository import OrganizationRepository, UserRepository
from app.schemas.auth import TokenResponse
from app.services.email import EmailSender

logger = get_logger(__name__)

_INVALID_CREDENTIALS = "Invalid email or password"  # noqa: S105 — user-facing message


def _as_utc(dt: datetime) -> datetime:
    """Normalize DB datetimes for comparison.

    PostgreSQL returns timezone-AWARE datetimes for TIMESTAMPTZ columns;
    SQLite (tests) returns NAIVE ones — and Python refuses to compare the
    two. All our stored times are UTC by convention, so a naive value is
    interpreted as UTC. Without this, `stored < now(UTC)` works in prod and
    crashes in tests (or vice versa) — a genuinely nasty class of bug.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class AuthService:
    def __init__(self, db: Session, email_sender: EmailSender) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.orgs = OrganizationRepository(db)
        self.refresh_tokens = RefreshTokenRepository(db)
        self.reset_tokens = PasswordResetTokenRepository(db)
        self.audit = AuditRepository(db)
        self.email_sender = email_sender
        self.settings = get_settings()

    # ------------------------------------------------------------------
    # Signup
    # ------------------------------------------------------------------
    def signup(
        self,
        *,
        email: str,
        password: str,
        full_name: str,
        organization_name: str,
        ip_address: str | None = None,
    ) -> User:
        """Create a workspace + its owning user (SaaS bootstrap model).

        The first user of an organization is its ADMIN — this solves the
        'who creates the first admin?' problem without seed scripts.
        Employees/managers are invited by an admin later (admin module).
        """
        if self.users.email_exists(email):
            raise ConflictError("An account with this email already exists")

        try:
            org = self.orgs.add(Organization(name=organization_name))
            user = self.users.add(
                User(
                    organization_id=org.id,
                    email=email.lower(),
                    password_hash=hash_password(password),
                    full_name=full_name,
                    role=UserRole.ADMIN,
                )
            )
            self.audit.record(
                action="auth.signup",
                organization_id=org.id,
                user_id=user.id,
                resource_type="user",
                resource_id=str(user.id),
                ip_address=ip_address,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()  # never leave a half-created org+user pair
            raise

        logger.info("user_signed_up", user_id=str(user.id), org_id=str(org.id))
        return user

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    def login(self, *, email: str, password: str, ip_address: str | None = None) -> TokenResponse:
        user = self.users.get_by_email(email)

        # Same error for unknown email AND wrong password (anti-enumeration).
        # NOTE: verify_password still runs its full cost when the user exists;
        # unknown-email requests return faster — acceptable here, closed in a
        # hardening pass with a dummy-hash comparison if timing matters.
        if user is None or not verify_password(password, user.password_hash):
            self._audit_and_commit(
                action="auth.login_failed",
                metadata={"email": email.lower()},
                ip_address=ip_address,
            )
            raise UnauthorizedError(_INVALID_CREDENTIALS)

        if not user.is_active:
            # Distinct from bad credentials: the password WAS right, but an
            # admin has deactivated the account. 403, not 401.
            raise ForbiddenError("Account is deactivated. Contact your administrator.")

        return self._issue_session(user, ip_address=ip_address, action="auth.login")

    # ------------------------------------------------------------------
    # Refresh (rotation + reuse detection)
    # ------------------------------------------------------------------
    def refresh(self, *, raw_refresh_token: str, ip_address: str | None = None) -> TokenResponse:
        row = self.refresh_tokens.get_by_hash(hash_token(raw_refresh_token))

        if row is None:
            raise UnauthorizedError("Invalid refresh token")

        if row.is_revoked:
            # REUSE DETECTED: this token was already rotated or logged out.
            # Someone (client bug or attacker) replayed it — nuke every
            # session for this user and force a fresh login.
            revoked = self.refresh_tokens.revoke_all_for_user(row.user_id)
            self._audit_and_commit(
                action="auth.refresh_reuse_detected",
                user_id=row.user_id,
                metadata={"sessions_revoked": revoked},
                ip_address=ip_address,
            )
            logger.warning(
                "refresh_token_reuse_detected",
                user_id=str(row.user_id),
                sessions_revoked=revoked,
            )
            raise UnauthorizedError("Session invalidated, please log in again")

        if _as_utc(row.expires_at) < datetime.now(UTC):
            raise UnauthorizedError("Refresh token has expired")

        user = self.users.get(row.user_id)
        if user is None or user.deleted_at is not None or not user.is_active:
            raise UnauthorizedError("Account is not available")

        # ROTATION: burn the old token in the same transaction that issues
        # the new one — there is never a moment with two live tokens.
        self.refresh_tokens.revoke(row)
        return self._issue_session(user, ip_address=ip_address, action="auth.refresh")

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------
    def logout(self, *, raw_refresh_token: str, ip_address: str | None = None) -> None:
        """Idempotent: logging out an unknown/already-revoked token is a
        no-op, not an error — the end state ('not logged in') is achieved."""
        row = self.refresh_tokens.get_by_hash(hash_token(raw_refresh_token))
        if row is not None and not row.is_revoked:
            self.refresh_tokens.revoke(row)
            self._audit_and_commit(
                action="auth.logout", user_id=row.user_id, ip_address=ip_address
            )

    # ------------------------------------------------------------------
    # Password reset
    # ------------------------------------------------------------------
    def forgot_password(self, *, email: str, ip_address: str | None = None) -> None:
        """ALWAYS appears to succeed — response never reveals whether the
        email exists (anti-enumeration). The email is only actually sent
        when there is a matching active account."""
        user = self.users.get_by_email(email)
        if user is None or not user.is_active:
            logger.info("password_reset_requested_unknown_email")
            return

        raw, token_hash = generate_opaque_token()
        self.reset_tokens.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(UTC)
                + timedelta(minutes=self.settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
            )
        )
        self._audit_and_commit(
            action="auth.password_reset_requested", user_id=user.id, ip_address=ip_address
        )
        # Sent AFTER commit: if the DB write failed we must not email a link
        # that points at a token which doesn't exist.
        reset_link = f"{self.settings.FRONTEND_URL}/reset-password?token={raw}"
        self.email_sender.send_password_reset(to_email=user.email, reset_link=reset_link)

    def reset_password(
        self, *, raw_token: str, new_password: str, ip_address: str | None = None
    ) -> None:
        row = self.reset_tokens.get_valid_by_hash(hash_token(raw_token))
        if row is None:
            raise UnauthorizedError("Invalid or expired reset token")

        user = self.users.get(row.user_id)
        if user is None or user.deleted_at is not None:
            raise UnauthorizedError("Account is not available")

        try:
            user.password_hash = hash_password(new_password)
            self.reset_tokens.mark_used(row)  # single-use
            # Password changed => every existing session is suspect.
            revoked = self.refresh_tokens.revoke_all_for_user(user.id)
            self.audit.record(
                action="auth.password_reset_completed",
                user_id=user.id,
                organization_id=user.organization_id,
                metadata={"sessions_revoked": revoked},
                ip_address=ip_address,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        logger.info("password_reset_completed", user_id=str(user.id))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _issue_session(
        self, user: User, *, ip_address: str | None, action: str
    ) -> TokenResponse:
        """Mint access JWT + stored refresh token; commits the transaction."""
        raw_refresh, refresh_hash = generate_opaque_token()
        try:
            self.refresh_tokens.add(
                RefreshToken(
                    user_id=user.id,
                    token_hash=refresh_hash,
                    expires_at=datetime.now(UTC)
                    + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS),
                )
            )
            self.audit.record(
                action=action,
                user_id=user.id,
                organization_id=user.organization_id,
                ip_address=ip_address,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return TokenResponse(
            access_token=create_access_token(
                user_id=user.id,
                organization_id=user.organization_id,
                role=user.role.value,
            ),
            refresh_token=raw_refresh,
            expires_in=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    def _audit_and_commit(
        self,
        *,
        action: str,
        user_id: uuid.UUID | None = None,
        metadata: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Audit events on FAILURE paths must survive even though the main
        operation failed — they get their own tiny transaction."""
        try:
            self.audit.record(
                action=action, user_id=user_id, metadata=metadata, ip_address=ip_address
            )
            self.db.commit()
        except Exception:  # noqa: BLE001 — auditing must never mask the real error
            self.db.rollback()
            logger.error("audit_write_failed", action=action, exc_info=True)
