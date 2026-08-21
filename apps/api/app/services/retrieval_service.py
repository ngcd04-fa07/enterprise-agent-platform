import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.base import EmbeddingProvider
from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk_repository import DocumentChunkRepository


class RetrievalService:
    """Semantic (vector) search over document chunks — the Stage 6
    baseline. Lexical/hybrid retrieval, reranking, and benchmarking are
    later stages (10-11); this is deliberately just cosine-distance
    nearest-neighbor search via pgvector, tenant-scoped and optionally
    narrowed to one submission.
    """

    def __init__(self, db: AsyncSession, embeddings: EmbeddingProvider) -> None:
        self._embeddings = embeddings
        self._chunks = DocumentChunkRepository(db)

    async def search(
        self,
        *,
        organisation_id: uuid.UUID,
        query: str,
        submission_id: uuid.UUID | None = None,
        limit: int = 10,
    ) -> list[tuple[DocumentChunk, int, float]]:
        """Returns (chunk, page_number, distance) triples, ordered by
        ascending distance (most similar first).
        """
        query_embedding = await self._embeddings.embed_query(query)
        return await self._chunks.search_similar(
            organisation_id=organisation_id,
            query_embedding=query_embedding,
            submission_id=submission_id,
            limit=limit,
        )
