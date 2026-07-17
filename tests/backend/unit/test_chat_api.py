"""
RAG chat + semantic search API tests.

Providers are overridden with fakes (StubEmbedder / InMemoryVectorStore /
StubLLMProvider) so the full retrieve -> context -> answer -> citations loop
runs with no ChromaDB and no API key. The shared in-memory store is seeded
directly to simulate an already-embedded meeting.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.ai.embeddings.stub import StubEmbedder
from app.ai.intelligence.factory import get_llm_provider
from app.ai.intelligence.stub_llm import StubLLMProvider
from app.ai.vectorstore.factory import get_vector_store
from app.ai.vectorstore.memory_store import InMemoryVectorStore
from app.services.pipeline_dispatcher import get_pipeline_dispatcher

SIGNUP = {
    "email": "rag@acme.com",
    "password": "Str0ng-pass!",
    "full_name": "Rag User",
    "organization_name": "Acme",
}


class SpyDispatcher:
    def enqueue_processing(self, meeting_id):
        pass


@pytest.fixture()
def store():
    return InMemoryVectorStore()


@pytest.fixture()
def client(auth_app, store):
    auth_app.dependency_overrides[get_vector_store] = lambda: store
    auth_app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
    auth_app.dependency_overrides[get_pipeline_dispatcher] = lambda: SpyDispatcher()
    # embedding provider factory isn't overridden here because the chat
    # endpoint imports get_embedding_provider; override it too.
    from app.ai.embeddings.factory import get_embedding_provider

    auth_app.dependency_overrides[get_embedding_provider] = lambda: StubEmbedder()
    return TestClient(auth_app, raise_server_exceptions=False)


def auth_headers(client, **overrides):
    client.post("/api/v1/auth/signup", json={**SIGNUP, **overrides})
    token = client.post(
        "/api/v1/auth/login",
        json={
            "email": overrides.get("email", SIGNUP["email"]),
            "password": SIGNUP["password"],
        },
    ).json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def me(client, headers):
    return client.get("/api/v1/auth/me", headers=headers).json()["data"]


def seed_chunks(store, *, org_id, meeting_id, texts):
    """Simulate an embedded meeting by upserting chunks into the vector store."""
    embedder = StubEmbedder()
    ids = [f"{meeting_id}:{i}" for i in range(len(texts))]
    store.upsert(
        ids=ids,
        embeddings=embedder.embed_documents(texts),
        documents=texts,
        metadatas=[
            {
                "meeting_id": str(meeting_id),
                "organization_id": str(org_id),
                "chunk_index": i,
                "start_time": float(i * 10),
                "end_time": float(i * 10 + 8),
            }
            for i in range(len(texts))
        ],
    )
    return ids


class TestSemanticSearch:
    def test_search_returns_matches(self, client, store):
        headers = auth_headers(client)
        org_id = me(client, headers)["organization_id"]
        mid = uuid.uuid4()
        seed_chunks(
            store, org_id=org_id, meeting_id=mid,
            texts=["We will ship on Friday", "Ankur owns the backend"],
        )
        resp = client.post(
            "/api/v1/search", headers=headers, json={"query": "when do we ship?"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["query"] == "when do we ship?"
        assert len(data["results"]) >= 1
        assert all("score" in r for r in data["results"])

    def test_search_scoped_to_org(self, client, store):
        """Tenant isolation: another org's chunks never surface."""
        headers = auth_headers(client)
        # Seed chunks for a DIFFERENT org.
        seed_chunks(
            store, org_id=uuid.uuid4(), meeting_id=uuid.uuid4(),
            texts=["secret from another company"],
        )
        resp = client.post(
            "/api/v1/search", headers=headers, json={"query": "secret"}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["results"] == []  # nothing from other org

    def test_search_requires_auth(self, client):
        assert client.post("/api/v1/search", json={"query": "x"}).status_code == 401


class TestChat:
    def test_create_session(self, client):
        headers = auth_headers(client)
        resp = client.post("/api/v1/chat/sessions", headers=headers, json={})
        assert resp.status_code == 201
        assert resp.json()["data"]["title"] == "New chat"

    def test_ask_returns_answer_with_citations(self, client, store):
        headers = auth_headers(client)
        org_id = me(client, headers)["organization_id"]
        mid = uuid.uuid4()
        seed_chunks(
            store, org_id=org_id, meeting_id=mid,
            texts=["We agreed to ship the release on Friday."],
        )
        session_id = client.post(
            "/api/v1/chat/sessions", headers=headers, json={}
        ).json()["data"]["id"]

        resp = client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"question": "When do we ship?"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "assistant"
        assert "Friday" in data["content"]          # stub grounds on context
        assert data["citations"]                     # citations attached
        assert data["citations"][0]["start_time"] is not None

    def test_history_persisted(self, client, store):
        headers = auth_headers(client)
        org_id = me(client, headers)["organization_id"]
        seed_chunks(
            store, org_id=org_id, meeting_id=uuid.uuid4(), texts=["Some content"]
        )
        session_id = client.post(
            "/api/v1/chat/sessions", headers=headers, json={}
        ).json()["data"]["id"]
        client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"question": "What happened?"},
        )
        detail = client.get(
            f"/api/v1/chat/sessions/{session_id}", headers=headers
        ).json()["data"]
        # user turn + assistant turn.
        roles = [m["role"] for m in detail["messages"]]
        assert roles == ["user", "assistant"]

    def test_first_question_becomes_title(self, client, store):
        headers = auth_headers(client)
        org_id = me(client, headers)["organization_id"]
        seed_chunks(store, org_id=org_id, meeting_id=uuid.uuid4(), texts=["x"])
        session_id = client.post(
            "/api/v1/chat/sessions", headers=headers, json={}
        ).json()["data"]["id"]
        client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            headers=headers,
            json={"question": "What was decided about the release?"},
        )
        detail = client.get(
            f"/api/v1/chat/sessions/{session_id}", headers=headers
        ).json()["data"]
        assert detail["title"] == "What was decided about the release?"

    def test_cannot_access_other_users_session(self, client, store):
        owner = auth_headers(client)
        session_id = client.post(
            "/api/v1/chat/sessions", headers=owner, json={}
        ).json()["data"]["id"]
        intruder = auth_headers(
            client, email="intruder@evil.com", organization_name="Evil"
        )
        resp = client.get(f"/api/v1/chat/sessions/{session_id}", headers=intruder)
        assert resp.status_code == 404

    def test_session_scoped_to_unknown_meeting_404(self, client):
        headers = auth_headers(client)
        resp = client.post(
            "/api/v1/chat/sessions",
            headers=headers,
            json={"meeting_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert resp.status_code == 404
