"""
SQLAlchemy engine + session management.

Choices (explained):
  * Sync SQLAlchemy (not async): the heavy work in this platform runs in
    Celery workers (which are sync by nature); API endpoints are short CRUD
    queries that FastAPI transparently executes in its threadpool. One session
    style across API + workers = half the code paths, none of the async
    session-lifetime footguns. Revisit only if profiling shows the API is
    I/O-bound at high concurrency.
  * `pool_pre_ping`: transparently replaces connections dropped by the DB /
    load balancer — eliminates the classic "server closed the connection" 500.
  * `expire_on_commit=False`: objects stay usable after commit, so services
    can return ORM objects without surprise lazy-load queries.
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,          # steady-state connections kept open
    max_overflow=20,       # extra connections allowed under burst load
    pool_pre_ping=True,    # validate connections before use
    pool_recycle=3600,     # recycle hourly (beats most idle-timeout policies)
    echo=settings.DEBUG,   # SQL logging in debug mode only
    # Fail fast when the DB is unreachable: without this, a TCP connect to a
    # dead host can hang for ~20s+ (OS default), which would make readiness
    # probes and requests pile up instead of failing cleanly.
    connect_args={"connect_timeout": 5},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# Deterministic constraint names. Without this, Postgres auto-generates names
# like "users_email_key" — and Alembic migrations can't reliably DROP a
# constraint they can't name. Non-negotiable for production migration hygiene.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base — every ORM model inherits from this."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency: one session per request.

    The session is ALWAYS closed (returned to the pool) even if the endpoint
    raises — that is the whole point of the try/finally. Transaction
    commit/rollback is owned by the service layer, not here.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Session for code OUTSIDE the request cycle (Celery tasks, scripts).

    FastAPI's get_db is a generator dependency the framework drives; workers
    have no framework, so they use this context manager. Same lifecycle
    guarantee: the session is always closed.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
