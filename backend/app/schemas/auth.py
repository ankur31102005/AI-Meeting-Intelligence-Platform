"""Auth request/response contracts.

Validation happens HERE, at the boundary — by the time data reaches the
service layer it is structurally sound (format, lengths, types), so services
only enforce BUSINESS rules (uniqueness, credentials, state).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole

# bcrypt hard limit is 72 BYTES; 72 chars is the safe conservative bound.
_PASSWORD_FIELD = Field(min_length=8, max_length=72)


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = _PASSWORD_FIELD
    full_name: str = Field(min_length=1, max_length=255)
    # Signup creates a fresh workspace (SaaS model); the signer-up owns it.
    organization_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20)
    new_password: str = _PASSWORD_FIELD


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 — OAuth2 scheme name, not a secret
    expires_in: int  # access-token lifetime in seconds (client refresh hint)


class UserResponse(BaseModel):
    """Public shape of a user — password_hash can NEVER leak through here
    because the field simply does not exist on this model."""

    model_config = ConfigDict(from_attributes=True)  # build from ORM objects

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    organization_id: uuid.UUID
    is_active: bool
    created_at: datetime
