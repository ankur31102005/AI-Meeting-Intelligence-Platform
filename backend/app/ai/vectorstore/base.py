"""Vector store interface + match value object."""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class VectorMatch:
    """One retrieval hit."""

    id: str
    document: str
    metadata: dict[str, Any]
    score: float  # similarity in [0, 1]; higher = more relevant


@runtime_checkable
class VectorStore(Protocol):
    def upsert(
        self,
        *,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Insert-or-replace vectors by id (idempotent re-embedding)."""
        ...

    def query(
        self,
        *,
        embedding: list[float],
        top_k: int,
        where: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        """Nearest neighbours to `embedding`, optionally filtered by metadata
        (`where`) — this is how we scope search to one org / one meeting."""
        ...

    def delete(self, *, where: dict[str, Any]) -> None:
        """Delete all vectors matching a metadata filter (e.g. a meeting's)."""
        ...
