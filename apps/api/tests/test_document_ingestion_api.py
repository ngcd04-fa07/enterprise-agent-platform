from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.document_chunk_repository import DocumentChunkRepository
from tests.pdf_fixtures import build_minimal_pdf

PASSWORD = "correct horse battery staple"


async def _register(
    client: AsyncClient, *, email: str, organisation_name: str
) -> dict[str, Any]:
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "full_name": "Test User",
            "password": PASSWORD,
            "organisation_name": organisation_name,
        },
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def _create_submission(client: AsyncClient, *, csrf_token: str) -> dict[str, Any]:
    response = await client.post(
        "/submissions", json={"title": "Q3 Renewal"}, headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_upload_creates_pages_with_extracted_text(client: AsyncClient) -> None:
    auth_body = await _register(client, email="ing1@example.com", organisation_name="Acme")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])
    pdf = build_minimal_pdf(["First page text", "Second page text"])

    upload_response = await client.post(
        f"/submissions/{submission['id']}/documents",
        files={"file": ("multi.pdf", pdf, "application/pdf")},
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )
    assert upload_response.status_code == 201, upload_response.text
    document_id = upload_response.json()["id"]

    pages_response = await client.get(f"/documents/{document_id}/pages")

    assert pages_response.status_code == 200
    pages = pages_response.json()
    assert len(pages) == 2
    assert pages[0]["page_number"] == 1
    assert "First page text" in pages[0]["text"]
    assert pages[1]["page_number"] == 2
    assert "Second page text" in pages[1]["text"]


async def test_upload_creates_chunks_with_provenance(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    auth_body = await _register(client, email="ing2@example.com", organisation_name="Acme2")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])
    pdf = build_minimal_pdf(["Some chunkable page content here."])

    upload_response = await client.post(
        f"/submissions/{submission['id']}/documents",
        files={"file": ("one.pdf", pdf, "application/pdf")},
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )
    assert upload_response.status_code == 201, upload_response.text
    document_body = upload_response.json()
    document_id = document_body["id"]

    chunks = await DocumentChunkRepository(db_session).list_for_document(
        organisation_id=auth_body["active_organisation_id"],
        document_id=document_id,
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert "Some chunkable page content here." in chunk.text
    assert chunk.chunk_index == 0
    assert str(chunk.submission_id) == submission["id"]
    assert str(chunk.organisation_id) == auth_body["active_organisation_id"]


async def test_pages_endpoint_requires_membership_in_owning_organisation(
    client: AsyncClient, second_client: AsyncClient
) -> None:
    auth_body = await _register(client, email="ing3@example.com", organisation_name="Org A")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])
    pdf = build_minimal_pdf(["Confidential content"])

    upload_response = await client.post(
        f"/submissions/{submission['id']}/documents",
        files={"file": ("doc.pdf", pdf, "application/pdf")},
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )
    document_id = upload_response.json()["id"]

    await _register(second_client, email="ing4@example.com", organisation_name="Org B")

    response = await second_client.get(f"/documents/{document_id}/pages")

    assert response.status_code == 404


async def test_upload_of_unparseable_pdf_marks_document_failed(client: AsyncClient) -> None:
    """A file that passes the %PDF- magic-byte check but isn't a real,
    parseable PDF should still be safely stored (the upload succeeds) —
    ingestion just marks the document failed instead of crashing the
    request. See IngestionService.
    """
    auth_body = await _register(client, email="ing5@example.com", organisation_name="Acme5")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])
    garbage_pdf = b"%PDF-1.4\nthis is not a real pdf structure at all"

    response = await client.post(
        f"/submissions/{submission['id']}/documents",
        files={"file": ("broken.pdf", garbage_pdf, "application/pdf")},
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "failed"
