"""
Meeting processing pipeline — the orchestration brain.

Kept SEPARATE from the Celery task (workers/tasks/pipeline.py) on purpose: the
task is a thin shell (get session, call this, handle retry); ALL the logic
lives here and is unit-testable with a fake storage + stub transcriber, no
broker required.

Flow (each step commits its status so progress is visible via polling):

    1. EXTRACTING   : download original from storage -> ffmpeg -> 16kHz WAV,
                      upload the extracted audio back to storage as a File.
    2. TRANSCRIBING : run the transcription provider on the WAV.
    3. persist       : replace segments (idempotent), store duration, COMPLETED.

Any exception -> status FAILED + error_message, and the exception is
re-raised so Celery can record the failure / retry.

Idempotency: safe to re-run. Segments are deleted-then-inserted, and a rerun
starts by transitioning the (terminal) status back to EXTRACTING.
"""

import tempfile
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.audio import prepare_audio
from app.ai.diarization.base import DiarizationProvider
from app.ai.embeddings.base import EmbeddingProvider
from app.ai.intelligence.base import LLMProvider
from app.ai.transcription.base import TranscriptionProvider
from app.ai.vectorstore.base import VectorStore
from app.core.logging import get_logger
from app.models import File, Meeting, Speaker, TranscriptSegment
from app.models.enums import FileType, MeetingStatus
from app.repositories.audit_repository import AuditRepository
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.speaker_repository import SpeakerRepository
from app.repositories.transcript_repository import (
    MeetingFileRepository,
    TranscriptRepository,
)
from app.services import pipeline_state
from app.services.embedding_service import EmbeddingService
from app.services.intelligence_service import IntelligenceService
from app.services.speaker_assignment import assign_speakers_to_segments
from app.storage.base import StorageProvider

logger = get_logger(__name__)


class MeetingNotProcessable(Exception):
    """Raised when the meeting row is gone or has no source file — a
    permanent failure the task must NOT retry."""


class PipelineService:
    def __init__(
        self,
        db: Session,
        storage: StorageProvider,
        transcriber: TranscriptionProvider,
        diarizer: DiarizationProvider,
        llm: LLMProvider,
        embedder: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self.db = db
        self.storage = storage
        self.transcriber = transcriber
        self.diarizer = diarizer
        self.llm = llm
        self.embedder = embedder
        self.vector_store = vector_store
        self.meetings = MeetingRepository(db)
        self.transcripts = TranscriptRepository(db)
        self.speakers = SpeakerRepository(db)
        self.files = MeetingFileRepository(db)
        self.audit = AuditRepository(db)

    def process(self, meeting_id: uuid.UUID) -> None:
        meeting = self.db.get(Meeting, meeting_id)
        if meeting is None or meeting.deleted_at is not None:
            raise MeetingNotProcessable(f"Meeting {meeting_id} not found")

        original_key = self.files.get_original_key(meeting_id)
        if original_key is None:
            self._fail(meeting, "No source file attached to this meeting")
            raise MeetingNotProcessable(f"Meeting {meeting_id} has no source file")

        try:
            # A single temp dir per run; removed automatically at the end.
            with tempfile.TemporaryDirectory(prefix=f"meeting_{meeting_id}_") as workdir:
                audio_path = self._extract_stage(meeting, original_key, workdir)
                self._transcribe_stage(meeting, audio_path)
                self._diarize_stage(meeting, audio_path)
                self._analyze_stage(meeting)
                self._embed_stage(meeting)
                self._finalize(meeting)
            logger.info("pipeline_completed", meeting_id=str(meeting_id))
        except Exception as exc:
            # Mark FAILED with a human-readable reason, then re-raise so the
            # worker layer sees the failure too.
            self._fail(meeting, str(exc))
            logger.error("pipeline_failed", meeting_id=str(meeting_id), exc_info=True)
            raise

    # ------------------------------------------------------------------
    # Stage 1: extract audio
    # ------------------------------------------------------------------
    def _extract_stage(self, meeting: Meeting, original_key: str, workdir: str) -> str:
        self._advance(meeting, MeetingStatus.EXTRACTING)

        src_ext = original_key.rsplit(".", 1)[-1]
        src_path = str(Path(workdir) / f"source.{src_ext}")
        audio_path = str(Path(workdir) / "audio.wav")

        # Download the original from object storage to local disk for ffmpeg.
        with open(src_path, "wb") as out:
            stream = self.storage.download_stream(original_key)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                out.write(chunk)

        duration = prepare_audio(src_path, audio_path)
        meeting.duration_seconds = int(duration)

        # Persist the extracted audio back to storage as its own File record,
        # so downstream stages / re-runs can reuse it without re-extracting.
        audio_key = f"meetings/{meeting.id}/audio.wav"
        with open(audio_path, "rb") as audio_file:
            stored = self.storage.upload(
                key=audio_key, fileobj=audio_file, content_type="audio/wav"
            )
        self._upsert_extracted_file(meeting.id, stored.key, stored.size_bytes)
        self.db.commit()
        return audio_path

    # ------------------------------------------------------------------
    # Stage 2: transcribe + persist
    # ------------------------------------------------------------------
    def _transcribe_stage(self, meeting: Meeting, audio_path: str) -> None:
        self._advance(meeting, MeetingStatus.TRANSCRIBING)

        result = self.transcriber.transcribe(audio_path)

        # Idempotent: clear any prior transcript, then bulk insert.
        self.transcripts.delete_for_meeting(meeting.id)
        segments = [
            TranscriptSegment(
                meeting_id=meeting.id,
                text=seg.text,
                start_time=seg.start,
                end_time=seg.end,
                confidence=seg.confidence,
                segment_index=i,
            )
            for i, seg in enumerate(result.segments)
        ]
        self.transcripts.bulk_add(segments)

        if result.duration:
            meeting.duration_seconds = int(result.duration)
        self.db.commit()

    # ------------------------------------------------------------------
    # Stage 3: diarization (optional, best-effort)
    # ------------------------------------------------------------------
    def _diarize_stage(self, meeting: Meeting, audio_path: str) -> None:
        """Identify speakers and link them to segments.

        BEST-EFFORT by design: a transcript without speaker labels is still
        valuable, so a diarizer failure logs a warning and lets the meeting
        COMPLETE — it does NOT fail the whole pipeline. The NullDiarizer path
        (no HF_TOKEN) simply produces zero speakers.
        """
        self._advance(meeting, MeetingStatus.DIARIZING)
        try:
            result = self.diarizer.diarize(audio_path)
        except Exception:  # noqa: BLE001 — diarization is optional enrichment
            logger.warning("diarization_failed_continuing", exc_info=True)
            return

        if result.is_empty:
            return  # nothing to link; segments keep speaker_id = None

        # Idempotent: clear prior speakers (FK SET NULL un-links segments).
        self.speakers.delete_for_meeting(meeting.id)

        # One Speaker row per unique label; build label -> id map.
        label_to_id: dict[str, uuid.UUID] = {}
        for label in result.speaker_labels:
            speaker = Speaker(meeting_id=meeting.id, diarization_label=label)
            self.db.add(speaker)
            self.db.flush()  # assign PK
            label_to_id[label] = speaker.id

        # Assign each segment to the best-overlapping speaker.
        segments = self.transcripts.list_for_meeting(meeting.id)
        labels = assign_speakers_to_segments(
            [(s.start_time, s.end_time) for s in segments], result.turns
        )
        for segment, label in zip(segments, labels, strict=True):
            segment.speaker_id = label_to_id.get(label) if label else None

        self.db.commit()
        logger.info(
            "diarization_done",
            meeting_id=str(meeting.id),
            speakers=len(label_to_id),
        )

    # ------------------------------------------------------------------
    # Stage 4: LLM analysis (summaries, insights, action items)
    # ------------------------------------------------------------------
    def _analyze_stage(self, meeting: Meeting) -> None:
        """Run the LLM over the transcript and persist intelligence.

        Unlike diarization, analysis is a CORE feature: a failure here fails
        the pipeline (Celery retries with backoff; a persistent failure lands
        in FAILED with a reason). The transcript is already committed, so even
        a FAILED meeting remains readable.
        """
        self._advance(meeting, MeetingStatus.ANALYZING)
        IntelligenceService(self.db, self.llm).analyze_and_store(meeting)
        self.db.commit()

    # ------------------------------------------------------------------
    # Stage 5: embeddings (chunk + vectorize for RAG/search)
    # ------------------------------------------------------------------
    def _embed_stage(self, meeting: Meeting) -> None:
        """Chunk + embed the transcript into the vector store.

        BEST-EFFORT: the vector store (ChromaDB) is a SEPARATE service. If it's
        down, we must not discard a fully transcribed + analyzed meeting — the
        core deliverables are already saved. Search/chat just won't find this
        meeting until it's reprocessed. Failure logs a warning and continues.
        """
        self._advance(meeting, MeetingStatus.EMBEDDING)
        try:
            EmbeddingService(self.db, self.embedder, self.vector_store).embed_meeting(
                meeting
            )
        except Exception:  # noqa: BLE001 — external store outage is non-fatal
            logger.warning("embedding_failed_continuing", exc_info=True)
            self.db.rollback()

    # ------------------------------------------------------------------
    # Finalize
    # ------------------------------------------------------------------
    def _finalize(self, meeting: Meeting) -> None:
        self._advance(meeting, MeetingStatus.COMPLETED)
        self.audit.record(
            action="meeting.processed",
            organization_id=meeting.organization_id,
            user_id=meeting.owner_id,
            resource_type="meeting",
            resource_id=str(meeting.id),
            metadata={"speakers": len(self.speakers.list_for_meeting(meeting.id))},
        )
        self.db.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _advance(self, meeting: Meeting, target: MeetingStatus) -> None:
        """Validated status change + immediate commit (progress visibility)."""
        pipeline_state.assert_transition(meeting.status, target)
        meeting.status = target
        meeting.error_message = None
        self.db.commit()

    def _fail(self, meeting: Meeting, reason: str) -> None:
        """Force FAILED. Rolls back any partial work first, then re-fetches a
        fresh row (the rollback expires the passed instance) and stamps the
        failure in its own transaction — so the reason always persists."""
        try:
            self.db.rollback()
            fresh = self.db.get(Meeting, meeting.id)
            if fresh is None:
                return
            fresh.status = MeetingStatus.FAILED
            fresh.error_message = reason[:1000]  # keep the column bounded
            self.db.commit()
        except Exception:  # noqa: BLE001 — failure bookkeeping must not raise
            self.db.rollback()
            logger.error("pipeline_fail_write_error", exc_info=True)

    def _upsert_extracted_file(
        self, meeting_id: uuid.UUID, key: str, size_bytes: int
    ) -> None:
        """Create or update the extracted-audio File record. On reprocess the
        deterministic key overwrites the object in storage, so we update the
        existing row rather than inserting a duplicate."""
        existing = self.files.get_by_type(meeting_id, FileType.EXTRACTED_AUDIO)
        if existing is None:
            self.db.add(
                File(
                    meeting_id=meeting_id,
                    file_type=FileType.EXTRACTED_AUDIO,
                    storage_key=key,
                    original_filename="audio.wav",
                    mime_type="audio/wav",
                    size_bytes=size_bytes,
                )
            )
        else:
            existing.storage_key = key
            existing.size_bytes = size_bytes
        self.db.flush()
