"""Summary / Insight / ActionItem data access."""

import uuid

from sqlalchemy import delete, select

from app.models import ActionItem, Insight, Summary
from app.repositories.base import BaseRepository


class SummaryRepository(BaseRepository[Summary]):
    model = Summary

    def delete_for_meeting(self, meeting_id: uuid.UUID) -> None:
        self.db.execute(delete(Summary).where(Summary.meeting_id == meeting_id))

    def list_for_meeting(self, meeting_id: uuid.UUID) -> list[Summary]:
        return list(
            self.db.scalars(select(Summary).where(Summary.meeting_id == meeting_id)).all()
        )


class InsightRepository(BaseRepository[Insight]):
    model = Insight

    def delete_for_meeting(self, meeting_id: uuid.UUID) -> None:
        self.db.execute(delete(Insight).where(Insight.meeting_id == meeting_id))

    def list_for_meeting(self, meeting_id: uuid.UUID) -> list[Insight]:
        return list(
            self.db.scalars(
                select(Insight)
                .where(Insight.meeting_id == meeting_id)
                .order_by(Insight.insight_type)
            ).all()
        )


class ActionItemRepository(BaseRepository[ActionItem]):
    model = ActionItem

    def delete_for_meeting(self, meeting_id: uuid.UUID) -> None:
        self.db.execute(delete(ActionItem).where(ActionItem.meeting_id == meeting_id))

    def list_for_meeting(self, meeting_id: uuid.UUID) -> list[ActionItem]:
        return list(
            self.db.scalars(
                select(ActionItem)
                .where(ActionItem.meeting_id == meeting_id)
                .order_by(ActionItem.created_at)
            ).all()
        )

    def get_for_meeting(
        self, item_id: uuid.UUID, meeting_id: uuid.UUID
    ) -> ActionItem | None:
        return self.db.scalars(
            select(ActionItem).where(
                ActionItem.id == item_id, ActionItem.meeting_id == meeting_id
            )
        ).first()
