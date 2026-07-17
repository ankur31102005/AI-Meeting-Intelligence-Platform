"""
Integration tests — require the Docker stack to be running (`make up`).

Skipped by default; enable with:  INTEGRATION_TESTS=1 pytest tests/backend/integration
(or: make test-integration)
"""

import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("INTEGRATION_TESTS") != "1",
        reason="requires running infrastructure — set INTEGRATION_TESTS=1",
    ),
]


class TestReadiness:
    def test_ready_when_all_dependencies_up(self, client):
        resp = client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "ready"
        assert body["data"]["checks"] == {"postgres": "ok", "redis": "ok"}
