"""
Structured logging via structlog.

Why structured logging?
  * Development : pretty, colored, human-readable console output.
  * Production  : one JSON object per line — directly ingestible by
    CloudWatch / Datadog / Loki, searchable by any field.

Every log line automatically carries the request-scoped context bound by the
middleware in `app.main` (request_id, method, path), because
`merge_contextvars` is the first processor in the chain. That is what lets
you trace ONE request across API logs and (later) Celery worker logs.
"""

import logging
import sys

import structlog


def setup_logging(log_level: str = "INFO", log_format: str = "console") -> None:
    """Configure structlog + the stdlib root logger. Call once at startup."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Third-party libraries (uvicorn, sqlalchemy, celery) log via stdlib —
    # give them a plain handler so their messages are not lost.
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    # Uvicorn's default access log duplicates our own richer access log
    # (see middleware in app.main), so silence it.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    shared_processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,  # inject request_id etc.
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,  # exc_info=True -> traceback field
    ]

    renderer: structlog.typing.Processor
    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Named logger accessor — use `get_logger(__name__)` in every module."""
    return structlog.get_logger(name)
