from typing import Any

import pytest
from httpx import AsyncClient

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


async def test_search_returns_exact_text_match_as_top_result(client: AsyncClient) -> None:
    """FakeEmbeddingProvider is deterministic per exact text, so querying
    with text identical to a stored chunk gives distance 0 / score 1.0 —
    a clean, deterministic wiring assertion without needing real semantic
    embeddings (those are covered in test_fastembed_provider.py).
    """
    auth_body = await _register(client, email="s1@example.com", organisation_name="Acme")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])
    pdf = build_minimal_pdf(["The quick brown fox jumps over the lazy dog."])
    await _upload(
        client, submission_id=submission["id"], csrf_token=auth_body["csrf_token"], pdf=pdf
    )

    response = await client.post(
        f"/submissions/{submission['id']}/search",
        json={"query": "The quick brown fox jumps over the lazy dog."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["strategy"] == "vector"
    assert len(body["results"]) == 1
    top = body["results"][0]
    assert "quick brown fox" in top["text"]
    assert top["page_number"] == 1
    assert top["score"] == pytest.approx(1.0, abs=1e-6)


async def test_search_with_no_documents_returns_empty_results(client: AsyncClient) -> None:
    auth_body = await _register(client, email="s4@example.com", organisation_name="Acme4")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    response = await client.post(
        f"/submissions/{submission['id']}/search", json={"query": "anything"}
    )

    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_search_requires_submission_in_own_organisation(
    client: AsyncClient, second_client: AsyncClient
) -> None:
    auth_body = await _register(client, email="s2@example.com", organisation_name="Org A")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    await _register(second_client, email="s3@example.com", organisation_name="Org B")

    response = await second_client.post(
        f"/submissions/{submission['id']}/search", json={"query": "anything"}
    )

    assert response.status_code == 404
