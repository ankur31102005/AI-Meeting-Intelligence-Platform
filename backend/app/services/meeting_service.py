"""
Meeting business logic: upload, list, fetch, update, delete.

The upload flow is the interesting one and models a real ordering hazard:

    1. Peek the first bytes -> validate (extension + magic) BEFORE storing.
    2. Stream the file to object storage (MinIO/S3).
    3. Create Meeting + File rows in ONE transaction.
    4. If the DB write fails, DELETE the stored object (compensating action)
       so a committed file never lacks its DB record — no orphan bytes.

Storage and DB are two systems with no shared transaction; step 4 is how we
keep them consistent without distributed transactions.
"""

import uuid
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models import File, Meeting
from app.models.enums import FileType, MeetingStatus
from app.repositories.audit_repository import AuditRepository
from app.repositories.intelligence_repository import (
    ActionItemRepository,
    InsightRepository,
    SummaryRepository,
)
from app.repositories.meeting_repository import FileRepository, MeetingRepository
from app.repositories.speaker_repository import SpeakerRepository
from app.repositories.transcript_repository import TranscriptRepository
from app.schemas.common import PaginationMeta
from app.services import pipeline_state
from app.services.file_validation import (
    LimitedReader,
    enforce_size_limit,
    validate_extension_and_magic,
)
from app.storage.base import StorageProvider

logger = get_logger(__name__)

# Enough bytes to cover every magic signature we check (mp4 'ftyp' at 4,
# wav 'WAVE' at 8..12). 32 is comfortably sufficient.
_MAGIC_PEEK_BYTES = 32


class MeetingService:
    def __init__(self, db: Session, storage: StorageProvider) -> None:
        self.db = db
        self.storage = storage
        self.meetings = MeetingRepository(db)
        self.files = FileRepository(db)
        self.transcripts = TranscriptRepository(db)
        self.speakers = SpeakerRepository(db)
        self.summaries = SummaryRepository(db)
        self.insights = InsightRepository(db)
        self.action_items = ActionItemRepository(db)
        self.audit = AuditRepository(db)
        self.settings = get_settings()

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------
    def create_from_upload(
        self,
        *,
        organization_id: uuid.UUID,
        owner_id: uuid.UUID,
        filename: str,
        fileobj: BinaryIO,
        title: str | None,
        ip_address: str | None = None,
    ) -> Meeting:
        # 1. Validate BEFORE storing — peek the header without consuming it.
        header = fileobj.read(_MAGIC_PEEK_BYTES)
        fileobj.seek(0)
        validated = validate_extension_and_magic(filename, header)

        # 2. Deterministic, collision-free key. Meeting id is minted up front
        #    (client-side UUID) so the key is known before any DB write.
        meeting_id = uuid.uuid4()
        storage_key = f"meetings/{meeting_id}/original.{validated.extension}"

        # Everything that can leave an orphaned object lives in one try, so a
        # failure ANYWHERE (mid-stream size abort, size re-check, or DB write)
        # triggers the same cleanup: delete the object + roll back the DB.
        try:
            # Wrap so the stream self-aborts if it exceeds the cap MID-UPLOAD —
            # storage never receives more than the limit.
            limited = LimitedReader(fileobj, self.settings.max_upload_size_bytes)
            stored = self.storage.upload(
                key=storage_key, fileobj=limited, content_type=validated.content_type
            )

            # Belt-and-braces: re-check the real bytes written (also rejects 0).
            enforce_size_limit(stored.size_bytes, self.settings.max_upload_size_bytes)

            meeting = Meeting(
                id=meeting_id,
                organization_id=organization_id,
                owner_id=owner_id,
                title=title or self._default_title(filename),
                status=MeetingStatus.UPLOADED,
                tags=[],
            )
            self.db.add(meeting)
            self.files.add(
                File(
                    meeting_id=meeting_id,
                    file_type=FileType.ORIGINAL,
                    storage_key=stored.key,
                    original_filename=filename,
                    mime_type=stored.content_type,
                    size_bytes=stored.size_bytes,
                )
            )
            self.audit.record(
                action="meeting.upload",
                organization_id=organization_id,
                user_id=owner_id,
                resource_type="meeting",
                resource_id=str(meeting_id),
                metadata={"filename": filename, "size_bytes": stored.size_bytes},
                ip_address=ip_address,
            )
            self.db.commit()
        except Exception:
            # COMPENSATING ACTION: roll back the DB AND remove the orphaned
            # object so storage and DB never disagree.
            self.db.rollback()
            self.storage.delete(storage_key)
            logger.warning("upload_rolled_back", storage_key=storage_key, exc_info=True)
            raise

        logger.info("meeting_created", meeting_id=str(meeting_id), size=stored.size_bytes)
        return meeting

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def get_detail(self, *, meeting_id: uuid.UUID, organization_id: uuid.UUID) -> Meeting:
        meeting = self.meetings.get_for_org(
            meeting_id, organization_id, with_files=True
        )
        if meeting is None:
            raise NotFoundError("Meeting not found")
        return meeting

    def list_meetings(
        self,
        *,
        organization_id: uuid.UUID,
        page: int,
        page_size: int,
        search: str | None = None,
    ) -> tuple[list[Meeting], PaginationMeta]:
        items, total = self.meetings.list_for_org(
            organization_id, page=page, page_size=page_size, search=search
        )
        meta = PaginationMeta.build(page=page, page_size=page_size, total_items=total)
        return items, meta

    def get_download_url(self, *, meeting_id: uuid.UUID, organization_id: uuid.UUID) -> str:
        meeting = self.get_detail(meeting_id=meeting_id, organization_id=organization_id)
        original = next(
            (f for f in meeting.files if f.file_type == FileType.ORIGINAL), None
        )
        if original is None:
            raise NotFoundError("Meeting has no original file")
        return self.storage.presigned_url(
            original.storage_key, expires_in=self.settings.PRESIGNED_URL_EXPIRE_SECONDS
        )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def update(
        self,
        *,
        meeting_id: uuid.UUID,
        organization_id: uuid.UUID,
        title: str | None,
        description: str | None,
        tags: list[str] | None,
    ) -> Meeting:
        meeting = self.get_detail(meeting_id=meeting_id, organization_id=organization_id)
        # PATCH semantics: only overwrite fields the client actually sent.
        if title is not None:
            meeting.title = title
        if description is not None:
            meeting.description = description
        if tags is not None:
            meeting.tags = tags
        self.db.commit()
        return meeting

    def delete(
        self,
        *,
        meeting_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        ip_address: str | None = None,
    ) -> None:
        """Soft delete: the row (and its media) stay recoverable. Storage
        cleanup for permanently-purged meetings is a separate admin job."""
        meeting = self.meetings.get_for_org(meeting_id, organization_id)
        if meeting is None:
            raise NotFoundError("Meeting not found")
        meeting.soft_delete()
        self.audit.record(
            action="meeting.delete",
            organization_id=organization_id,
            user_id=user_id,
            resource_type="meeting",
            resource_id=str(meeting_id),
            ip_address=ip_address,
        )
        self.db.commit()

    # ------------------------------------------------------------------
    # Transcript + reprocess (M5)
    # ------------------------------------------------------------------
    def get_transcript(self, *, meeting_id: uuid.UUID, organization_id: uuid.UUID):
        """Return (meeting, ordered segments with speakers). 404 if the meeting
        isn't the caller's — segments are empty until the pipeline finishes."""
        meeting = self.meetings.get_for_org(meeting_id, organization_id)
        if meeting is None:
            raise NotFoundError("Meeting not found")
        segments = self.transcripts.list_for_meeting(meeting_id, with_speaker=True)
        return meeting, segments

    # ------------------------------------------------------------------
    # Speakers (M6)
    # ------------------------------------------------------------------
    def list_speakers(self, *, meeting_id: uuid.UUID, organization_id: uuid.UUID):
        meeting = self.meetings.get_for_org(meeting_id, organization_id)
        if meeting is None:
            raise NotFoundError("Meeting not found")
        return self.speakers.list_for_meeting(meeting_id)

    def rename_speaker(
        self,
        *,
        meeting_id: uuid.UUID,
        speaker_id: uuid.UUID,
        organization_id: uuid.UUID,
        display_name: str,
    ):
        """Assign a human name to a diarized speaker. The immutable
        diarization_label is untouched, so segment links never break."""
        meeting = self.meetings.get_for_org(meeting_id, organization_id)
        if meeting is None:
            raise NotFoundError("Meeting not found")
        speaker = self.speakers.get_for_meeting(speaker_id, meeting_id)
        if speaker is None:
            raise NotFoundError("Speaker not found")
        speaker.display_name = display_name
        self.db.commit()
        return speaker

    def request_reprocess(
        self,
        *,
        meeting_id: uuid.UUID,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        ip_address: str | None = None,
    ) -> Meeting:
        """Validate that a meeting CAN be reprocessed, then hand back to the
        caller to enqueue. Only terminal meetings (COMPLETED/FAILED) may be
        re-run — re-running one mid-flight would race the active task."""
        meeting = self.meetings.get_for_org(meeting_id, organization_id)
        if meeting is None:
            raise NotFoundError("Meeting not found")
        # Reuses the state machine: EXTRACTING is only reachable from
        # UPLOADED / COMPLETED / FAILED, so an in-progress meeting is rejected.
        pipeline_state.assert_transition(meeting.status, MeetingStatus.EXTRACTING)
        self.audit.record(
            action="meeting.reprocess_requested",
            organization_id=organization_id,
            user_id=user_id,
            resource_type="meeting",
            resource_id=str(meeting_id),
            ip_address=ip_address,
        )
        self.db.commit()
        return meeting

    # ------------------------------------------------------------------
    # Intelligence reads + action-item update (M7)
    # ------------------------------------------------------------------
    def get_intelligence(self, *, meeting_id: uuid.UUID, organization_id: uuid.UUID):
        """Return (meeting, summaries, insights, action_items). Lists are
        empty until the ANALYZING stage runs."""
        meeting = self.meetings.get_for_org(meeting_id, organization_id)
        if meeting is None:
            raise NotFoundError("Meeting not found")
        return (
            meeting,
            self.summaries.list_for_meeting(meeting_id),
            self.insights.list_for_meeting(meeting_id),
            self.action_items.list_for_meeting(meeting_id),
        )

    def update_action_item(
        self,
        *,
        meeting_id: uuid.UUID,
        item_id: uuid.UUID,
        organization_id: uuid.UUID,
        status=None,
        assignee_user_id=None,
        priority=None,
        description: str | None = None,
    ):
        """Update a task's tracking fields (status, owner, priority, text).
        Org-scoped: the meeting must belong to the caller's organization."""
        meeting = self.meetings.get_for_org(meeting_id, organization_id)
        if meeting is None:
            raise NotFoundError("Meeting not found")
        item = self.action_items.get_for_meeting(item_id, meeting_id)
        if item is None:
            raise NotFoundError("Action item not found")

        if status is not None:
            item.status = status
        if assignee_user_id is not None:
            item.assignee_user_id = assignee_user_id
        if priority is not None:
            item.priority = priority
        if description is not None:
            item.description = description
        self.db.commit()
        return item

    @staticmethod
    def _default_title(filename: str) -> str:
        """'q3-standup.mp4' -> 'q3-standup' as a friendly default title."""
        stem = filename.rsplit(".", 1)[0].strip()
        return stem or "Untitled meeting"
