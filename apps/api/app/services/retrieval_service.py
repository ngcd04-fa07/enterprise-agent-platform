import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.base import EmbeddingProvider
from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk_repository import DocumentChunkRepository

# Standard Reciprocal Rank Fusion constant (Cormack et al., 2009) — large
# enough that rank differences among top results still matter (a rank-1 vs
# rank-2 result isn't swamped), small enough that being found at all still
# counts meaningfully. Not tuned for this dataset; there's no benchmark yet
# to tune against (Stage 11).
_RRF_K = 60

# Each underlying search fetches more candidates than the final result
# limit, so fusion has enough from each side to actually rank — with only
# `limit` candidates per side, a chunk found by just one method could never
# out-rank one found by both, regardless of how strong its rank was.
_CANDIDATE_POOL_MULTIPLIER = 3
_MIN_CANDIDATE_POOL = 20


class RetrievalService:
    """Hybrid retrieval: pgvector cosine similarity (semantic) and Postgres
    full-text search (lexical), merged via Reciprocal Rank Fusion — see
    docs/architecture.md, hybrid retrieval decision, for why RRF over a
    weighted score blend (distance and ts_rank_cd aren't on comparable
    scales, so a weighted sum would need arbitrary normalization; RRF only
    needs each list's rank order, which is exactly what both already
    produce).
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
        """Returns (chunk, page_number, rrf_score) triples, ordered by
        descending fused score. The score is a Reciprocal Rank Fusion
        value, not a 0..1 relevance measure — only meaningful for ranking
        within one query's results, not for comparison across queries.
        """
        candidate_pool = max(limit * _CANDIDATE_POOL_MULTIPLIER, _MIN_CANDIDATE_POOL)
        query_embedding = await self._embeddings.embed_query(query)

        vector_results = await self._chunks.search_similar(
            organisation_id=organisation_id,
            query_embedding=query_embedding,
            submission_id=submission_id,
            limit=candidate_pool,
        )
        lexical_results = await self._chunks.search_lexical(
            organisation_id=organisation_id,
            query=query,
            submission_id=submission_id,
            limit=candidate_pool,
        )

        scores: dict[uuid.UUID, float] = {}
        chunks_by_id: dict[uuid.UUID, tuple[DocumentChunk, int]] = {}
        for ranked_list in (vector_results, lexical_results):
            for rank, (chunk, page_number, _relevance) in enumerate(ranked_list, start=1):
                scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (_RRF_K + rank)
                chunks_by_id[chunk.id] = (chunk, page_number)

        ranked_ids = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)[:limit]
        return [(*chunks_by_id[chunk_id], scores[chunk_id]) for chunk_id in ranked_ids]
