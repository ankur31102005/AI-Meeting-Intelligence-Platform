"""
System/operational tasks.

`system.ping` is the worker-side readiness check: if
    celery_app.send_task("system.ping").get(timeout=5) == "pong"
then broker, worker and result backend are ALL healthy. Used by
`scripts/verify_stack.py` and by admins to diagnose a stuck queue.
"""

from app.core.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="system.ping")
def ping() -> str:
    """Round-trip probe through broker -> worker -> result backend."""
    logger.info("worker_ping_received")
    return "pong"
