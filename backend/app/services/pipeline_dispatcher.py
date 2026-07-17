"""
Pipeline dispatch abstraction.

The upload/reprocess endpoints must ENQUEUE the background job, but importing
Celery's send_task directly into an endpoint would make every upload test
require a running broker. So we hide enqueueing behind a tiny interface and
inject it (same pattern as EmailSender / StorageProvider):

    * CeleryPipelineDispatcher -> real broker (production).
    * tests override get_pipeline_dispatcher with a spy (records calls).
"""

import uuid
from typing import Protocol

from app.core.logging import get_logger

logger = get_logger(__name__)


class PipelineDispatcher(Protocol):
    def enqueue_processing(self, meeting_id: uuid.UUID) -> None: ...


class CeleryPipelineDispatcher:
    def enqueue_processing(self, meeting_id: uuid.UUID) -> None:
        # Imported here so this module (and the endpoints that depend on it)
        # don't import Celery wiring at module load.
        from app.workers.celery_app import celery_app

        celery_app.send_task("pipeline.process_meeting", args=[str(meeting_id)])
        logger.info("pipeline_enqueued", meeting_id=str(meeting_id))


def get_pipeline_dispatcher() -> PipelineDispatcher:
    return CeleryPipelineDispatcher()
