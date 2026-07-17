"""
Cryptographic primitives: password hashing, JWTs, opaque tokens.

Design rules encoded here:
  * Passwords -> bcrypt (slow BY DESIGN: ~100ms per hash makes offline
    brute-force of a leaked DB economically painful).
  * Access tokens -> JWT (HS256): STATELESS, verified by signature alone —
    no DB hit per request. Short-lived (30 min) because they cannot be
    revoked individually.
  * Refresh/reset tokens -> OPAQUE random strings, only their SHA-256 hash
    is stored. Server-side rows make them revocable; hashing means a stolen
    DB dump contains nothing replayable. (SHA-256, not bcrypt, is correct
    here: these are 256-bit random values — unguessable by brute force —
    and lookups must be exact-match on an indexed column.)
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

_JWT_ALGORITHM = "HS256"

# bcrypt ignores bytes beyond 72 — enforced at the schema layer too, but
# guarded here so the primitive is safe regardless of caller.
_BCRYPT_MAX_BYTES = 72


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """bcrypt with per-password random salt (embedded in the output)."""
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > _BCRYPT_MAX_BYTES:
        raise ValueError("password exceeds bcrypt's 72-byte limit")
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time comparison happens inside bcrypt.checkpw."""
    pw_bytes = password.encode("utf-8")
    if len(pw_bytes) > _BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(pw_bytes, password_hash.encode("utf-8"))
    except ValueError:
        # Malformed hash in DB (corruption) — treat as auth failure, not 500.
        return False


# ---------------------------------------------------------------------------
# Access tokens (JWT)
# ---------------------------------------------------------------------------
def create_access_token(
    *, user_id: uuid.UUID, organization_id: uuid.UUID, role: str
) -> str:
    """Short-lived, stateless credential carrying identity + authorization.

    Claims kept minimal: everything here is READABLE by the client (JWT is
    signed, not encrypted) — never put secrets in a token.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org": str(organization_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": uuid.uuid4().hex,  # unique token id (audit / future denylist)
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate signature + expiry + type. Any failure -> 401, never 500."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[_JWT_ALGORITHM],  # explicit list kills alg-swap attacks
            options={"require": ["sub", "exp", "iat", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid access token") from exc

    if payload.get("type") != "access":
        # A refresh/reset token must never pass as an access token.
        raise UnauthorizedError("Invalid token type")
    return payload


# ---------------------------------------------------------------------------
# Opaque tokens (refresh / password-reset)
# ---------------------------------------------------------------------------
def generate_opaque_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash).

    The RAW value goes to the client exactly once; only the HASH is stored.
    48 random bytes -> 64 url-safe chars -> 384 bits of entropy.
    """
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw_token: str) -> str:
    """Deterministic digest for exact-match DB lookup on an indexed column."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
