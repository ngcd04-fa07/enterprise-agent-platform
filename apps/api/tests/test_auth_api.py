from typing import Any

from httpx import AsyncClient

REGISTER_PASSWORD = "correct horse battery staple"


async def _register(client: AsyncClient, *, email: str = "owner@example.com") -> dict[str, Any]:
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "full_name": "Owner",
            "password": REGISTER_PASSWORD,
            "organisation_name": "Acme Insurance",
        },
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_register_creates_session_cookie_and_active_organisation(
    client: AsyncClient,
) -> None:
    body = await _register(client)

    assert body["user"]["email"] == "owner@example.com"
    assert body["active_organisation_id"] is not None
    assert "session_token" in client.cookies


async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    await _register(client)

    response = await client.post(
        "/auth/register",
        json={
            "email": "owner@example.com",
            "full_name": "Someone Else",
            "password": "another-strong-password",
            "organisation_name": "Other Org",
        },
    )

    assert response.status_code == 409


async def test_login_succeeds_with_correct_password(client: AsyncClient) -> None:
    await _register(client)
    client.cookies.clear()

    response = await client.post(
        "/auth/login", json={"email": "owner@example.com", "password": REGISTER_PASSWORD}
    )

    assert response.status_code == 200
    assert "session_token" in client.cookies


async def test_login_rejects_wrong_password(client: AsyncClient) -> None:
    await _register(client)
    client.cookies.clear()

    response = await client.post(
        "/auth/login", json={"email": "owner@example.com", "password": "wrong password"}
    )

    assert response.status_code == 401


async def test_login_rejects_unknown_email(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )

    assert response.status_code == 401


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401


async def test_me_returns_current_user_and_admin_membership(client: AsyncClient) -> None:
    await _register(client)

    response = await client.get("/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "owner@example.com"
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["role"] == "admin"


async def test_logout_requires_csrf_token(client: AsyncClient) -> None:
    await _register(client)

    response = await client.post("/auth/logout")

    assert response.status_code == 403


async def test_logout_revokes_session(client: AsyncClient) -> None:
    body = await _register(client)

    response = await client.post(
        "/auth/logout", headers={"X-CSRF-Token": body["csrf_token"]}
    )
    assert response.status_code == 204

    me_response = await client.get("/auth/me")
    assert me_response.status_code == 401
