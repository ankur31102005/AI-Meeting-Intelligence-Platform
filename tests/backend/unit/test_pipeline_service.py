"""
PipelineService orchestration tests — the heart of M5.

No ffmpeg, no Whisper, no broker: a FAKE storage (in-memory dict) and the
STUB transcriber let us drive the whole flow deterministically and assert on
status transitions, segment persistence, idempotency, and failure handling.

The one external thing we must neutralize is ffmpeg (prepare_audio): it's
monkeypatched to just copy bytes, so these tests run on any machine.
"""

import io
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.diarization.null_diarizer import NullDiarizer
from app.ai.diarization.stub_diarizer import StubDiarizer
from app.ai.embeddings.stub import StubEmbedder
from app.ai.intelligence.stub_llm import StubLLMProvider
from app.ai.transcription.stub import StubTranscriber
from app.ai.vectorstore.memory_store import InMemoryVectorStore
from app.core.database import Base
from app.models import (
    ActionItem,
    File,
    Insight,
    Meeting,
    Organization,
    Speaker,
    Summary,
    User,
)
from app.models.enums import FileType, MeetingStatus, UserRole
from app.services.pipeline_service import MeetingNotProcessable, PipelineService


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeStorage:
    """In-memory object store implementing the StorageProvider surface."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload(self, *, key, fileobj, content_type):
        from app.storage.base import StorageObject

        data = fileobj.read()
        self.objects[key] = data
        return StorageObject(key=key, size_bytes=len(data), content_type=content_type)

    def download_stream(self, key):
        return io.BytesIO(self.objects[key])

    def delete(self, key):
        self.objects.pop(key, None)

    def exists(self, key):
        return key in self.objects

    def presigned_url(self, key, *, expires_in):
        return f"/fake/{key}"


class ExplodingTranscriber:
    def transcribe(self, audio_path):
        raise RuntimeError("model blew up")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture(autouse=True)
def no_ffmpeg(monkeypatch):
    """Replace ffmpeg extraction with a byte copy so tests need no binary."""

    def fake_prepare_audio(input_path, output_path):
        import shutil

        shutil.copyfile(input_path, output_path)
        return 11.2  # pretend duration

    # Patch where pipeline_service looked it up (imported name).
    monkeypatch.setattr(
        "app.services.pipeline_service.prepare_audio", fake_prepare_audio
    )
    # Both stubs probe duration via ffprobe — pin them too.
    monkeypatch.setattr(
        "app.ai.transcription.stub.get_media_duration", lambda path: 11.2
    )
    monkeypatch.setattr(
        "app.ai.diarization.stub_diarizer.get_media_duration", lambda path: 11.2
    )


@pytest.fixture()
def storage():
    return FakeStorage()


def seed_meeting(db, storage, *, with_file=True) -> Meeting:
    org = Organization(name="Acme")
    user = User(
        organization=org, email="o@acme.com", password_hash="x", full_name="O",
        role=UserRole.ADMIN,
    )
    meeting = Meeting(
        organization=org, owner=user, title="Standup", status=MeetingStatus.UPLOADED, tags=[]
    )
    db.add_all([org, user, meeting])
    db.flush()
    if with_file:
        key = f"meetings/{meeting.id}/original.mp3"
        storage.objects[key] = b"ID3fake-audio-bytes"
        db.add(
            File(
                meeting_id=meeting.id, file_type=FileType.ORIGINAL, storage_key=key,
                original_filename="standup.mp3", mime_type="audio/mpeg", size_bytes=19,
            )
        )
    db.commit()
    return meeting


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestHappyPath:
    def test_full_pipeline_completes(self, db, storage):
        meeting = seed_meeting(db, storage)
        PipelineService(db, storage, StubTranscriber(), NullDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore()).process(meeting.id)

        db.refresh(meeting)
        assert meeting.status == MeetingStatus.COMPLETED
        assert meeting.error_message is None
        assert meeting.duration_seconds == 11  # int(11.2)

    def test_segments_persisted_in_order(self, db, storage):
        meeting = seed_meeting(db, storage)
        PipelineService(db, storage, StubTranscriber(), NullDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore()).process(meeting.id)

        db.refresh(meeting)
        segs = sorted(meeting.segments, key=lambda s: s.segment_index)
        assert len(segs) == 3
        assert segs[0].segment_index == 0
        assert "Hello everyone" in segs[0].text
        assert all(0.0 <= s.confidence <= 1.0 for s in segs)

    def test_extracted_audio_file_recorded(self, db, storage):
        meeting = seed_meeting(db, storage)
        PipelineService(db, storage, StubTranscriber(), NullDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore()).process(meeting.id)

        db.refresh(meeting)
        types = {f.file_type for f in meeting.files}
        assert FileType.EXTRACTED_AUDIO in types
        assert any(k.endswith("audio.wav") for k in storage.objects)


class TestIdempotency:
    def test_reprocess_replaces_not_appends(self, db, storage):
        meeting = seed_meeting(db, storage)
        svc = PipelineService(db, storage, StubTranscriber(), NullDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore())
        svc.process(meeting.id)
        # Simulate reprocess: terminal -> rerun.
        svc.process(meeting.id)

        db.refresh(meeting)
        # Still exactly 3 segments, not 6 (old ones were cleared).
        assert len(meeting.segments) == 3


class TestFailureHandling:
    def test_transcriber_error_marks_failed(self, db, storage):
        meeting = seed_meeting(db, storage)
        with pytest.raises(RuntimeError, match="blew up"):
            PipelineService(db, storage, ExplodingTranscriber(), NullDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore()).process(meeting.id)

        db.refresh(meeting)
        assert meeting.status == MeetingStatus.FAILED
        assert "blew up" in meeting.error_message

    def test_missing_file_is_permanent_failure(self, db, storage):
        meeting = seed_meeting(db, storage, with_file=False)
        with pytest.raises(MeetingNotProcessable):
            PipelineService(db, storage, StubTranscriber(), NullDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore()).process(meeting.id)

        db.refresh(meeting)
        assert meeting.status == MeetingStatus.FAILED

    def test_deleted_meeting_is_permanent_failure(self, db, storage):
        with pytest.raises(MeetingNotProcessable):
            PipelineService(db, storage, StubTranscriber(), NullDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore()).process(uuid.uuid4())

    def test_can_recover_after_failure(self, db, storage):
        """FAILED -> reprocess -> COMPLETED (state machine allows the retry)."""
        meeting = seed_meeting(db, storage)
        with pytest.raises(RuntimeError):
            PipelineService(db, storage, ExplodingTranscriber(), NullDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore()).process(meeting.id)
        # Now a working transcriber recovers it.
        PipelineService(db, storage, StubTranscriber(), NullDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore()).process(meeting.id)

        db.refresh(meeting)
        assert meeting.status == MeetingStatus.COMPLETED


class ExplodingDiarizer:
    def diarize(self, audio_path):
        raise RuntimeError("diarizer crashed")


class TestDiarizationStage:
    def test_stub_diarizer_creates_speakers_and_links_segments(self, db, storage):
        meeting = seed_meeting(db, storage)
        PipelineService(db, storage, StubTranscriber(), StubDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore()).process(meeting.id)

        db.refresh(meeting)
        assert meeting.status == MeetingStatus.COMPLETED
        # Stub alternates 2 speakers over the ~11s clip.
        speakers = db.query(Speaker).filter_by(meeting_id=meeting.id).all()
        assert len(speakers) == 2
        # Every segment got assigned to some speaker (they all overlap a turn).
        assert all(s.speaker_id is not None for s in meeting.segments)

    def test_null_diarizer_leaves_segments_unassigned(self, db, storage):
        meeting = seed_meeting(db, storage)
        PipelineService(db, storage, StubTranscriber(), NullDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore()).process(meeting.id)

        db.refresh(meeting)
        assert meeting.status == MeetingStatus.COMPLETED
        assert db.query(Speaker).filter_by(meeting_id=meeting.id).count() == 0
        assert all(s.speaker_id is None for s in meeting.segments)

    def test_diarizer_failure_is_non_fatal(self, db, storage):
        """A diarizer crash must NOT fail the meeting — transcript is still
        valuable. Best-effort enrichment, graceful degradation."""
        meeting = seed_meeting(db, storage)
        # Does not raise; meeting still completes.
        PipelineService(db, storage, StubTranscriber(), ExplodingDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore()).process(meeting.id)

        db.refresh(meeting)
        assert meeting.status == MeetingStatus.COMPLETED
        assert meeting.error_message is None
        assert db.query(Speaker).filter_by(meeting_id=meeting.id).count() == 0

    def test_reprocess_replaces_speakers_not_appends(self, db, storage):
        meeting = seed_meeting(db, storage)
        svc = PipelineService(db, storage, StubTranscriber(), StubDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore())
        svc.process(meeting.id)
        svc.process(meeting.id)  # reprocess

        db.refresh(meeting)
        # Still exactly 2 speakers, not 4.
        assert db.query(Speaker).filter_by(meeting_id=meeting.id).count() == 2


class ExplodingLLM:
    def generate_intelligence(self, transcript_text):
        raise RuntimeError("LLM API down")


class TestAnalyzeStage:
    def _run(self, db, storage):
        meeting = seed_meeting(db, storage)
        PipelineService(
            db, storage, StubTranscriber(), NullDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore()
        ).process(meeting.id)
        db.refresh(meeting)
        return meeting

    def test_summaries_created(self, db, storage):
        meeting = self._run(db, storage)
        summaries = db.query(Summary).filter_by(meeting_id=meeting.id).all()
        types = {s.summary_type.value for s in summaries}
        assert types == {"full", "executive"}

    def test_insights_created_across_types(self, db, storage):
        meeting = self._run(db, storage)
        insights = db.query(Insight).filter_by(meeting_id=meeting.id).all()
        types = {i.insight_type.value for i in insights}
        # Stub returns decisions, risks, discussion points, etc.
        assert "decision" in types
        assert "risk" in types

    def test_action_items_created_with_fields(self, db, storage):
        meeting = self._run(db, storage)
        items = db.query(ActionItem).filter_by(meeting_id=meeting.id).all()
        assert len(items) == 2
        ankur_item = next(i for i in items if i.assignee_name == "Ankur")
        assert ankur_item.priority.value == "high"
        assert ankur_item.due_date is not None  # ISO date parsed

    def test_llm_failure_marks_meeting_failed(self, db, storage):
        """Analysis is a CORE feature — LLM failure fails the pipeline
        (unlike diarization, which is best-effort)."""
        meeting = seed_meeting(db, storage)
        with pytest.raises(RuntimeError, match="LLM API down"):
            PipelineService(
                db, storage, StubTranscriber(), NullDiarizer(), ExplodingLLM(),
                StubEmbedder(), InMemoryVectorStore()
            ).process(meeting.id)
        db.refresh(meeting)
        assert meeting.status == MeetingStatus.FAILED
        assert "LLM API down" in meeting.error_message
        # But the transcript survived (committed before analysis).
        assert len(meeting.segments) == 3

    def test_reprocess_replaces_intelligence(self, db, storage):
        meeting = seed_meeting(db, storage)
        svc = PipelineService(
            db, storage, StubTranscriber(), NullDiarizer(), StubLLMProvider(), StubEmbedder(), InMemoryVectorStore()
        )
        svc.process(meeting.id)
        svc.process(meeting.id)  # reprocess
        db.refresh(meeting)
        # Still exactly 2 summaries, not 4 (idempotent).
        assert db.query(Summary).filter_by(meeting_id=meeting.id).count() == 2
        assert db.query(ActionItem).filter_by(meeting_id=meeting.id).count() == 2


class ExplodingVectorStore:
    def upsert(self, **kwargs):
        raise RuntimeError("chroma down")

    def query(self, **kwargs):
        return []

    def delete(self, **kwargs):
        raise RuntimeError("chroma down")


class TestEmbeddingStage:
    def _svc(self, db, storage, vector_store):
        return PipelineService(
            db, storage, StubTranscriber(), NullDiarizer(), StubLLMProvider(),
            StubEmbedder(), vector_store,
        )

    def test_embedding_chunks_created(self, db, storage):
        from app.models import EmbeddingChunk

        meeting = seed_meeting(db, storage)
        self._svc(db, storage, InMemoryVectorStore()).process(meeting.id)

        chunks = db.query(EmbeddingChunk).filter_by(meeting_id=meeting.id).all()
        assert len(chunks) >= 1
        # Each Postgres twin references a Chroma id derived from the meeting.
        assert all(c.chroma_id.startswith(str(meeting.id)) for c in chunks)

    def test_vectors_stored_and_searchable(self, db, storage):
        meeting = seed_meeting(db, storage)
        store = InMemoryVectorStore()
        self._svc(db, storage, store).process(meeting.id)

        q = StubEmbedder().embed_query("Friday release")
        matches = store.query(embedding=q, top_k=5, where={"meeting_id": str(meeting.id)})
        assert len(matches) >= 1
        assert matches[0].metadata["meeting_id"] == str(meeting.id)

    def test_embedding_failure_is_non_fatal(self, db, storage):
        """ChromaDB outage must NOT fail a transcribed+analyzed meeting."""
        meeting = seed_meeting(db, storage)
        self._svc(db, storage, ExplodingVectorStore()).process(meeting.id)

        db.refresh(meeting)
        assert meeting.status == MeetingStatus.COMPLETED
        assert meeting.error_message is None

    def test_reprocess_replaces_chunks(self, db, storage):
        from app.models import EmbeddingChunk

        meeting = seed_meeting(db, storage)
        svc = self._svc(db, storage, InMemoryVectorStore())
        svc.process(meeting.id)
        first = db.query(EmbeddingChunk).filter_by(meeting_id=meeting.id).count()
        svc.process(meeting.id)
        second = db.query(EmbeddingChunk).filter_by(meeting_id=meeting.id).count()
        assert first == second  # replaced, not doubled
