"""Local embeddings via sentence-transformers (all-MiniLM-L6-v2, 384-dim).

The model loads weights into RAM, so it's built once per process and cached.
`sentence_transformers` is imported lazily so this module is import-safe on
processes that don't embed.
"""

from functools import lru_cache

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def _load_model():
    from sentence_transformers import SentenceTransformer  # lazy heavy import

    settings = get_settings()
    logger.info("embedding_model_loading", model=settings.EMBEDDING_MODEL)
    return SentenceTransformer(settings.EMBEDDING_MODEL)


class SentenceTransformerEmbedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = _load_model()
        # normalize_embeddings=True -> unit vectors, so cosine == dot product
        # and distances are consistent with Chroma's cosine space.
        vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        model = _load_model()
        vector = model.encode([text], normalize_embeddings=True, convert_to_numpy=True)
        return vector[0].tolist()
