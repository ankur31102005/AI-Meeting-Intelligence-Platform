"""Embedding backend selection (cached per process)."""

from functools import lru_cache

from app.ai.embeddings.base import EmbeddingProvider
from app.core.config import get_settings


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    if get_settings().EMBEDDING_PROVIDER == "stub":
        from app.ai.embeddings.stub import StubEmbedder

        return StubEmbedder()

    from app.ai.embeddings.sentence_transformer import SentenceTransformerEmbedder

    return SentenceTransformerEmbedder()
