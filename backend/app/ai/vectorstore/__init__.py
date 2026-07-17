"""Vector store abstraction (Provider Pattern).

The vector store holds embeddings + metadata and answers "which chunks are
most similar to this query vector?". `get_vector_store()` returns:
    chroma -> ChromaVectorStore (the ChromaDB service)
    memory -> InMemoryVectorStore (in-process cosine search, tests)

Business code depends only on the `VectorStore` interface, so ChromaDB could
be swapped for pgvector/Pinecone by adding one class.
"""

from app.ai.vectorstore.base import VectorMatch, VectorStore
from app.ai.vectorstore.factory import get_vector_store

__all__ = ["VectorMatch", "VectorStore", "get_vector_store"]
