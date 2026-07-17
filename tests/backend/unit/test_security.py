"""Unit tests for cryptographic primitives (core/security.py)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)


class TestPasswordHashing:
    def test_roundtrip(self):
        h = hash_password("S3cure-pass!")
        assert h != "S3cure-pass!"          # never stored in plaintext
        assert h.startswith("$2b$12$")       # bcrypt, cost factor 12
        assert verify_password("S3cure-pass!", h)

    def test_wrong_password_rejected(self):
        assert not verify_password("wrong", hash_password("right-password"))

    def test_same_password_different_hashes(self):
        # Per-password random salt => identical passwords hash differently,
        # so a leaked table can't be attacked with one rainbow lookup.
        assert hash_password("same-pass") != hash_password("same-pass")

    def test_over_72_bytes_raises_on_hash(self):
        with pytest.raises(ValueError, match="72-byte"):
            hash_password("x" * 73)

    def test_over_72_bytes_fails_verify_not_crash(self):
        assert not verify_password("x" * 100, hash_password("short-pass"))

    def test_corrupt_hash_fails_closed(self):
        assert not verify_password("any", "not-a-bcrypt-hash")


class TestAccessTokens:
    def _ids(self):
        return uuid.uuid4(), uuid.uuid4()

    def test_roundtrip_carries_identity_claims(self):
        user_id, org_id = self._ids()
        token = create_access_token(user_id=user_id, organization_id=org_id, role="manager")
        payload = decode_access_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["org"] == str(org_id)
        assert payload["role"] == "manager"
        assert payload["type"] == "access"

    def test_expired_token_rejected(self):
        user_id, org_id = self._ids()
        expired = pyjwt.encode(
            {
                "sub": str(user_id), "org": str(org_id), "role": "admin",
                "type": "access",
                "iat": datetime.now(UTC) - timedelta(hours=2),
                "exp": datetime.now(UTC) - timedelta(hours=1),
            },
            get_settings().SECRET_KEY,
            algorithm="HS256",
        )
        with pytest.raises(UnauthorizedError, match="expired"):
            decode_access_token(expired)

    def test_tampered_signature_rejected(self):
        user_id, org_id = self._ids()
        token = create_access_token(user_id=user_id, organization_id=org_id, role="employee")
        with pytest.raises(UnauthorizedError):
            decode_access_token(token[:-4] + "AAAA")

    def test_wrong_secret_rejected(self):
        forged = pyjwt.encode(
            {
                "sub": str(uuid.uuid4()), "type": "access",
                "iat": datetime.now(UTC),
                "exp": datetime.now(UTC) + timedelta(minutes=30),
            },
            "attacker-controlled-secret-that-is-long-enough",
            algorithm="HS256",
        )
        with pytest.raises(UnauthorizedError):
            decode_access_token(forged)

    def test_non_access_type_rejected(self):
        wrong_type = pyjwt.encode(
            {
                "sub": str(uuid.uuid4()), "type": "refresh",
                "iat": datetime.now(UTC),
                "exp": datetime.now(UTC) + timedelta(minutes=30),
            },
            get_settings().SECRET_KEY,
            algorithm="HS256",
        )
        with pytest.raises(UnauthorizedError, match="token type"):
            decode_access_token(wrong_type)


class TestOpaqueTokens:
    def test_raw_and_hash_pair_consistent(self):
        raw, hashed = generate_opaque_token()
        assert hash_token(raw) == hashed     # DB lookup works
        assert raw != hashed                 # stored value is NOT the secret
        assert len(hashed) == 64             # sha256 hexdigest

    def test_tokens_are_unique(self):
        assert generate_opaque_token()[0] != generate_opaque_token()[0]
