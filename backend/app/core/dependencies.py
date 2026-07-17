"""
FastAPI dependency-injection wiring: authentication + RBAC.

Usage in endpoints (declarative, zero boilerplate in handlers):

    def my_endpoint(user: CurrentUser): ...                      # any logged-in user
    def admin_thing(user: AdminUser): ...                        # admins only
    def team_view(user: Annotated[User, Depends(require_roles(
        UserRole.ADMIN, UserRole.MANAGER))]): ...                # custom combo

Every protected request costs one indexed DB lookup (fresh is_active /
deleted_at check) — deliberately chosen over trusting JWT claims for 30
minutes: a deactivated employee loses access on their NEXT request, not
half an hour later.
"""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.models import User
from app.models.enums import UserRole

# auto_error=False: WE raise (enveloped 401), not FastAPI's default 403.
_bearer_scheme = HTTPBearer(auto_error=False, description="Paste the access token")

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
    db: DbSession,
) -> User:
    """Bearer JWT -> validated, ACTIVE user object."""
    if credentials is None:
        raise UnauthorizedError("Not authenticated")

    payload = decode_access_token(credentials.credentials)

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Invalid token subject") from exc

    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise UnauthorizedError("Account no longer exists")
    if not user.is_active:
        raise ForbiddenError("Account is deactivated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*allowed: UserRole) -> Callable[..., User]:
    """RBAC dependency factory (closure pattern).

    401 = "who are you?" (handled by get_current_user)
    403 = "I know who you are, and you're not allowed" (handled here).
    """

    def check_role(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise ForbiddenError(
                f"Requires one of roles: {', '.join(r.value for r in allowed)}"
            )
        return user

    return check_role


AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
ManagerUser = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]


def get_client_ip(request: Request) -> str | None:
    """Real client IP, honoring reverse-proxy headers (nginx/ALB in prod)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
