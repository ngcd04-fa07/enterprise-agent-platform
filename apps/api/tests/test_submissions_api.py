import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password
from app.models.membership import MembershipRole
from app.repositories.membership_repository import OrganisationMembershipRepository
from app.repositories.user_repository import UserRepository

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


async def _create_submission(
    client: AsyncClient, *, csrf_token: str, title: str = "Q3 Renewal"
) -> dict[str, Any]:
    response = await client.post(
        "/submissions", json={"title": title}, headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_create_submission_requires_csrf_token(client: AsyncClient) -> None:
    await _register(client, email="uw@example.com", organisation_name="Acme")

    response = await client.post("/submissions", json={"title": "No CSRF"})

    assert response.status_code == 403


async def test_admin_can_create_and_list_submissions(client: AsyncClient) -> None:
    body = await _register(client, email="admin@example.com", organisation_name="Acme")
    created = await _create_submission(client, csrf_token=body["csrf_token"])

    list_response = await client.get("/submissions")

    assert list_response.status_code == 200
    titles = [s["title"] for s in list_response.json()]
    assert created["title"] in titles


async def test_viewer_cannot_create_submission(
    client: AsyncClient, second_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_body = await _register(client, email="admin2@example.com", organisation_name="Acme 2")
    organisation_id = admin_body["active_organisation_id"]

    viewer = await UserRepository(db_session).create(
        email="viewer@example.com", full_name="Viewer", password_hash=hash_password(PASSWORD)
    )
    await OrganisationMembershipRepository(db_session).create(
        organisation_id=uuid.UUID(organisation_id), user_id=viewer.id, role=MembershipRole.VIEWER
    )

    login_response = await second_client.post(
        "/auth/login", json={"email": "viewer@example.com", "password": PASSWORD}
    )
    assert login_response.status_code == 200
    csrf_token = login_response.json()["csrf_token"]

    response = await second_client.post(
        "/submissions", json={"title": "Viewer attempt"}, headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 403


async def test_user_cannot_read_other_org_submission(
    client: AsyncClient, second_client: AsyncClient
) -> None:
    org_a_body = await _register(client, email="a@example.com", organisation_name="Org A")
    submission = await _create_submission(client, csrf_token=org_a_body["csrf_token"])

    await _register(second_client, email="b@example.com", organisation_name="Org B")

    response = await second_client.get(f"/submissions/{submission['id']}")

    assert response.status_code == 404


async def test_user_cannot_modify_other_org_submission(
    client: AsyncClient, second_client: AsyncClient
) -> None:
    org_a_body = await _register(client, email="a2@example.com", organisation_name="Org A2")
    submission = await _create_submission(client, csrf_token=org_a_body["csrf_token"])

    org_b_body = await _register(second_client, email="b2@example.com", organisation_name="Org B2")

    response = await second_client.patch(
        f"/submissions/{submission['id']}",
        json={"title": "Hijacked"},
        headers={"X-CSRF-Token": org_b_body["csrf_token"]},
    )

    assert response.status_code == 404
