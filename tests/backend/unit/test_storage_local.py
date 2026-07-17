"""Unit tests for the LocalStorage backend (filesystem, no infra)."""

import io

import pytest

from app.storage.local import LocalStorage


@pytest.fixture()
def storage(tmp_path):
    """Storage rooted in pytest's per-test temp dir — auto-cleaned."""
    return LocalStorage(base_path=str(tmp_path))


class TestLocalStorage:
    def test_upload_and_download_roundtrip(self, storage):
        payload = b"meeting audio bytes"
        obj = storage.upload(
            key="meetings/abc/original.mp3",
            fileobj=io.BytesIO(payload),
            content_type="audio/mpeg",
        )
        assert obj.size_bytes == len(payload)
        assert obj.content_type == "audio/mpeg"
        assert storage.download_stream("meetings/abc/original.mp3").read() == payload

    def test_exists(self, storage):
        assert not storage.exists("meetings/x/original.mp3")
        storage.upload(
            key="meetings/x/original.mp3",
            fileobj=io.BytesIO(b"data"),
            content_type="audio/mpeg",
        )
        assert storage.exists("meetings/x/original.mp3")

    def test_delete_is_idempotent(self, storage):
        storage.delete("does/not/exist.mp3")  # no raise
        storage.upload(
            key="a/b.mp3", fileobj=io.BytesIO(b"d"), content_type="audio/mpeg"
        )
        storage.delete("a/b.mp3")
        assert not storage.exists("a/b.mp3")

    def test_path_traversal_blocked(self, storage):
        """A key escaping the base dir must be refused (security)."""
        with pytest.raises(ValueError, match="traversal"):
            storage.upload(
                key="../../../etc/passwd",
                fileobj=io.BytesIO(b"pwned"),
                content_type="audio/mpeg",
            )

    def test_presigned_url_points_at_api_route(self, storage):
        url = storage.presigned_url("meetings/x/original.mp3", expires_in=900)
        assert url.endswith("/meetings/files/meetings/x/original.mp3")

    def test_satisfies_storage_protocol(self, storage):
        from app.storage.base import StorageProvider

        # runtime_checkable Protocol — structural conformance check.
        assert isinstance(storage, StorageProvider)
