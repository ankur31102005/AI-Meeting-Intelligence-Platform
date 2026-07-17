"""
Application exception hierarchy + global handlers.

Design:
  * Services/repositories raise DOMAIN exceptions (`NotFoundError`, ...) —
    they never import HTTP concepts. The mapping to status codes lives here,
    in ONE place, keeping business logic transport-agnostic (Clean
    Architecture: inner layers know nothing about the web).
  * Every error leaving the API has the SAME envelope:
        {"success": false, "error": {"code": "...", "message": "...", "details": ...}}
    so the frontend needs exactly one error-handling code path.
  * Unhandled exceptions are logged with full tracebacks but NEVER leak
    internals to the client (security: no stack traces in responses).
"""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppException(Exception):
    """Base class for all domain exceptions raised by services."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class BadRequestError(AppException):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "BAD_REQUEST"


class UnauthorizedError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "UNAUTHORIZED"


class ForbiddenError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "FORBIDDEN"


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    error_code = "CONFLICT"


class PayloadTooLargeError(AppException):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    error_code = "PAYLOAD_TOO_LARGE"


class UnprocessableError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "UNPROCESSABLE"


class ServiceUnavailableError(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "SERVICE_UNAVAILABLE"


def _error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    """Build the standard error envelope."""
    return {"success": False, "error": {"code": code, "message": message, "details": details}}


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the three global handlers. Called once from the app factory."""

    @app.exception_handler(AppException)
    async def handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
        # Domain errors are expected flow-control — log at warning, not error.
        logger.warning(
            "domain_exception",
            error_code=exc.error_code,
            message=exc.message,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.error_code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Reshape pydantic's verbose error list into {field: message} pairs
        # the frontend can render next to form inputs.
        field_errors = [
            {
                "field": ".".join(str(loc) for loc in err["loc"] if loc != "body"),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_error_body("VALIDATION_ERROR", "Request validation failed", field_errors),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        # Unknown failure: full traceback to logs, generic message to client.
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("INTERNAL_ERROR", "An unexpected error occurred"),
        )
