"""
FastAPI application factory.

`create_app()` (factory pattern) instead of a bare module-level app, because:
  * tests can build isolated app instances with overridden dependencies,
  * startup order is explicit and readable: logging -> middleware ->
    exception handlers -> routes,
  * future variants (admin-only app, internal API) can reuse the factory.

The module-level `app = create_app()` at the bottom is what
`uvicorn app.main:app` imports.
"""

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.rate_limit import limiter, rate_limit_handler

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hooks (modern replacement for on_event handlers)."""
    settings = get_settings()
    logger.info(
        "application_startup",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )
    yield
    # Return all pooled DB connections cleanly on shutdown.
    from app.core.database import engine

    engine.dispose()
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    """Build and wire the FastAPI application."""
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="AI-powered meeting transcription, intelligence and RAG chat platform.",
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        redoc_url=f"{settings.API_V1_PREFIX}/redoc",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # CORS — must be the outermost middleware so even error responses
    # carry the CORS headers the browser requires.
    # ------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # ------------------------------------------------------------------
    # Request context middleware: every request gets a request_id that is
    # (a) bound to all log lines via structlog contextvars, and
    # (b) echoed back in the X-Request-ID response header,
    # so a user bug report with an ID leads you straight to the exact logs.
    # ------------------------------------------------------------------
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            structlog.contextvars.unbind_contextvars("request_id", "method", "path")

        response.headers["X-Request-ID"] = request_id
        # Single structured access log line (replaces uvicorn's plain one).
        logger.info(
            "http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response

    register_exception_handlers(app)

    # Rate limiting: slowapi reads the limiter off app.state; its 429s go
    # through our handler so they use the standard error envelope.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
