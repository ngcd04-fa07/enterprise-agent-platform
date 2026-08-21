import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password
from app.core.config import get_settings
from app.main import app
from app.models.membership import MembershipRole
from app.repositories.membership_repository import OrganisationMembershipRepository
from app.repositories.user_repository import UserRepository

PASSWORD = "correct horse battery staple"
VALID_PDF_BYTES = b"%PDF-1.4\n%%EOF"


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


async def test_upload_valid_pdf_succeeds(client: AsyncClient) -> None:
    auth_body = await _register(client, email="uw@example.com", organisation_name="Acme")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    response = await client.post(
        f"/submissions/{submission['id']}/documents",
        files={"file": ("application.pdf", VALID_PDF_BYTES, "application/pdf")},
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["filename"] == "application.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["size_bytes"] == len(VALID_PDF_BYTES)
    assert body["status"] == "uploaded"


async def test_upload_requires_csrf_token(client: AsyncClient) -> None:
    auth_body = await _register(client, email="uw2@example.com", organisation_name="Acme2")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    response = await client.post(
        f"/submissions/{submission['id']}/documents",
        files={"file": ("application.pdf", VALID_PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 403


async def test_upload_rejects_non_pdf_content_type(client: AsyncClient) -> None:
    auth_body = await _register(client, email="uw3@example.com", organisation_name="Acme3")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    response = await client.post(
        f"/submissions/{submission['id']}/documents",
        files={"file": ("notes.txt", b"just text", "text/plain")},
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )

    assert response.status_code == 415


async def test_upload_rejects_content_mismatching_declared_pdf_type(client: AsyncClient) -> None:
    auth_body = await _register(client, email="uw4@example.com", organisation_name="Acme4")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    response = await client.post(
        f"/submissions/{submission['id']}/documents",
        files={"file": ("fake.pdf", b"not actually a pdf", "application/pdf")},
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )

    assert response.status_code == 422


async def test_upload_rejects_oversized_file(client: AsyncClient) -> None:
    auth_body = await _register(client, email="uw5@example.com", organisation_name="Acme5")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    tiny_settings = get_settings().model_copy(update={"max_upload_size_bytes": 4})
    app.dependency_overrides[get_settings] = lambda: tiny_settings
    try:
        response = await client.post(
            f"/submissions/{submission['id']}/documents",
            files={"file": ("application.pdf", VALID_PDF_BYTES, "application/pdf")},
            headers={"X-CSRF-Token": auth_body["csrf_token"]},
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 413


async def test_download_returns_original_bytes(client: AsyncClient) -> None:
    auth_body = await _register(client, email="uw6@example.com", organisation_name="Acme6")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])
    upload_response = await client.post(
        f"/submissions/{submission['id']}/documents",
        files={"file": ("application.pdf", VALID_PDF_BYTES, "application/pdf")},
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )
    document_id = upload_response.json()["id"]

    response = await client.get(f"/documents/{document_id}/content")

    assert response.status_code == 200
    assert response.content == VALID_PDF_BYTES
    assert response.headers["content-type"] == "application/pdf"


async def test_viewer_cannot_upload_document(
    client: AsyncClient, second_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_body = await _register(client, email="admin@example.com", organisation_name="Acme7")
    submission = await _create_submission(client, csrf_token=admin_body["csrf_token"])
    organisation_id = admin_body["active_organisation_id"]

    viewer = await UserRepository(db_session).create(
        email="viewer2@example.com", full_name="Viewer", password_hash=hash_password(PASSWORD)
    )
    await OrganisationMembershipRepository(db_session).create(
        organisation_id=uuid.UUID(organisation_id), user_id=viewer.id, role=MembershipRole.VIEWER
    )

    login_response = await second_client.post(
        "/auth/login", json={"email": "viewer2@example.com", "password": PASSWORD}
    )
    assert login_response.status_code == 200
    csrf_token = login_response.json()["csrf_token"]

    response = await second_client.post(
        f"/submissions/{submission['id']}/documents",
        files={"file": ("application.pdf", VALID_PDF_BYTES, "application/pdf")},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 403


async def test_user_cannot_download_other_org_document(
    client: AsyncClient, second_client: AsyncClient
) -> None:
    auth_body = await _register(client, email="a3@example.com", organisation_name="Org A3")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])
    upload_response = await client.post(
        f"/submissions/{submission['id']}/documents",
        files={"file": ("application.pdf", VALID_PDF_BYTES, "application/pdf")},
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )
    document_id = upload_response.json()["id"]

    await _register(second_client, email="b3@example.com", organisation_name="Org B3")

    response = await second_client.get(f"/documents/{document_id}/content")

    assert response.status_code == 404
