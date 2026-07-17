"""
In-process vector store — brute-force cosine search over a dict.

For tests and CI: no ChromaDB service, fully deterministic. It implements the
same `where`-filter + cosine-ranking semantics as the Chroma backend, so tests
that pass here exercise the real retrieval contract. NOT for production (O(n)
per query, single-process).
"""

import math
from dataclasses import dataclass
from typing import Any

from app.ai.vectorstore.base import VectorMatch


@dataclass
class _Entry:
    embedding: list[float]
    document: str
    metadata: dict[str, Any]


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._data: dict[str, _Entry] = {}

    def upsert(self, *, ids, embeddings, documents, metadatas) -> None:
        for id_, emb, doc, meta in zip(ids, embeddings, documents, metadatas, strict=True):
            self._data[id_] = _Entry(embedding=emb, document=doc, metadata=meta)

    def query(self, *, embedding, top_k, where=None) -> list[VectorMatch]:
        scored = []
        for id_, entry in self._data.items():
            if where and not self._matches(entry.metadata, where):
                continue
            sim = self._cosine(embedding, entry.embedding)
            scored.append(
                VectorMatch(
                    id=id_,
                    document=entry.document,
                    metadata=entry.metadata,
                    score=sim,
                )
            )
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:top_k]

    def delete(self, *, where: dict[str, Any]) -> None:
        to_drop = [id_ for id_, e in self._data.items() if self._matches(e.metadata, where)]
        for id_ in to_drop:
            del self._data[id_]

    # --- helpers ---
    @staticmethod
    def _matches(metadata: dict, where: dict) -> bool:
        return all(metadata.get(k) == v for k, v in where.items())

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (na * nb)
