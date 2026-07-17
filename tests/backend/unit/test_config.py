"""Unit tests for app.core.config.Settings — validation, URLs, prod guards."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def make_settings(**overrides) -> Settings:
    """Build Settings ignoring any local .env file (deterministic tests).
    Explicit kwargs take precedence over ambient environment variables."""
    return Settings(_env_file=None, **overrides)


class TestDerivedUrls:
    def test_database_url_assembles_all_parts(self):
        s = make_settings(
            POSTGRES_HOST="db.internal",
            POSTGRES_PORT=5433,
            POSTGRES_USER="svc",
            POSTGRES_PASSWORD="pw123",
            POSTGRES_DB="meetings",
        )
        assert s.DATABASE_URL == "postgresql+psycopg://svc:pw123@db.internal:5433/meetings"

    def test_redis_databases_are_isolated_per_concern(self):
        s = make_settings(REDIS_HOST="cache.internal", REDIS_PORT=6380)
        assert s.REDIS_URL.endswith("/0")
        assert s.CELERY_BROKER_URL.endswith("/1")
        assert s.CELERY_RESULT_BACKEND.endswith("/2")
        assert all(
            url.startswith("redis://cache.internal:6380/")
            for url in (s.REDIS_URL, s.CELERY_BROKER_URL, s.CELERY_RESULT_BACKEND)
        )


class TestCorsParsing:
    def test_single_origin(self):
        s = make_settings(CORS_ORIGINS="http://localhost:3000")
        assert s.cors_origins_list == ["http://localhost:3000"]

    def test_multiple_origins_with_whitespace(self):
        s = make_settings(CORS_ORIGINS="http://a.com, https://b.com ,https://c.com")
        assert s.cors_origins_list == ["http://a.com", "https://b.com", "https://c.com"]


class TestProductionGuards:
    def test_production_rejects_default_secret_key(self):
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            make_settings(
                ENVIRONMENT="production",
                POSTGRES_PASSWORD="a-real-password",
                # SECRET_KEY left at dev default -> must fail
            )

    def test_production_rejects_default_db_password(self):
        with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
            make_settings(
                ENVIRONMENT="production",
                SECRET_KEY="a-real-64-char-secret-key-value",
                POSTGRES_PASSWORD="dev_password_change_me",
            )

    def test_production_boots_with_real_secrets(self):
        s = make_settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-real-64-char-secret-key-value",
            POSTGRES_PASSWORD="a-real-password",
        )
        assert s.is_production is True

    def test_development_allows_dev_defaults(self):
        s = make_settings(ENVIRONMENT="development")
        assert s.is_production is False

    def test_invalid_environment_rejected(self):
        with pytest.raises(ValidationError):
            make_settings(ENVIRONMENT="qa")  # not in the Literal enum
