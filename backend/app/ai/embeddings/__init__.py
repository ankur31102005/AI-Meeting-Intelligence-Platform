"""Text embedding providers (Provider Pattern).

An embedder turns text into a fixed-length vector so semantically similar
text lands near it in vector space — the basis of semantic search + RAG.
`get_embedding_provider()` returns:
    local -> SentenceTransformerEmbedder (free, offline, 384-dim)
    stub  -> deterministic fake (tests / CI, no model download)
"""

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.embeddings.factory import get_embedding_provider

__all__ = ["EmbeddingProvider", "get_embedding_provider"]
