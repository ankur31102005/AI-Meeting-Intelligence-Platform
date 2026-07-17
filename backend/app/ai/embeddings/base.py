"""Embedding interface.

Two methods, one intentional distinction:
  * embed_documents — for the corpus (transcript chunks), embedded once at
    ingest time and stored.
  * embed_query — for a user's search/question at read time.
Some models embed queries and documents differently (asymmetric models); the
split lets a provider specialize without changing callers.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents. Batching matters: encoding 100 chunks
        in one call is far cheaper than 100 calls."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        ...
