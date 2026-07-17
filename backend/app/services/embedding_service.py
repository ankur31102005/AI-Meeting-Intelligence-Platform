"""
Embedding stage: chunk the transcript, embed it, store vectors.

Dual write by design:
  * ChromaDB holds the VECTORS (for similarity search),
  * Postgres holds a TWIN row per chunk (chroma_id, text, time span).
The twin lets us render citations from one SQL query (no Chroma round-trip per
message) and, critically, clean up Chroma when a meeting is deleted/reprocessed
— without the twins we'd leak orphaned vectors that surface in future answers.

Idempotent: a re-run deletes both sides (Postgres rows + Chroma vectors for the
meeting) before re-inserting.
"""

import uuid

from sqlalchemy.orm import Session

from app.ai.embeddings.base import EmbeddingProvider
from app.ai.vectorstore.base import VectorStore
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import EmbeddingChunk, Meeting
from app.repositories.rag_repository import EmbeddingChunkRepository
from app.repositories.transcript_repository import TranscriptRepository
from app.services.chunking import SegmentInput, chunk_segments

logger = get_logger(__name__)


class EmbeddingService:
    def __init__(
        self, db: Session, embedder: EmbeddingProvider, vector_store: VectorStore
    ) -> None:
        self.db = db
        self.embedder = embedder
        self.vector_store = vector_store
        self.transcripts = TranscriptRepository(db)
        self.chunks = EmbeddingChunkRepository(db)
        self.settings = get_settings()

    def embed_meeting(self, meeting: Meeting) -> int:
        """Chunk -> embed -> store. Returns the number of chunks. Safe to
        re-run (clears prior chunks on both stores first)."""
        segments = self.transcripts.list_for_meeting(meeting.id, with_speaker=True)
        seg_inputs = [
            SegmentInput(
                text=s.text,
                start=s.start_time,
                end=s.end_time,
                speaker_label=s.speaker.label if s.speaker else None,
            )
            for s in segments
        ]
        chunks = chunk_segments(
            seg_inputs,
            target_chars=self.settings.CHUNK_TARGET_CHARS,
            overlap_chars=self.settings.CHUNK_OVERLAP_CHARS,
        )

        # Idempotent cleanup on BOTH stores (order: Chroma then Postgres).
        self.vector_store.delete(where={"meeting_id": str(meeting.id)})
        self.chunks.delete_for_meeting(meeting.id)
        self.db.flush()

        if not chunks:
            self.db.commit()
            return 0

        # Deterministic ids so re-embedding overwrites the same vectors.
        chroma_ids = [f"{meeting.id}:{c.index}" for c in chunks]
        documents = [c.text for c in chunks]
        embeddings = self.embedder.embed_documents(documents)
        metadatas = [
            {
                "meeting_id": str(meeting.id),
                "organization_id": str(meeting.organization_id),
                "chunk_index": c.index,
                "start_time": c.start,
                "end_time": c.end,
            }
            for c in chunks
        ]

        self.vector_store.upsert(
            ids=chroma_ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        self.chunks.bulk_add(
            [
                EmbeddingChunk(
                    meeting_id=meeting.id,
                    chroma_id=chroma_ids[i],
                    chunk_text=chunks[i].text,
                    start_time=chunks[i].start,
                    end_time=chunks[i].end,
                    chunk_index=chunks[i].index,
                )
                for i in range(len(chunks))
            ]
        )
        self.db.commit()
        logger.info("embedding_done", meeting_id=str(meeting.id), chunks=len(chunks))
        return len(chunks)

    def delete_meeting_vectors(self, meeting_id: uuid.UUID) -> None:
        """Remove a meeting's vectors (used on hard delete / cleanup)."""
        self.vector_store.delete(where={"meeting_id": str(meeting_id)})
        self.chunks.delete_for_meeting(meeting_id)
        self.db.commit()
