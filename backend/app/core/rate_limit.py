"""
Rate limiting (slowapi) — brute-force protection for auth endpoints.

Keyed by client IP. In production behind a reverse proxy the real IP
arrives in X-Forwarded-For, so the key function checks it first.

The limiter is created once here and shared: endpoints decorate themselves
with `@limiter.limit("5/minute")`, and main.py registers the 429 handler so
rate-limit errors use the SAME error envelope as everything else.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings


def _client_ip_key(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(
    key_func=_client_ip_key,
    enabled=get_settings().RATE_LIMIT_ENABLED,  # off in tests
    headers_enabled=True,  # X-RateLimit-* response headers for clients
)


async def rate_limit_handler(request: Request, exc: Exception) -> JSONResponse:
    """429 in the standard error envelope."""
    detail = exc.detail if isinstance(exc, RateLimitExceeded) else "rate limit exceeded"
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "error": {
                "code": "RATE_LIMITED",
                "message": f"Too many requests ({detail}). Try again shortly.",
                "details": None,
            },
        },
    )
