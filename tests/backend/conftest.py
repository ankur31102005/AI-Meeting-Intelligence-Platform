"""
Shared pytest fixtures for backend tests.

IMPORTANT: environment variables are pinned BEFORE any `app.*` import,
because `app.core.database` builds its engine (and rate_limit builds its
limiter) from settings at import time.

Two client flavors:
  * `client`      — app with NO database behind it (pure HTTP-layer tests).
  * `auth_client` — app wired to a fresh in-memory SQLite DB via dependency
    override; full request->service->repository->DB flows run for real.
"""

import os

# Pin config BEFORE importing the app (module-level side effects).
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("POSTGRES_PASSWORD", "test_password")
os.environ.setdefault("LOG_FORMAT", "console")
os.environ.setdefault("LOG_LEVEL", "WARNING")  # keep test output clean
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")  # limits are prod concerns

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import Base, get_db  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def app():
    """Fresh application instance per test — no cross-test state leaks."""
    return create_app()


@pytest.fixture()
def client(app):
    """HTTP client for the app. Server exceptions are handled by our global
    handler (returning enveloped 500s), so don't re-raise them here."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def db_engine():
    """In-memory SQLite shared across connections within one test.

    StaticPool + check_same_thread=False => TestClient's worker threads all
    see the SAME in-memory database (each new connection would otherwise get
    its own empty one).
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fks(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session_factory(db_engine):
    return sessionmaker(bind=db_engine, expire_on_commit=False)


@pytest.fixture()
def auth_app(db_engine, db_session_factory):
    """App whose get_db dependency is overridden to the test database."""
    application = create_app()

    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    application.dependency_overrides[get_db] = override_get_db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture()
def auth_client(auth_app):
    return TestClient(auth_app, raise_server_exceptions=False)
