"""
Model-layer unit tests — run against in-memory SQLite (no Docker needed).

What this suite proves:
  * every mapper/relationship is correctly configured (a whole class of
    runtime errors caught at test time),
  * the full object graph persists and loads,
  * DB-level integrity rules fire: unique constraints, CHECK constraints,
    FK cascades,
  * soft-delete behaves as designed.

PostgreSQL-only behaviors (native enums, JSONB operators, pg_trgm) are
exercised by integration tests once the Docker stack is up.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, configure_mappers, sessionmaker

from app.core.database import Base
from app.models import (
    ActionItem,
    AuditLog,
    ChatMessage,
    ChatSession,
    EmbeddingChunk,
    File,
    Insight,
    Meeting,
    Organization,
    RefreshToken,
    Speaker,
    Summary,
    TranscriptSegment,
    User,
)
from app.models.enums import (
    ChatRole,
    FileType,
    InsightType,
    MeetingStatus,
    SummaryType,
    UserRole,
)


@pytest.fixture()
def db() -> Session:
    """Fresh in-memory database per test — total isolation."""
    engine = create_engine("sqlite://")

    # SQLite ships with FK enforcement OFF; our cascade tests need it ON.
    @event.listens_for(engine, "connect")
    def _enable_fks(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


def seed_org_user(db: Session) -> tuple[Organization, User]:
    org = Organization(name="Acme Corp")
    user = User(
        organization=org,
        email="ankur@acme.com",
        password_hash="$2b$12$notarealhashbutcorrectshape",
        full_name="Ankur Sharma",
        role=UserRole.ADMIN,
    )
    db.add_all([org, user])
    db.commit()
    return org, user


def seed_meeting(db: Session) -> Meeting:
    org, user = seed_org_user(db)
    meeting = Meeting(
        organization=org,
        owner=user,
        title="Q3 Planning",
        meeting_date=datetime(2026, 7, 15, 10, 0, tzinfo=UTC),
        tags=["planning", "q3"],
    )
    db.add(meeting)
    db.commit()
    return meeting


class TestMapperConfiguration:
    def test_all_relationships_resolve(self):
        # Fails loudly if ANY back_populates pair or FK target is wrong.
        configure_mappers()

    def test_all_16_tables_registered(self):
        assert len(Base.metadata.tables) == 16


class TestFullGraph:
    def test_complete_meeting_graph_persists_and_loads(self, db):
        meeting = seed_meeting(db)
        speaker = Speaker(meeting=meeting, diarization_label="SPEAKER_00")
        db.add_all(
            [
                speaker,
                TranscriptSegment(
                    meeting=meeting, speaker=speaker, text="Let's begin.",
                    start_time=0.0, end_time=2.5, confidence=0.97, segment_index=0,
                ),
                TranscriptSegment(
                    meeting=meeting, speaker=speaker, text="Release ships Friday.",
                    start_time=2.5, end_time=6.0, confidence=0.94, segment_index=1,
                ),
                File(
                    meeting=meeting, file_type=FileType.ORIGINAL,
                    storage_key=f"meetings/{meeting.id}/original.mp4",
                    original_filename="standup.mp4", mime_type="video/mp4",
                    size_bytes=52_428_800,
                ),
                Summary(
                    meeting=meeting, summary_type=SummaryType.EXECUTIVE,
                    content="Team aligned on Friday release.", model_used="gpt-4.1",
                ),
                Insight(
                    meeting=meeting, insight_type=InsightType.DECISION,
                    content="Ship on Friday", timestamp_reference=4.2,
                ),
                ActionItem(
                    meeting=meeting, description="Prepare release notes",
                    assignee_name="Ankur",
                ),
                EmbeddingChunk(
                    meeting=meeting, chroma_id=f"{meeting.id}:0",
                    chunk_text="Let's begin. Release ships Friday.",
                    start_time=0.0, end_time=6.0, chunk_index=0,
                ),
            ]
        )
        db.commit()

        loaded = db.get(Meeting, meeting.id)
        assert loaded.status == MeetingStatus.UPLOADED  # default applied
        assert [s.text for s in loaded.segments] == ["Let's begin.", "Release ships Friday."]
        assert loaded.segments[0].speaker.label == "SPEAKER_00"
        assert loaded.summaries[0].model_used == "gpt-4.1"
        assert loaded.tags == ["planning", "q3"]

    def test_chat_session_with_citations(self, db):
        meeting = seed_meeting(db)
        session = ChatSession(user=meeting.owner, meeting=meeting, title="Release Qs")
        db.add(session)
        db.add(
            ChatMessage(
                session=session, role=ChatRole.ASSISTANT,
                content="The release is on Friday.",
                citations=[{"segment_index": 1, "timestamp": 2.5, "text": "Release ships Friday."}],
            )
        )
        db.commit()
        loaded = db.get(ChatSession, session.id)
        assert loaded.messages[0].citations[0]["timestamp"] == 2.5


class TestIntegrityRules:
    def test_duplicate_email_rejected(self, db):
        org, _ = seed_org_user(db)
        db.add(
            User(organization=org, email="ankur@acme.com",
                 password_hash="x", full_name="Impostor")
        )
        with pytest.raises(IntegrityError):
            db.commit()

    def test_duplicate_speaker_label_in_same_meeting_rejected(self, db):
        meeting = seed_meeting(db)
        db.add_all([
            Speaker(meeting=meeting, diarization_label="SPEAKER_00"),
            Speaker(meeting=meeting, diarization_label="SPEAKER_00"),
        ])
        with pytest.raises(IntegrityError):
            db.commit()

    def test_one_summary_per_type_per_meeting(self, db):
        meeting = seed_meeting(db)
        db.add_all([
            Summary(meeting=meeting, summary_type=SummaryType.FULL, content="a", model_used="m"),
            Summary(meeting=meeting, summary_type=SummaryType.FULL, content="b", model_used="m"),
        ])
        with pytest.raises(IntegrityError):
            db.commit()

    def test_segment_end_before_start_rejected(self, db):
        meeting = seed_meeting(db)
        db.add(
            TranscriptSegment(meeting=meeting, text="bad times",
                              start_time=10.0, end_time=5.0, segment_index=0)
        )
        with pytest.raises(IntegrityError):
            db.commit()

    def test_confidence_above_one_rejected(self, db):
        meeting = seed_meeting(db)
        db.add(
            TranscriptSegment(meeting=meeting, text="x", start_time=0, end_time=1,
                              confidence=1.5, segment_index=0)
        )
        with pytest.raises(IntegrityError):
            db.commit()


class TestCascades:
    def test_hard_deleting_meeting_cascades_all_children(self, db):
        meeting = seed_meeting(db)
        speaker = Speaker(meeting=meeting, diarization_label="SPEAKER_00")
        db.add_all([
            speaker,
            TranscriptSegment(meeting=meeting, speaker=speaker, text="hello",
                              start_time=0, end_time=1, segment_index=0),
            EmbeddingChunk(meeting=meeting, chroma_id="c1", chunk_text="hello", chunk_index=0),
        ])
        db.commit()

        db.delete(meeting)
        db.commit()

        assert db.scalars(select(Speaker)).all() == []
        assert db.scalars(select(TranscriptSegment)).all() == []
        assert db.scalars(select(EmbeddingChunk)).all() == []

    def test_deleting_speaker_nullifies_segments_not_deletes(self, db):
        meeting = seed_meeting(db)
        speaker = Speaker(meeting=meeting, diarization_label="SPEAKER_00")
        seg = TranscriptSegment(meeting=meeting, speaker=speaker, text="keep me",
                                start_time=0, end_time=1, segment_index=0)
        db.add_all([speaker, seg])
        db.commit()

        db.delete(speaker)
        db.commit()

        survivor = db.scalars(select(TranscriptSegment)).one()
        assert survivor.text == "keep me"       # transcript text survives
        assert survivor.speaker_id is None      # link cleanly severed

    def test_deleting_user_preserves_audit_log(self, db):
        org, user = seed_org_user(db)
        db.add(AuditLog(organization_id=org.id, user_id=user.id, action="auth.login"))
        db.commit()

        db.delete(user)
        db.commit()

        log = db.scalars(select(AuditLog)).one()
        assert log.action == "auth.login"  # the log outlives its actor
        assert log.user_id is None


class TestSoftDelete:
    def test_soft_delete_flags_without_removing(self, db):
        meeting = seed_meeting(db)
        assert not meeting.is_deleted

        meeting.soft_delete()
        db.commit()

        still_there = db.get(Meeting, meeting.id)
        assert still_there is not None
        assert still_there.is_deleted
        # Children untouched — restore is a one-field revert.
        still_there.restore()
        db.commit()
        assert not db.get(Meeting, meeting.id).is_deleted


class TestDefaultsAndEnums:
    def test_uuid_generated_client_side_at_flush(self, db):
        org = Organization(name="PreFlush Inc")
        db.add(org)
        db.flush()  # SQL sent, but NOT committed yet
        # ID was generated in Python (client-side), not by the database —
        # so it's usable (e.g. for Celery task args) before any commit.
        assert isinstance(org.id, uuid.UUID)

    def test_enum_stored_as_lowercase_value(self, db):
        _, user = seed_org_user(db)
        raw = db.execute(
            select(User.__table__.c.role).where(User.__table__.c.id == user.id)
        ).scalar_one()
        assert raw == "admin"  # value, not "ADMIN" name — readable raw SQL

    def test_refresh_token_revocation_flag(self, db):
        _, user = seed_org_user(db)
        token = RefreshToken(
            user=user, token_hash="a" * 64,
            expires_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
        db.add(token)
        db.commit()
        assert not token.is_revoked
        token.revoked_at = datetime.now(UTC)
        assert token.is_revoked
