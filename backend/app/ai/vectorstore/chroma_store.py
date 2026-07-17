"""ChromaDB-backed vector store (talks to the chromadb service).

One shared collection holds every org's chunks; queries ALWAYS pass a
metadata `where` filter (organization_id, and usually meeting_id) so tenants
never see each other's vectors. The collection uses cosine space to match our
normalized embeddings.
"""

from functools import lru_cache
from typing import Any

from app.ai.vectorstore.base import VectorMatch
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache
def _collection():
    import chromadb  # lazy import

    settings = get_settings()
    client = chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
    # get_or_create so a fresh stack works with no manual setup.
    collection = client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    logger.info("chroma_collection_ready", name=settings.CHROMA_COLLECTION)
    return collection


def _to_chroma_where(where: dict[str, Any] | None) -> dict[str, Any] | None:
    """Translate a flat {k: v, ...} AND-filter into Chroma's syntax.

    Chroma requires an explicit $and for multiple conditions, but a single
    condition must stay flat. Callers pass a simple dict; this keeps the
    VectorStore interface backend-agnostic (the memory store ANDs a flat dict
    directly)."""
    if not where:
        return None
    if len(where) == 1:
        return where
    return {"$and": [{k: v} for k, v in where.items()]}


class ChromaVectorStore:
    def upsert(self, *, ids, embeddings, documents, metadatas) -> None:
        if not ids:
            return
        _collection().upsert(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )

    def query(self, *, embedding, top_k, where=None) -> list[VectorMatch]:
        result = _collection().query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=_to_chroma_where(where),
            include=["documents", "metadatas", "distances"],
        )
        # Chroma returns parallel lists nested one level (one query).
        ids = result["ids"][0]
        docs = result["documents"][0]
        metas = result["metadatas"][0]
        dists = result["distances"][0]
        matches = []
        for id_, doc, meta, dist in zip(ids, docs, metas, dists, strict=True):
            # cosine distance in [0, 2] -> similarity in [0, 1].
            matches.append(
                VectorMatch(id=id_, document=doc, metadata=meta, score=1.0 - (dist / 2.0))
            )
        return matches

    def delete(self, *, where: dict[str, Any]) -> None:
        _collection().delete(where=_to_chroma_where(where))
