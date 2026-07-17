"""
End-to-end meeting/upload flow tests (SQLite + temp-dir LocalStorage).

Exercises endpoint -> service -> repository -> DB AND -> storage, covering:
upload validation, tenant isolation, pagination, update, soft delete, and
the storage/DB rollback contract.
"""

import io

import pytest
from fastapi.testclient import TestClient

from app.services.pipeline_dispatcher import get_pipeline_dispatcher
from app.storage.factory import get_storage_provider
from app.storage.local import LocalStorage


class SpyDispatcher:
    """Records enqueue calls instead of touching a real broker."""

    def __init__(self) -> None:
        self.enqueued: list = []

    def enqueue_processing(self, meeting_id) -> None:
        self.enqueued.append(meeting_id)

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 2048  # valid-ish mp3 header + body

SIGNUP = {
    "email": "owner@acme.com",
    "password": "Str0ng-pass!",
    "full_name": "Owner",
    "organization_name": "Acme",
}


@pytest.fixture()
def spy_dispatcher():
    return SpyDispatcher()


@pytest.fixture()
def client(auth_app, tmp_path, spy_dispatcher):
    """Authenticated-capable client with storage pointed at a temp dir and
    the pipeline dispatcher replaced by a spy (no broker needed)."""
    auth_app.dependency_overrides[get_storage_provider] = lambda: LocalStorage(
        base_path=str(tmp_path)
    )
    auth_app.dependency_overrides[get_pipeline_dispatcher] = lambda: spy_dispatcher
    return TestClient(auth_app, raise_server_exceptions=False)


def auth_headers(client, **overrides) -> dict:
    client.post("/api/v1/auth/signup", json={**SIGNUP, **overrides})
    token = (
        client.post(
            "/api/v1/auth/login",
            json={"email": overrides.get("email", SIGNUP["email"]), "password": SIGNUP["password"]},
        )
        .json()["data"]["access_token"]
    )
    return {"Authorization": f"Bearer {token}"}


def upload(client, headers, *, content=MP3, filename="standup.mp3", title=None):
    files = {"file": (filename, io.BytesIO(content), "audio/mpeg")}
    data = {"title": title} if title else {}
    return client.post("/api/v1/meetings", headers=headers, files=files, data=data)


class TestUpload:
    def test_upload_creates_meeting_with_file(self, client):
        headers = auth_headers(client)
        resp = upload(client, headers, title="Q3 Standup")
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Q3 Standup"
        assert data["status"] == "uploaded"
        assert len(data["files"]) == 1
        assert data["files"][0]["original_filename"] == "standup.mp3"
        assert data["files"][0]["size_bytes"] == len(MP3)

    def test_title_defaults_to_filename_stem(self, client):
        headers = auth_headers(client)
        data = upload(client, headers, filename="team-sync.mp3").json()["data"]
        assert data["title"] == "team-sync"

    def test_upload_requires_auth(self, client):
        assert upload(client, {}).status_code == 401

    def test_wrong_extension_rejected(self, client):
        headers = auth_headers(client)
        resp = upload(client, headers, filename="virus.exe")
        assert resp.status_code == 400

    def test_renamed_file_rejected_by_magic(self, client):
        headers = auth_headers(client)
        resp = upload(client, headers, content=b"MZ\x90fake", filename="fake.mp3")
        assert resp.status_code == 400

    def test_empty_file_rejected(self, client):
        headers = auth_headers(client)
        resp = upload(client, headers, content=b"", filename="empty.mp3")
        assert resp.status_code in (400, 413)


class TestListAndDetail:
    def test_list_is_paginated(self, client):
        headers = auth_headers(client)
        for i in range(3):
            upload(client, headers, title=f"Meeting {i}")
        resp = client.get("/api/v1/meetings?page=1&page_size=2", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["meta"]["total_items"] == 3
        assert body["meta"]["total_pages"] == 2

    def test_pagination_covers_all_items_without_overlap(self, client):
        """Stable ordering guarantee: every item appears exactly once across
        pages (no duplicates, no skips) — even with tied timestamps."""
        headers = auth_headers(client)
        for i in range(5):
            upload(client, headers, title=f"Meeting {i}")
        page1 = client.get("/api/v1/meetings?page=1&page_size=2", headers=headers).json()["data"]
        page2 = client.get("/api/v1/meetings?page=2&page_size=2", headers=headers).json()["data"]
        page3 = client.get("/api/v1/meetings?page=3&page_size=2", headers=headers).json()["data"]
        ids = [m["id"] for m in page1 + page2 + page3]
        assert len(ids) == 5
        assert len(set(ids)) == 5  # no item on two pages, none skipped

    def test_newest_first_ordering(self, client, db_session_factory):
        """Newest-first, verified with explicitly-stamped timestamps so the
        assertion doesn't depend on sub-second clock resolution."""
        from datetime import UTC, datetime

        from app.models import Meeting

        headers = auth_headers(client)
        for i in range(3):
            upload(client, headers, title=f"Meeting {i}")
        # Stamp distinct, known created_at values (oldest -> newest by title).
        with db_session_factory() as db:
            for m in db.query(Meeting).all():
                idx = int(m.title.split()[-1])
                m.created_at = datetime(2026, 1, 1 + idx, tzinfo=UTC)
            db.commit()
        titles = [
            m["title"]
            for m in client.get("/api/v1/meetings", headers=headers).json()["data"]
        ]
        assert titles == ["Meeting 2", "Meeting 1", "Meeting 0"]  # newest first

    def test_search_by_title(self, client):
        headers = auth_headers(client)
        upload(client, headers, title="Budget Review")
        upload(client, headers, title="Sprint Planning")
        resp = client.get("/api/v1/meetings?search=budget", headers=headers)
        titles = [m["title"] for m in resp.json()["data"]]
        assert titles == ["Budget Review"]

    def test_detail_includes_files(self, client):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        resp = client.get(f"/api/v1/meetings/{mid}", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]["files"]) == 1

    def test_detail_404_for_unknown(self, client):
        headers = auth_headers(client)
        resp = client.get(
            "/api/v1/meetings/00000000-0000-0000-0000-000000000000", headers=headers
        )
        assert resp.status_code == 404


class TestTenantIsolation:
    def test_cannot_read_other_orgs_meeting(self, client):
        """The core multi-tenant security guarantee."""
        owner = auth_headers(client)
        mid = upload(client, owner).json()["data"]["id"]

        # A different user in a DIFFERENT org must get 404, not the meeting.
        intruder = auth_headers(
            client, email="intruder@evil.com", organization_name="Evil Inc"
        )
        resp = client.get(f"/api/v1/meetings/{mid}", headers=intruder)
        assert resp.status_code == 404


class TestUpdateAndDelete:
    def test_patch_updates_only_sent_fields(self, client):
        headers = auth_headers(client)
        mid = upload(client, headers, title="Original").json()["data"]["id"]
        resp = client.patch(
            f"/api/v1/meetings/{mid}",
            headers=headers,
            json={"tags": ["planning", "q3"]},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title"] == "Original"          # untouched
        assert data["tags"] == ["planning", "q3"]    # updated

    def test_soft_delete_hides_from_list(self, client):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        assert client.delete(f"/api/v1/meetings/{mid}", headers=headers).status_code == 200
        # Gone from list and detail.
        assert client.get("/api/v1/meetings", headers=headers).json()["data"] == []
        assert client.get(f"/api/v1/meetings/{mid}", headers=headers).status_code == 404


class TestDownload:
    def test_download_url_returned(self, client):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        resp = client.get(f"/api/v1/meetings/{mid}/download", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "/meetings/files/" in data["download_url"]  # local backend URL
        assert data["expires_in_seconds"] > 0


class TestPipelineTrigger:
    def test_upload_enqueues_processing(self, client, spy_dispatcher):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        # Exactly one job enqueued, for the created meeting.
        assert len(spy_dispatcher.enqueued) == 1
        assert str(spy_dispatcher.enqueued[0]) == mid

    def test_new_meeting_starts_in_uploaded_status(self, client):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        resp = client.get(f"/api/v1/meetings/{mid}/status", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "uploaded"

    def test_transcript_empty_before_processing(self, client):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        resp = client.get(f"/api/v1/meetings/{mid}/transcript", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["segment_count"] == 0
        assert data["segments"] == []

    def test_reprocess_rejected_while_in_progress(self, client, auth_app, db_session_factory):
        """A meeting mid-flight (TRANSCRIBING) cannot be reprocessed."""
        from app.models import Meeting
        from app.models.enums import MeetingStatus

        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        with db_session_factory() as db:
            import uuid

            m = db.get(Meeting, uuid.UUID(mid))
            m.status = MeetingStatus.TRANSCRIBING
            db.commit()
        resp = client.post(f"/api/v1/meetings/{mid}/reprocess", headers=headers)
        assert resp.status_code == 409  # illegal transition

    def test_reprocess_allowed_when_completed(
        self, client, spy_dispatcher, db_session_factory
    ):
        from app.models import Meeting
        from app.models.enums import MeetingStatus

        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        with db_session_factory() as db:
            import uuid

            db.get(Meeting, uuid.UUID(mid)).status = MeetingStatus.COMPLETED
            db.commit()
        spy_dispatcher.enqueued.clear()
        resp = client.post(f"/api/v1/meetings/{mid}/reprocess", headers=headers)
        assert resp.status_code == 200
        assert len(spy_dispatcher.enqueued) == 1  # re-enqueued


class TestSpeakers:
    """Speaker listing + renaming. We seed speakers/segments directly (the
    pipeline is covered by test_pipeline_service.py) to test the API surface."""

    def _seed_speakers(self, db_session_factory, meeting_id):
        import uuid

        from app.models import Speaker, TranscriptSegment

        with db_session_factory() as db:
            s0 = Speaker(meeting_id=uuid.UUID(meeting_id), diarization_label="SPEAKER_00")
            s1 = Speaker(meeting_id=uuid.UUID(meeting_id), diarization_label="SPEAKER_01")
            db.add_all([s0, s1])
            db.flush()
            db.add_all([
                TranscriptSegment(
                    meeting_id=uuid.UUID(meeting_id), speaker_id=s0.id, text="Hi",
                    start_time=0, end_time=2, segment_index=0,
                ),
                TranscriptSegment(
                    meeting_id=uuid.UUID(meeting_id), speaker_id=s1.id, text="Hello",
                    start_time=2, end_time=4, segment_index=1,
                ),
            ])
            db.commit()
            return str(s0.id)

    def test_list_speakers(self, client, db_session_factory):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        self._seed_speakers(db_session_factory, mid)
        resp = client.get(f"/api/v1/meetings/{mid}/speakers", headers=headers)
        assert resp.status_code == 200
        labels = [s["diarization_label"] for s in resp.json()["data"]]
        assert labels == ["SPEAKER_00", "SPEAKER_01"]

    def test_rename_speaker_updates_label(self, client, db_session_factory):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        sid = self._seed_speakers(db_session_factory, mid)

        resp = client.patch(
            f"/api/v1/meetings/{mid}/speakers/{sid}",
            headers=headers,
            json={"display_name": "Ankur"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["display_name"] == "Ankur"
        assert data["label"] == "Ankur"                 # computed label
        assert data["diarization_label"] == "SPEAKER_00"  # machine id untouched

    def test_renamed_speaker_appears_in_transcript(self, client, db_session_factory):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        sid = self._seed_speakers(db_session_factory, mid)
        client.patch(
            f"/api/v1/meetings/{mid}/speakers/{sid}",
            headers=headers,
            json={"display_name": "Ankur"},
        )
        transcript = client.get(
            f"/api/v1/meetings/{mid}/transcript", headers=headers
        ).json()["data"]
        # First segment (SPEAKER_00 -> Ankur) shows the human name.
        assert transcript["segments"][0]["speaker_label"] == "Ankur"
        assert transcript["segments"][1]["speaker_label"] == "SPEAKER_01"

    def test_rename_unknown_speaker_404(self, client):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        resp = client.patch(
            f"/api/v1/meetings/{mid}/speakers/00000000-0000-0000-0000-000000000000",
            headers=headers,
            json={"display_name": "Ghost"},
        )
        assert resp.status_code == 404

    def test_cannot_rename_speaker_in_other_org(self, client, db_session_factory):
        """Tenant isolation extends to speakers."""
        owner = auth_headers(client)
        mid = upload(client, owner).json()["data"]["id"]
        sid = self._seed_speakers(db_session_factory, mid)
        intruder = auth_headers(
            client, email="intruder@evil.com", organization_name="Evil"
        )
        resp = client.patch(
            f"/api/v1/meetings/{mid}/speakers/{sid}",
            headers=intruder,
            json={"display_name": "Hacked"},
        )
        assert resp.status_code == 404


class TestIntelligence:
    """Intelligence reads + action-item updates. We seed the analysis
    directly (pipeline covered elsewhere) to test the API surface."""

    def _seed_intelligence(self, db_session_factory, meeting_id):
        import uuid
        from datetime import date

        from app.models import ActionItem, Insight, Summary
        from app.models.enums import (
            ActionItemPriority,
            InsightType,
            SummaryType,
        )

        with db_session_factory() as db:
            mid = uuid.UUID(meeting_id)
            db.add_all([
                Summary(meeting_id=mid, summary_type=SummaryType.FULL,
                        content="Full summary text", model_used="stub"),
                Summary(meeting_id=mid, summary_type=SummaryType.EXECUTIVE,
                        content="Exec summary", model_used="stub"),
                Insight(meeting_id=mid, insight_type=InsightType.DECISION,
                        content="Ship on Friday"),
                Insight(meeting_id=mid, insight_type=InsightType.RISK,
                        content="Tight timeline"),
            ])
            item = ActionItem(
                meeting_id=mid, description="Prepare release",
                assignee_name="Ankur", due_date=date(2026, 7, 24),
                priority=ActionItemPriority.HIGH,
            )
            db.add(item)
            db.commit()
            return str(item.id)

    def test_get_intelligence(self, client, db_session_factory):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        self._seed_intelligence(db_session_factory, mid)
        resp = client.get(f"/api/v1/meetings/{mid}/intelligence", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["summaries"]) == 2
        assert len(data["insights"]) == 2
        assert len(data["action_items"]) == 1
        assert data["action_items"][0]["assignee_name"] == "Ankur"

    def test_intelligence_empty_before_analysis(self, client):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        resp = client.get(f"/api/v1/meetings/{mid}/intelligence", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summaries"] == []
        assert data["action_items"] == []

    def test_update_action_item_status(self, client, db_session_factory):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        item_id = self._seed_intelligence(db_session_factory, mid)
        resp = client.patch(
            f"/api/v1/meetings/{mid}/action-items/{item_id}",
            headers=headers,
            json={"status": "done"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "done"

    def test_update_unknown_action_item_404(self, client):
        headers = auth_headers(client)
        mid = upload(client, headers).json()["data"]["id"]
        resp = client.patch(
            f"/api/v1/meetings/{mid}/action-items/00000000-0000-0000-0000-000000000000",
            headers=headers,
            json={"status": "done"},
        )
        assert resp.status_code == 404

    def test_cannot_read_other_orgs_intelligence(self, client, db_session_factory):
        owner = auth_headers(client)
        mid = upload(client, owner).json()["data"]["id"]
        self._seed_intelligence(db_session_factory, mid)
        intruder = auth_headers(
            client, email="intruder@evil.com", organization_name="Evil"
        )
        resp = client.get(f"/api/v1/meetings/{mid}/intelligence", headers=intruder)
        assert resp.status_code == 404
