"""Transcript (segments) + File-record data access for the pipeline."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.models import File, TranscriptSegment
from app.repositories.base import BaseRepository


class TranscriptRepository(BaseRepository[TranscriptSegment]):
    model = TranscriptSegment

    def delete_for_meeting(self, meeting_id: uuid.UUID) -> int:
        """Wipe existing segments before a (re)run — makes the pipeline
        IDEMPOTENT: reprocessing replaces the transcript instead of appending
        a second copy. Returns rows deleted."""
        result = self.db.execute(
            delete(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting_id)
        )
        return result.rowcount

    def bulk_add(self, segments: list[TranscriptSegment]) -> None:
        """Insert many segments in one round-trip (bulk_save_objects is far
        cheaper than N add() calls for a long transcript)."""
        self.db.bulk_save_objects(segments)
        self.db.flush()

    def list_for_meeting(
        self, meeting_id: uuid.UUID, *, with_speaker: bool = False
    ) -> list[TranscriptSegment]:
        stmt = (
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting_id)
            .order_by(TranscriptSegment.segment_index)
        )
        if with_speaker:
            # Eager-load the speaker so rendering "Ankur: ..." for every
            # segment doesn't fire one query per row (N+1).
            stmt = stmt.options(selectinload(TranscriptSegment.speaker))
        return list(self.db.scalars(stmt).all())


class MeetingFileRepository(BaseRepository[File]):
    """File records created BY the pipeline (extracted audio, later exports)."""

    model = File

    def get_original_key(self, meeting_id: uuid.UUID) -> str | None:
        from app.models.enums import FileType

        stmt = select(File.storage_key).where(
            File.meeting_id == meeting_id,
            File.file_type == FileType.ORIGINAL,
        )
        return self.db.scalars(stmt).first()

    def get_by_type(self, meeting_id: uuid.UUID, file_type) -> File | None:
        stmt = select(File).where(
            File.meeting_id == meeting_id, File.file_type == file_type
        )
        return self.db.scalars(stmt).first()
