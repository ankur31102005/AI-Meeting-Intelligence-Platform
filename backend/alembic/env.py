"""
Alembic migration environment.

Wired to the application's own config and metadata:
  * URL comes from `get_settings().DATABASE_URL` — the same env vars the app
    uses, so migrations always target the same database as the code.
  * `import app.models` registers every table on Base.metadata — this is
    what `alembic revision --autogenerate` diffs against the live schema.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  side effect: registers ALL tables on Base.metadata
from alembic import context
from app.core.config import get_settings
from app.core.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """'Offline' mode: emit SQL to stdout instead of executing it.
    Used for DBA review / environments where the app can't connect directly:
        alembic upgrade head --sql > migration.sql
    """
    context.configure(
        url=get_settings().DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,           # detect column TYPE changes too
        compare_server_default=True,  # and server-default changes
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Standard mode: connect and apply migrations transactionally."""
    connectable = create_engine(
        get_settings().DATABASE_URL,
        poolclass=pool.NullPool,  # migrations need exactly one connection
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
