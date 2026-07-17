"""
Deterministic fake embedder for tests/CI — no model download.

Produces a stable unit vector from a hash of the text. Two properties we
actually rely on in tests:
  * SAME text -> SAME vector (deterministic, so retrieval is testable),
  * different text -> different vector (so ranking is meaningful).
It is NOT semantically meaningful (hash-based), which is fine: tests assert on
plumbing and exact-match retrieval, not on real semantic quality.
"""

import hashlib
import math

from app.core.config import get_settings


class StubEmbedder:
    def __init__(self) -> None:
        self._dim = get_settings().EMBEDDING_DIM

    def _vector(self, text: str) -> list[float]:
        # Seed a repeatable byte stream from the text, spread across dims,
        # then L2-normalize to a unit vector (matches the real embedder).
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [digest[i % len(digest)] / 255.0 for i in range(self._dim)]
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)
