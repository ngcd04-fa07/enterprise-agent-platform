"""Stage 20: PDF ingestion must reject a pathological document (too many
pages, or too much text producing too many chunks) with a clean `failed`
status — not by trying to embed an unbounded number of chunks
synchronously in one request. Constructs IngestionService directly with
a shrunk Settings copy (via model_copy) so the default limits (500
pages, 2000 chunks) don't need an impractically large test PDF.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.embeddings.base import EmbeddingProvider
from app.models.document import DocumentStatus
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_page_repository import DocumentPageRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.organisation_repository import OrganisationRepository
from app.repositories.submission_repository import SubmissionRepository
from app.repositories.user_repository import UserRepository
from app.services.ingestion_service import IngestionService
from app.storage.base import ObjectStorage
from tests.pdf_fixtures import build_minimal_pdf


async def _seed_document(db_session: AsyncSession, storage: ObjectStorage, *, pdf: bytes) -> object:
    org = await OrganisationRepository(db_session).create(name="Limits Test Org")
    user = await UserRepository(db_session).create(
        email="limits@example.com", full_name="Limits", password_hash="unused"
    )
    submission = await SubmissionRepository(db_session).create(
        organisation_id=org.id, created_by_user_id=user.id, title="Limits Test"
    )
    storage_key = f"{org.id}/limits-test.pdf"
    await storage.put_object(storage_key, pdf, content_type="application/pdf")
    return await DocumentRepository(db_session).create(
        organisation_id=org.id,
        submission_id=submission.id,
        filename="limits-test.pdf",
        content_type="application/pdf",
        size_bytes=len(pdf),
        storage_key=storage_key,
    )


async def test_ingestion_fails_cleanly_when_page_count_exceeds_the_limit(
    db_session: AsyncSession, object_storage: ObjectStorage, embedding_provider: EmbeddingProvider
) -> None:
    pdf = build_minimal_pdf(["Page one.", "Page two.", "Page three."])
    document = await _seed_document(db_session, object_storage, pdf=pdf)
    settings = get_settings().model_copy(update={"max_pdf_pages": 2})

    result = await IngestionService(
        db_session, object_storage, embedding_provider, settings
    ).ingest_document(document)

    assert result.status == DocumentStatus.FAILED
    # No partial rows left behind — the whole parse/chunk/embed attempt
    # rolled back to its savepoint, not just the status flip.
    pages = await DocumentPageRepository(db_session).list_for_document(
        organisation_id=document.organisation_id, document_id=document.id
    )
    chunks = await DocumentChunkRepository(db_session).list_for_document(
        organisation_id=document.organisation_id, document_id=document.id
    )
    assert pages == []
    assert chunks == []


async def test_ingestion_fails_cleanly_when_chunk_count_exceeds_the_limit(
    db_session: AsyncSession, object_storage: ObjectStorage, embedding_provider: EmbeddingProvider
) -> None:
    # One page, but long enough to produce several chunks at the default
    # chunk size (2000 chars, 400 overlap) — a tight max_chunks_per_document
    # of 1 makes any multi-chunk page exceed it.
    long_page_text = "Sentence about the submission. " * 500
    pdf = build_minimal_pdf([long_page_text])
    document = await _seed_document(db_session, object_storage, pdf=pdf)
    settings = get_settings().model_copy(update={"max_chunks_per_document": 1})

    result = await IngestionService(
        db_session, object_storage, embedding_provider, settings
    ).ingest_document(document)

    assert result.status == DocumentStatus.FAILED
    chunks = await DocumentChunkRepository(db_session).list_for_document(
        organisation_id=document.organisation_id, document_id=document.id
    )
    assert chunks == []


async def test_ingestion_succeeds_when_within_both_limits(
    db_session: AsyncSession, object_storage: ObjectStorage, embedding_provider: EmbeddingProvider
) -> None:
    pdf = build_minimal_pdf(["A short, ordinary page."])
    document = await _seed_document(db_session, object_storage, pdf=pdf)
    settings = get_settings()  # real defaults — 500 pages, 2000 chunks

    result = await IngestionService(
        db_session, object_storage, embedding_provider, settings
    ).ingest_document(document)

    assert result.status == DocumentStatus.READY
