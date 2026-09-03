"""Proves IngestionService doesn't leave partial DocumentPage/DocumentChunk
rows committed when a later step in the same ingestion run fails — the
SAVEPOINT in IngestionService.ingest_document exists specifically to
prevent this (see the comment there). Found as a real, reproducible bug
during the Stage 1-8 release-candidate audit: before the fix, a document
could end up status=failed with fully-persisted page rows still attached.
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.base import EmbeddingProvider
from app.models.document_chunk import EMBEDDING_DIMENSION
from tests.pdf_fixtures import build_minimal_pdf

PASSWORD = "correct horse battery staple"


class AlwaysFailingEmbeddingProvider(EmbeddingProvider):
    """Simulates an embedding backend that's unreachable partway through
    ingestion — after pages have already been created, but before any
    chunk is.
    """

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIMENSION

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding backend unavailable (simulated)")

    async def embed_query(self, text: str) -> list[float]:
        raise RuntimeError("embedding backend unavailable (simulated)")


async def test_failed_ingestion_leaves_no_partial_pages(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.embeddings.factory import get_embedding_provider
    from app.main import app

    app.dependency_overrides[get_embedding_provider] = lambda: AlwaysFailingEmbeddingProvider()
    try:
        register_response = await client.post(
            "/auth/register",
            json={
                "email": "atomicity@example.com",
                "full_name": "Atomicity Test",
                "password": PASSWORD,
                "organisation_name": "Atomicity Org",
            },
        )
        assert register_response.status_code == 201, register_response.text
        csrf_token = register_response.json()["csrf_token"]

        submission_response = await client.post(
            "/submissions", json={"title": "Atomicity"}, headers={"X-CSRF-Token": csrf_token}
        )
        submission_id = submission_response.json()["id"]

        pdf = build_minimal_pdf(["Page one text.", "Page two text."])
        upload_response = await client.post(
            f"/submissions/{submission_id}/documents",
            files={"file": ("doc.pdf", pdf, "application/pdf")},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert upload_response.status_code == 201, upload_response.text
        document_body = upload_response.json()
        assert document_body["status"] == "failed"

        pages_response = await client.get(f"/documents/{document_body['id']}/pages")
        assert pages_response.status_code == 200
        assert pages_response.json() == []
    finally:
        app.dependency_overrides.pop(get_embedding_provider, None)
