"""Speaker data access."""

import uuid

from sqlalchemy import delete, select

from app.models import Speaker
from app.repositories.base import BaseRepository


class SpeakerRepository(BaseRepository[Speaker]):
    model = Speaker

    def delete_for_meeting(self, meeting_id: uuid.UUID) -> int:
        """Clear speakers before a re-run. The FK on transcript_segments is
        ON DELETE SET NULL, so this un-links segments WITHOUT deleting the
        transcript — exactly what idempotent reprocessing needs."""
        result = self.db.execute(
            delete(Speaker).where(Speaker.meeting_id == meeting_id)
        )
        return result.rowcount

    def list_for_meeting(self, meeting_id: uuid.UUID) -> list[Speaker]:
        stmt = (
            select(Speaker)
            .where(Speaker.meeting_id == meeting_id)
            .order_by(Speaker.diarization_label)
        )
        return list(self.db.scalars(stmt).all())

    def get_for_meeting(
        self, speaker_id: uuid.UUID, meeting_id: uuid.UUID
    ) -> Speaker | None:
        stmt = select(Speaker).where(
            Speaker.id == speaker_id, Speaker.meeting_id == meeting_id
        )
        return self.db.scalars(stmt).first()
