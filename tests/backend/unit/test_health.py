"""Unit tests for the liveness endpoint and request-context middleware.
(The readiness probe needs real Postgres/Redis — covered by integration tests.)"""


class TestLiveness:
    def test_returns_200_with_envelope(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["status"] == "ok"
        assert body["data"]["environment"] == "development"
        assert "version" in body["data"]

    def test_meta_is_null_for_non_paginated_endpoints(self, client):
        body = client.get("/api/v1/health").json()
        assert body["meta"] is None


class TestRequestContextMiddleware:
    def test_response_carries_generated_request_id(self, client):
        resp = client.get("/api/v1/health")
        assert "X-Request-ID" in resp.headers
        assert len(resp.headers["X-Request-ID"]) == 32  # uuid4().hex

    def test_client_supplied_request_id_is_echoed_back(self, client):
        # Distributed tracing: an upstream gateway's ID must be preserved.
        resp = client.get("/api/v1/health", headers={"X-Request-ID": "trace-abc-123"})
        assert resp.headers["X-Request-ID"] == "trace-abc-123"


class TestApiDocs:
    def test_openapi_schema_is_served(self, client):
        resp = client.get("/api/v1/openapi.json")
        assert resp.status_code == 200
        assert resp.json()["info"]["title"] == "AI Meeting Intelligence Platform"
