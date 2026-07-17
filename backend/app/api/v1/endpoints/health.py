"""
Health endpoints — the operational heartbeat of the service.

Two probes, two different questions (Kubernetes/ELB convention):
  * GET /health        (liveness)  : "is the process up?" — no dependencies,
    must never fail unless the process itself is broken.
  * GET /health/ready  (readiness) : "can it serve traffic?" — checks each
    hard dependency and reports per-dependency status. Load balancers stop
    routing to instances that return 503 here.
"""

import redis
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine
from app.core.logging import get_logger
from app.schemas.common import APIResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])

# Fail fast: a probe that hangs is worse than a probe that fails.
_PROBE_TIMEOUT_SECONDS = 2


def _check_postgres() -> str:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:  # noqa: BLE001 — any failure means "not ready"
        logger.warning("health_check_failed", dependency="postgres", error=str(exc))
        return "unavailable"


def _check_redis() -> str:
    settings = get_settings()
    try:
        client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=_PROBE_TIMEOUT_SECONDS,
            socket_timeout=_PROBE_TIMEOUT_SECONDS,
        )
        client.ping()
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("health_check_failed", dependency="redis", error=str(exc))
        return "unavailable"


@router.get("", summary="Liveness probe")
def liveness() -> APIResponse[dict]:
    """Process is up. Intentionally dependency-free."""
    settings = get_settings()
    return APIResponse(
        data={
            "status": "ok",
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
        }
    )


@router.get(
    "/ready",
    summary="Readiness probe",
    responses={503: {"description": "One or more dependencies unavailable"}},
)
def readiness() -> JSONResponse:
    """Check hard dependencies; 503 with per-dependency detail if any is down."""
    checks = {
        "postgres": _check_postgres(),
        "redis": _check_redis(),
    }
    healthy = all(state == "ok" for state in checks.values())
    body = APIResponse(
        data={"status": "ready" if healthy else "degraded", "checks": checks}
    ).model_dump()
    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=body,
    )
