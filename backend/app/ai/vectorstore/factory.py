"""Vector store backend selection.

NOTE: unlike other factories this is NOT lru_cached for the memory backend,
because tests need a fresh empty store each time. Chroma is effectively a
singleton via its own cached collection/client.
"""

from app.ai.vectorstore.base import VectorStore
from app.core.config import get_settings

_chroma_singleton: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _chroma_singleton
    if get_settings().VECTORSTORE == "memory":
        from app.ai.vectorstore.memory_store import InMemoryVectorStore

        return InMemoryVectorStore()

    if _chroma_singleton is None:
        from app.ai.vectorstore.chroma_store import ChromaVectorStore

        _chroma_singleton = ChromaVectorStore()
    return _chroma_singleton
