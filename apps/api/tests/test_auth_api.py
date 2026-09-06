from typing import Any

from httpx import AsyncClient

from app.core.config import get_settings

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

    response = await client.post("/auth/logout", headers={"X-CSRF-Token": body["csrf_token"]})
    assert response.status_code == 204

    me_response = await client.get("/auth/me")
    assert me_response.status_code == 401


async def test_login_flood_eventually_returns_429_with_retry_after(client: AsyncClient) -> None:
    """Stage 20: a wrong-password flood must eventually be throttled, not
    processed forever — every attempt still gets a real password
    verification up to that point (see AuthService.login's timing-safe
    design), so this also proves the limiter check runs before that cost
    is paid indefinitely.

    Every attempt here targets the same account from the same (test)
    client IP, so the tighter per-(IP, identifier) bucket is the one that
    actually trips — not the more permissive per-IP bucket, which is
    sized for "how much login traffic can one source generate at all,"
    not "how many guesses against one account." See test_rate_limiter.py
    for the pure-logic proof that a *different* IP guessing the same
    email is an entirely separate bucket (an attacker can't lock out a
    victim this way).
    """
    await _register(client)
    client.cookies.clear()
    max_attempts = get_settings().login_rate_limit_per_identifier_max_attempts

    responses = [
        await client.post(
            "/auth/login", json={"email": "owner@example.com", "password": "wrong password"}
        )
        for _ in range(max_attempts + 1)
    ]

    assert all(r.status_code == 401 for r in responses[:max_attempts])
    last = responses[-1]
    assert last.status_code == 429
    assert "Retry-After" in last.headers
    assert int(last.headers["Retry-After"]) > 0


async def test_register_flood_eventually_returns_429(client: AsyncClient) -> None:
    max_attempts = get_settings().register_rate_limit_per_ip_max_attempts

    responses = []
    for i in range(max_attempts + 1):
        responses.append(
            await client.post(
                "/auth/register",
                json={
                    "email": f"flood{i}@example.com",
                    "full_name": "Flood",
                    "password": REGISTER_PASSWORD,
                    "organisation_name": f"Flood Org {i}",
                },
            )
        )

    assert all(r.status_code == 201 for r in responses[:max_attempts])
    assert responses[-1].status_code == 429
    assert "Retry-After" in responses[-1].headers
