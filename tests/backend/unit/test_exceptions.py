"""Unit tests for the global exception handlers — the error envelope contract."""

from fastapi.testclient import TestClient

from app.core.exceptions import ConflictError, NotFoundError
from app.main import create_app


def build_client_with_failing_routes() -> TestClient:
    """App with routes that raise each class of error we must handle."""
    app = create_app()

    @app.get("/_test/not-found")
    def raise_not_found():
        raise NotFoundError("Meeting not found")

    @app.get("/_test/conflict")
    def raise_conflict():
        raise ConflictError("Email already registered", details={"field": "email"})

    @app.get("/_test/crash")
    def raise_unexpected():
        raise RuntimeError("database exploded: secret=hunter2")

    @app.get("/_test/validated")
    def validated(limit: int):  # query param must be an int
        return {"limit": limit}

    return TestClient(app, raise_server_exceptions=False)


class TestDomainExceptions:
    def test_not_found_maps_to_404_envelope(self):
        resp = build_client_with_failing_routes().get("/_test/not-found")
        assert resp.status_code == 404
        body = resp.json()
        assert body["success"] is False
        assert body["error"]["code"] == "NOT_FOUND"
        assert body["error"]["message"] == "Meeting not found"

    def test_conflict_carries_structured_details(self):
        resp = build_client_with_failing_routes().get("/_test/conflict")
        assert resp.status_code == 409
        assert resp.json()["error"]["details"] == {"field": "email"}


class TestValidationErrors:
    def test_bad_query_param_returns_422_with_field_errors(self):
        resp = build_client_with_failing_routes().get("/_test/validated?limit=abc")
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        fields = [d["field"] for d in body["error"]["details"]]
        assert any("limit" in f for f in fields)


class TestUnexpectedExceptions:
    def test_crash_returns_500_without_leaking_internals(self):
        resp = build_client_with_failing_routes().get("/_test/crash")
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"]["code"] == "INTERNAL_ERROR"
        # SECURITY: internal message ("secret=hunter2") must NOT leak.
        assert "hunter2" not in resp.text
        assert "RuntimeError" not in resp.text
