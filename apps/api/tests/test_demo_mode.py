"""Tests the public-demo guardrails: registration disabled, and a tight
per-IP rate limit on the two routes that actually spend LLM tokens
(extraction, triage). Both are no-ops unless Settings.demo_mode is on —
proven here by overriding get_settings for the duration of one test, the
same pattern test_documents_api.py uses for max_upload_size_bytes.
"""

from typing import Any

from httpx import AsyncClient

from app.core.config import get_settings
from app.main import app
from tests.fake_llm_gateway import FakeLLMGateway
from tests.pdf_fixtures import build_minimal_pdf

PASSWORD = "correct horse battery staple"


async def _register(client: AsyncClient, *, email: str, organisation_name: str) -> dict[str, Any]:
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


async def _upload(
    client: AsyncClient, *, submission_id: str, csrf_token: str, pdf: bytes
) -> dict[str, Any]:
    response = await client.post(
        f"/submissions/{submission_id}/documents",
        files={"file": ("doc.pdf", pdf, "application/pdf")},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_registration_is_disabled_when_demo_mode_is_on(client: AsyncClient) -> None:
    demo_settings = get_settings().model_copy(update={"demo_mode": True})
    app.dependency_overrides[get_settings] = lambda: demo_settings
    try:
        response = await client.post(
            "/auth/register",
            json={
                "email": "visitor@example.com",
                "full_name": "Visitor",
                "password": PASSWORD,
                "organisation_name": "Should Not Be Created",
            },
        )
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 403


async def test_registration_still_works_when_demo_mode_is_off(client: AsyncClient) -> None:
    await _register(client, email="normal@example.com", organisation_name="Acme")


async def test_extraction_trigger_is_rate_limited_in_demo_mode(
    client: AsyncClient, llm_gateway: FakeLLMGateway
) -> None:
    llm_gateway.responses["some text"] = {"named_insured": "Acme Roofing Co."}

    auth_body = await _register(client, email="demo1@example.com", organisation_name="Acme")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])
    pdf = build_minimal_pdf(["some text"])
    await _upload(
        client, submission_id=submission["id"], csrf_token=auth_body["csrf_token"], pdf=pdf
    )

    # The rate limiter's own threshold is read from the real, un-overridden
    # get_settings() singleton (a module-level lru_cache, not the FastAPI
    # DI override below) — see app/security/demo_guard.py. Only demo_mode
    # itself is meaningfully overridable here, so this floods the real
    # configured count rather than trying to shrink it, same as
    # test_auth_api.py's login/register flood tests do for their limiters.
    max_attempts = get_settings().demo_llm_rate_limit_per_ip_max_attempts
    demo_settings = get_settings().model_copy(update={"demo_mode": True})
    app.dependency_overrides[get_settings] = lambda: demo_settings
    try:
        responses = [
            await client.post(
                f"/submissions/{submission['id']}/extract",
                headers={"X-CSRF-Token": auth_body["csrf_token"]},
            )
            for _ in range(max_attempts + 1)
        ]
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert all(r.status_code == 200 for r in responses[:max_attempts]), responses[0].text
    assert responses[-1].status_code == 429
    assert "Retry-After" in responses[-1].headers


async def test_agent_run_trigger_is_rate_limited_in_demo_mode(
    client: AsyncClient, llm_gateway: FakeLLMGateway
) -> None:
    llm_gateway.default_response = {"summary": "No documentation on file."}

    auth_body = await _register(client, email="demo2@example.com", organisation_name="Acme")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    max_attempts = get_settings().demo_llm_rate_limit_per_ip_max_attempts
    demo_settings = get_settings().model_copy(update={"demo_mode": True})
    app.dependency_overrides[get_settings] = lambda: demo_settings
    try:
        responses = [
            await client.post(
                f"/submissions/{submission['id']}/agent-runs",
                headers={"X-CSRF-Token": auth_body["csrf_token"]},
            )
            for _ in range(max_attempts + 1)
        ]
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert all(r.status_code == 201 for r in responses[:max_attempts]), responses[0].text
    assert responses[-1].status_code == 429
    assert "Retry-After" in responses[-1].headers
