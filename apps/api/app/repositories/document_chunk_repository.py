import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_chunk import DocumentChunk
from app.models.document_page import DocumentPage


class DocumentChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        document_id: uuid.UUID,
        page_id: uuid.UUID,
        organisation_id: uuid.UUID,
        submission_id: uuid.UUID,
        chunk_index: int,
        text: str,
        start_char: int,
        end_char: int,
        embedding: list[float] | None = None,
    ) -> DocumentChunk:
        chunk = DocumentChunk(
            document_id=document_id,
            page_id=page_id,
            organisation_id=organisation_id,
            submission_id=submission_id,
            chunk_index=chunk_index,
            text=text,
            start_char=start_char,
            end_char=end_char,
            embedding=embedding,
        )
        self._session.add(chunk)
        await self._session.flush()
        return chunk

    async def list_for_document(
        self, *, organisation_id: uuid.UUID, document_id: uuid.UUID
    ) -> list[DocumentChunk]:
        result = await self._session.execute(
            select(DocumentChunk)
            .where(
                DocumentChunk.organisation_id == organisation_id,
                DocumentChunk.document_id == document_id,
            )
            .order_by(DocumentChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def list_for_submission(
        self, *, organisation_id: uuid.UUID, submission_id: uuid.UUID
    ) -> list[DocumentChunk]:
        """Every chunk under a submission, across all its documents, in a
        stable reading order — used by extraction, which reads chunk text
        directly rather than doing a similarity search.
        """
        result = await self._session.execute(
            select(DocumentChunk)
            .where(
                DocumentChunk.organisation_id == organisation_id,
                DocumentChunk.submission_id == submission_id,
            )
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        )
        return list(result.scalars().all())

    async def search_similar(
        self,
        *,
        organisation_id: uuid.UUID,
        query_embedding: list[float],
        limit: int = 10,
        submission_id: uuid.UUID | None = None,
    ) -> list[tuple[DocumentChunk, int, float]]:
        """Nearest-neighbor search by cosine distance, tenant-scoped.
        Returns (chunk, page_number, distance) triples ordered by
        ascending distance (most similar first) — pgvector's comparator
        returns distance, not similarity; callers wanting a 0..1 relevance
        score can use 1 - distance for cosine. Joins DocumentPage for
        page_number so callers get a source-aware result without a
        separate query per chunk.
        """
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)
        stmt = (
            select(DocumentChunk, DocumentPage.page_number, distance.label("distance"))
            .join(DocumentPage, DocumentChunk.page_id == DocumentPage.id)
            .where(
                DocumentChunk.organisation_id == organisation_id,
                DocumentChunk.embedding.is_not(None),
            )
            .order_by(distance)
            .limit(limit)
        )
        if submission_id is not None:
            stmt = stmt.where(DocumentChunk.submission_id == submission_id)

        result = await self._session.execute(stmt)
        return [(chunk, page_number, float(dist)) for chunk, page_number, dist in result.all()]

    async def search_lexical(
        self,
        *,
        organisation_id: uuid.UUID,
        query: str,
        limit: int = 10,
        submission_id: uuid.UUID | None = None,
    ) -> list[tuple[DocumentChunk, int, float]]:
        """Full-text (keyword) search over the generated `search_vector`
        column, tenant-scoped. Returns (chunk, page_number, rank) triples
        ordered by descending rank (best match first) — the other half of
        Stage 10's hybrid retrieval alongside search_similar; see
        RetrievalService for how the two are merged.

        websearch_to_tsquery accepts natural, user-typed search-box syntax
        (quoted phrases, `-` to exclude, implicit AND between words) rather
        than requiring Postgres's stricter tsquery operator syntax.
        """
        ts_query = func.websearch_to_tsquery("english", query)
        rank = func.ts_rank_cd(DocumentChunk.search_vector, ts_query)
        stmt = (
            select(DocumentChunk, DocumentPage.page_number, rank.label("rank"))
            .join(DocumentPage, DocumentChunk.page_id == DocumentPage.id)
            .where(
                DocumentChunk.organisation_id == organisation_id,
                DocumentChunk.search_vector.op("@@")(ts_query),
            )
            .order_by(rank.desc())
            .limit(limit)
        )
        if submission_id is not None:
            stmt = stmt.where(DocumentChunk.submission_id == submission_id)

        result = await self._session.execute(stmt)
        return [(chunk, page_number, float(r)) for chunk, page_number, r in result.all()]
