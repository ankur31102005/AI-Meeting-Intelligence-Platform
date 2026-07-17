"""
Application configuration (12-factor style).

Every runtime setting is read from environment variables (or a local `.env`
file in development). The `Settings` object is created ONCE per process via
`get_settings()` and shared everywhere — this makes configuration:

  * validated at startup (bad config fails fast, not at 3am in production),
  * type-safe (ports are ints, environment is a closed enum),
  * testable (tests construct `Settings(...)` with explicit overrides).
"""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel defaults that make local development frictionless but must NEVER
# reach production. A validator below rejects them when ENVIRONMENT=production.
# S105 suppressed below: these are PUBLIC dev-only sentinels, not secrets —
# the production validator below refuses to boot if they are still in use.
_DEV_SECRET_KEY = "dev-only-secret-key-change-in-production"  # noqa: S105
_DEV_DB_PASSWORD = "dev_password_change_me"  # noqa: S105


class Settings(BaseSettings):
    """Central, validated application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # unknown env vars (PATH, HOME, ...) are not errors
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    APP_NAME: str = "AI Meeting Intelligence Platform"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_FORMAT: Literal["console", "json"] = "console"

    # Comma-separated list of allowed browser origins.
    CORS_ORIGINS: str = "http://localhost:3000"

    # ------------------------------------------------------------------
    # Security (consumed by the auth module)
    # ------------------------------------------------------------------
    SECRET_KEY: str = _DEV_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30
    # Auth endpoints are brute-force targets; disabled only in tests.
    RATE_LIMIT_ENABLED: bool = True
    # Used to build user-facing links (password reset emails).
    FRONTEND_URL: str = "http://localhost:3000"

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "meeting_user"
    POSTGRES_PASSWORD: str = _DEV_DB_PASSWORD
    POSTGRES_DB: str = "meeting_platform"

    # ------------------------------------------------------------------
    # Redis — one logical DB per concern so keys never collide:
    #   db 0 = cache, db 1 = Celery broker, db 2 = Celery results
    # ------------------------------------------------------------------
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # ------------------------------------------------------------------
    # Object storage (MinIO in dev, AWS S3 in prod — identical API)
    # ------------------------------------------------------------------
    STORAGE_PROVIDER: Literal["local", "s3"] = "s3"
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minio_admin"
    S3_SECRET_KEY: str = "minio_dev_password"  # noqa: S105 — dev default, overridden via env
    S3_BUCKET: str = "meeting-files"
    S3_REGION: str = "us-east-1"
    LOCAL_STORAGE_PATH: str = "./storage"

    # ------------------------------------------------------------------
    # ChromaDB (vector store for RAG)
    # ------------------------------------------------------------------
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001

    # ------------------------------------------------------------------
    # AI providers (Strategy Pattern — swap via env, zero code changes)
    # ------------------------------------------------------------------
    # "stub" is a deterministic fake for CI / pipeline smoke tests (no API key,
    # no cost). "ollama" is reserved for a future local-LLM provider.
    LLM_PROVIDER: Literal["openai", "ollama", "stub"] = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4.1"
    # Ollama (free local LLM). From the Dockerized worker, the host's Ollama
    # is reached via host.docker.internal (Docker Desktop). Uses Ollama's
    # OpenAI-compatible endpoint, so no extra dependency is needed.
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434/v1"
    OLLAMA_MODEL: str = "llama3.2"
    # Cap the transcript characters sent to the LLM (cost + context-window
    # guard). ~48k chars ≈ a long meeting; longer transcripts are truncated
    # with a marker (chunked map-reduce summarization is a later enhancement).
    LLM_MAX_TRANSCRIPT_CHARS: int = 48000

    # "stub" is a deterministic fake used by CI / integration tests (and to
    # verify the pipeline end-to-end without downloading a model). Never set
    # it in real deployments.
    TRANSCRIPTION_PROVIDER: Literal["local", "openai", "stub"] = "local"
    WHISPER_MODEL_SIZE: Literal["tiny", "base", "small", "medium"] = "base"
    # CPU is the safe default; set to "cuda" on a GPU host. "int8" keeps the
    # CPU memory footprint small with a tiny accuracy cost.
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    # ffmpeg / ffprobe binaries (just the name if on PATH).
    FFMPEG_BINARY: str = "ffmpeg"
    FFPROBE_BINARY: str = "ffprobe"

    # Empty HF_TOKEN => speaker diarization is gracefully skipped.
    HF_TOKEN: str = ""
    # DIARIZATION_PROVIDER:
    #   auto     -> pyannote if HF_TOKEN is set, else disabled (graceful skip)
    #   stub     -> deterministic fake (tests / smoke checks)
    #   disabled -> never diarize
    DIARIZATION_PROVIDER: Literal["auto", "stub", "disabled"] = "auto"
    # Pretrained pyannote pipeline (accepted on HuggingFace with the token).
    PYANNOTE_PIPELINE: str = "pyannote/speaker-diarization-3.1"

    # EMBEDDING_PROVIDER: local (sentence-transformers) | stub (tests/CI)
    EMBEDDING_PROVIDER: Literal["local", "stub"] = "local"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    # all-MiniLM-L6-v2 outputs 384-dim vectors; the stub matches this.
    EMBEDDING_DIM: int = 384
    # VECTORSTORE: chroma (ChromaDB service) | memory (in-process, tests)
    VECTORSTORE: Literal["chroma", "memory"] = "chroma"
    CHROMA_COLLECTION: str = "meeting_chunks"

    # --- RAG chunking + retrieval ---
    # Target chunk size in characters; consecutive transcript segments are
    # packed up to this size so each chunk is a coherent, embeddable unit.
    CHUNK_TARGET_CHARS: int = 1200
    CHUNK_OVERLAP_CHARS: int = 200
    # How many chunks to retrieve as context for a chat answer.
    RAG_TOP_K: int = 5

    # ------------------------------------------------------------------
    # Uploads (consumed by the file/upload module)
    # ------------------------------------------------------------------
    # 500 MB default cap. Streamed to disk/S3, never held whole in memory.
    MAX_UPLOAD_SIZE_MB: int = 500
    # Presigned download links expire after this many seconds (15 min).
    PRESIGNED_URL_EXPIRE_SECONDS: int = 900

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    # ------------------------------------------------------------------
    # Derived URLs (properties keep the raw env vars simple & composable)
    # ------------------------------------------------------------------
    @property
    def DATABASE_URL(self) -> str:
        """SQLAlchemy connection string (psycopg v3 driver)."""
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL(self) -> str:
        """Redis DB 0 — application cache."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def CELERY_BROKER_URL(self) -> str:
        """Redis DB 1 — Celery task queue."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/1"

    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        """Redis DB 2 — Celery task results."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/2"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS_ORIGINS env var into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    # ------------------------------------------------------------------
    # Fail-fast guard: dev-only secrets must never boot in production.
    # ------------------------------------------------------------------
    @model_validator(mode="after")
    def _reject_dev_secrets_in_production(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            problems: list[str] = []
            if self.SECRET_KEY == _DEV_SECRET_KEY:
                problems.append("SECRET_KEY is still the development default")
            if self.POSTGRES_PASSWORD == _DEV_DB_PASSWORD:
                problems.append("POSTGRES_PASSWORD is still the development default")
            if problems:
                raise ValueError(
                    "Refusing to start in production with insecure config: "
                    + "; ".join(problems)
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """
    Process-wide settings singleton.

    `lru_cache` ensures the `.env` file is parsed and validated exactly once.
    In tests, call `get_settings.cache_clear()` after mutating env vars.
    """
    return Settings()
