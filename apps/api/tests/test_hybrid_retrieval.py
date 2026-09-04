"""Proves hybrid retrieval (RetrievalService) actually changes ranking
versus vector-only search, not just that it runs without error. Uses
directly-controlled embedding vectors (not FakeEmbeddingProvider's
hash-based ones) so the vector-similarity outcome is exactly known,
letting this construct a case where the two signals clearly disagree.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.base import EmbeddingProvider
from app.models.document_chunk import EMBEDDING_DIMENSION
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_page_repository import DocumentPageRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.organisation_repository import OrganisationRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.user_repository import UserRepository
from app.services.retrieval_service import RetrievalService


class _FixedEmbeddingProvider(EmbeddingProvider):
    """Always returns the same vector, regardless of input text — lets a
    test dictate the exact semantic-similarity outcome instead of relying
    on FakeEmbeddingProvider's unpredictable hash-based one.
    """

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    @property
    def dimension(self) -> int:
        return len(self._vector)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector


async def test_hybrid_ranks_lexical_match_above_a_closer_but_irrelevant_vector_match(
    db_session: AsyncSession,
) -> None:
    query_vector = [1.0] + [0.0] * (EMBEDDING_DIMENSION - 1)
    # Orthogonal to query_vector -> cosine distance 1.0, the worst possible
    # vector match, despite containing the exact search phrase.
    lexical_match_vector = [0.0] * (EMBEDDING_DIMENSION - 1) + [1.0]
    # Identical to query_vector -> cosine distance 0.0, the best possible
    # vector match, despite sharing no vocabulary with the query at all.
    vector_match_vector = list(query_vector)

    org = await OrganisationRepository(db_session).create(name="Hybrid Test Org")
    user = await UserRepository(db_session).create(
        email="hybrid@example.com", full_name="Hybrid Tester", password_hash="test-hash"
    )
    submission = await SubmissionRepository(db_session).create(
        organisation_id=org.id, created_by_user_id=user.id, title="Hybrid Test Submission"
    )
    document = await DocumentRepository(db_session).create(
        organisation_id=org.id,
        submission_id=submission.id,
        filename="doc.pdf",
        content_type="application/pdf",
        size_bytes=100,
        storage_key=f"{org.id}/doc.pdf",
    )
    page = await DocumentPageRepository(db_session).create(
        document_id=document.id, organisation_id=org.id, page_number=1, text="irrelevant"
    )

    chunks = DocumentChunkRepository(db_session)
    lexical_match_chunk = await chunks.create(
        document_id=document.id,
        page_id=page.id,
        organisation_id=org.id,
        submission_id=submission.id,
        chunk_index=0,
        text="Confidential acquisition due diligence report, restricted circulation.",
        start_char=0,
        end_char=10,
        embedding=lexical_match_vector,
    )
    vector_match_chunk = await chunks.create(
        document_id=document.id,
        page_id=page.id,
        organisation_id=org.id,
        submission_id=submission.id,
        chunk_index=1,
        text="The cafeteria menu changes every Tuesday and Friday.",
        start_char=0,
        end_char=10,
        embedding=vector_match_vector,
    )

    # Sanity-check the setup deterministically before trusting the fused
    # result: vector search alone should rank the irrelevant chunk first.
    vector_only = await chunks.search_similar(
        organisation_id=org.id, query_embedding=query_vector, limit=10
    )
    assert vector_only[0][0].id == vector_match_chunk.id

    # Lexical search alone should find only the relevant chunk.
    lexical_only = await chunks.search_lexical(
        organisation_id=org.id, query="acquisition due diligence", limit=10
    )
    assert [chunk.id for chunk, _page, _rank in lexical_only] == [lexical_match_chunk.id]

    # Hybrid must recover the lexically-relevant chunk as the top result,
    # despite it being the worst possible vector match.
    service = RetrievalService(db_session, _FixedEmbeddingProvider(query_vector))
    hybrid_results = await service.search(
        organisation_id=org.id, query="acquisition due diligence", limit=10
    )

    assert hybrid_results[0][0].id == lexical_match_chunk.id
