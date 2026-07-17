"""
Celery application instance.

Configuration choices matter a LOT for long AI tasks:
  * task_acks_late=True + worker_prefetch_multiplier=1:
    a task is acknowledged only AFTER it finishes, and each worker prefetches
    exactly one task. If a worker dies mid-transcription, the task returns to
    the queue and another worker picks it up — no silently lost meetings, and
    no 45-minute jobs hoarded in a dead worker's prefetch buffer.
  * task_time_limit: hard kill for runaway tasks (e.g. ffmpeg stuck on a
    corrupt file); soft limit fires first so the task can mark the meeting
    FAILED before dying.
  * Queues are split so cheap tasks (exports, emails) are never stuck behind
    hour-long transcriptions — scale each queue's workers independently.
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "meeting_platform",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    # Task modules — each pipeline stage registers here in later modules.
    include=[
        "app.workers.tasks.system",
        "app.workers.tasks.pipeline",
    ],
)

celery_app.conf.update(
    # Serialization: JSON only. Never allow pickle (arbitrary code execution
    # if the broker is ever compromised).
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone discipline: everything UTC, always.
    timezone="UTC",
    enable_utc=True,
    # Reliability for long-running AI tasks (see module docstring).
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    # Observability: STARTED state is visible while a task runs.
    task_track_started=True,
    # Guardrails: 2h hard kill, soft signal 5 min earlier for cleanup.
    task_time_limit=2 * 60 * 60,
    task_soft_time_limit=2 * 60 * 60 - 300,
    # Results are transient progress signals, not a datastore — the source
    # of truth for pipeline state is the meetings.status column in Postgres.
    result_expires=24 * 60 * 60,
    # Survive broker restarts during deploys.
    broker_connection_retry_on_startup=True,
    # Route by workload so queues can scale independently:
    #   ai_pipeline -> GPU/CPU-heavy (whisper, diarization, LLM, embeddings)
    #   default     -> light tasks (exports, notifications)
    task_routes={
        "pipeline.*": {"queue": "ai_pipeline"},
        "system.*": {"queue": "default"},
    },
    task_default_queue="default",
)
