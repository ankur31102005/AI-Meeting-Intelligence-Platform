"""
Auth endpoints — thin HTTP adapters over AuthService.

Endpoint bodies follow one shape: parse (Pydantic did it) -> call service ->
wrap in envelope. Anything smarter than that belongs in the service.

Rate limits (per client IP) guard the brute-forceable routes; authenticated
routes are naturally throttled by credential checks.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.dependencies import CurrentUser, DbSession, get_client_ip
from app.core.rate_limit import limiter
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.common import APIResponse
from app.services.auth_service import AuthService
from app.services.email import EmailSender, get_email_sender

router = APIRouter(prefix="/auth", tags=["Auth"])


def get_auth_service(
    db: DbSession, email_sender: Annotated[EmailSender, Depends(get_email_sender)]
) -> AuthService:
    """Composition root for auth: swap email sender / db in tests via
    dependency_overrides without touching endpoint code."""
    return AuthService(db, email_sender)


AuthSvc = Annotated[AuthService, Depends(get_auth_service)]

# Rate-limited endpoints below declare a `response: Response` parameter.
# slowapi (with headers_enabled) injects X-RateLimit-* headers into it, and
# FastAPI merges those headers into the returned envelope. Without the param,
# slowapi raises on every successful response — a bug that only surfaces when
# rate limiting is actually enabled (i.e. NOT in the test suite).


@router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace and its admin user",
)
@limiter.limit("5/minute")
def signup(
    request: Request, response: Response, body: SignupRequest, svc: AuthSvc
) -> APIResponse[UserResponse]:
    user = svc.signup(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        organization_name=body.organization_name,
        ip_address=get_client_ip(request),
    )
    return APIResponse(data=UserResponse.model_validate(user))


@router.post("/login", summary="Exchange credentials for tokens")
@limiter.limit("10/minute")
def login(
    request: Request, response: Response, body: LoginRequest, svc: AuthSvc
) -> APIResponse[TokenResponse]:
    tokens = svc.login(
        email=body.email, password=body.password, ip_address=get_client_ip(request)
    )
    return APIResponse(data=tokens)


@router.post("/refresh", summary="Rotate refresh token, get a new pair")
@limiter.limit("30/minute")
def refresh(
    request: Request, response: Response, body: RefreshRequest, svc: AuthSvc
) -> APIResponse[TokenResponse]:
    tokens = svc.refresh(
        raw_refresh_token=body.refresh_token, ip_address=get_client_ip(request)
    )
    return APIResponse(data=tokens)


@router.post("/logout", summary="Revoke a refresh token")
@limiter.limit("30/minute")
def logout(
    request: Request, response: Response, body: LogoutRequest, svc: AuthSvc
) -> APIResponse[dict]:
    svc.logout(raw_refresh_token=body.refresh_token, ip_address=get_client_ip(request))
    return APIResponse(data={"message": "Logged out"})


@router.post(
    "/forgot-password",
    summary="Request a password reset link",
    description="Always returns success — never reveals whether the email exists.",
)
@limiter.limit("3/minute")
def forgot_password(
    request: Request, response: Response, body: ForgotPasswordRequest, svc: AuthSvc
) -> APIResponse[dict]:
    svc.forgot_password(email=body.email, ip_address=get_client_ip(request))
    return APIResponse(
        data={"message": "If that email is registered, a reset link has been sent."}
    )


@router.post("/reset-password", summary="Set a new password using a reset token")
@limiter.limit("5/minute")
def reset_password(
    request: Request, response: Response, body: ResetPasswordRequest, svc: AuthSvc
) -> APIResponse[dict]:
    svc.reset_password(
        raw_token=body.token,
        new_password=body.new_password,
        ip_address=get_client_ip(request),
    )
    return APIResponse(data={"message": "Password updated. Please log in again."})


@router.get("/me", summary="Current authenticated user")
def me(user: CurrentUser) -> APIResponse[UserResponse]:
    return APIResponse(data=UserResponse.model_validate(user))
