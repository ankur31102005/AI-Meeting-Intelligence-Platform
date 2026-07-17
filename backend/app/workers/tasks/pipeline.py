"""
Celery task: run the meeting processing pipeline.

Deliberately THIN — it only wires infrastructure (DB session, storage,
transcriber) to the PipelineService and manages retry policy. All logic and
error handling lives in the service, so it's unit-tested without a broker.

Retry policy:
  * MeetingNotProcessable (deleted meeting / no file) is PERMANENT — do not
    retry; the service has already marked it FAILED where appropriate.
  * Any other error (transient storage blip, ffmpeg hiccup) is retried with
    exponential backoff. autoretry gives up after max_retries, leaving the
    meeting in FAILED (the service set that before re-raising).
"""

from app.ai.diarization.factory import get_diarization_provider
from app.ai.embeddings.factory import get_embedding_provider
from app.ai.intelligence.factory import get_llm_provider
from app.ai.transcription.factory import get_transcription_provider
from app.ai.vectorstore.factory import get_vector_store
from app.core.database import session_scope
from app.core.logging import get_logger
from app.services.pipeline_service import MeetingNotProcessable, PipelineService
from app.storage.factory import get_storage_provider
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="pipeline.process_meeting",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,          # 1s, 2s, 4s, ... between attempts
    retry_backoff_max=300,
    retry_jitter=True,           # spread retries to avoid thundering herd
    max_retries=3,
    dont_autoretry_for=(MeetingNotProcessable,),  # permanent failures
)
def process_meeting(self, meeting_id: str) -> dict:
    """Entry point enqueued on upload (and on reprocess)."""
    logger.info("pipeline_task_start", meeting_id=meeting_id, attempt=self.request.retries)

    # A fresh provider/session per task run — never share ORM sessions across
    # tasks (they are not thread/'fork'-safe).
    with session_scope() as db:
        service = PipelineService(
            db=db,
            storage=get_storage_provider(),
            transcriber=get_transcription_provider(),
            diarizer=get_diarization_provider(),
            llm=get_llm_provider(),
            embedder=get_embedding_provider(),
            vector_store=get_vector_store(),
        )
        service.process(_parse_uuid(meeting_id))

    return {"meeting_id": meeting_id, "status": "completed"}


def _parse_uuid(value: str):
    import uuid

    try:
        return uuid.UUID(value)
    except ValueError as exc:
        # Bad id can never succeed on retry — surface as permanent.
        raise MeetingNotProcessable(f"Invalid meeting id: {value!r}") from exc
