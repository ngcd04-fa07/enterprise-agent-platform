import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password
from app.models.membership import MembershipRole
from app.repositories.membership_repository import OrganisationMembershipRepository
from app.repositories.user_repository import UserRepository
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


async def test_extraction_merges_first_non_null_value_per_field_with_provenance(
    client: AsyncClient, llm_gateway: FakeLLMGateway
) -> None:
    """Two chunks (one per page): page 1 names the insured but not the
    broker, page 2 names the broker and repeats a *different* named_insured
    value. The merged result must take named_insured from page 1 (first
    chunk order wins) and broker_or_agent_name from page 2, each citing
    its own source page — proving both the merge order and provenance are
    correct, not just that some value came back.
    """
    page_1_text = "Submission for Acme Roofing Co."
    page_2_text = "Submitted by broker Jane Doe Insurance, re-confirming Acme Roofing Co."
    llm_gateway.responses[page_1_text] = {"named_insured": "Acme Roofing Co."}
    llm_gateway.responses[page_2_text] = {
        "named_insured": "WRONG - should not win",
        "broker_or_agent_name": "Jane Doe Insurance",
    }

    auth_body = await _register(client, email="ex1@example.com", organisation_name="Acme")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])
    pdf = build_minimal_pdf([page_1_text, page_2_text])
    await _upload(
        client, submission_id=submission["id"], csrf_token=auth_body["csrf_token"], pdf=pdf
    )

    response = await client.post(
        f"/submissions/{submission['id']}/extract",
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "succeeded"
    fields_by_name = {f["field_name"]: f for f in body["fields"]}

    assert fields_by_name["named_insured"]["value"] == "Acme Roofing Co."
    assert fields_by_name["named_insured"]["source_page_number"] == 1
    assert fields_by_name["broker_or_agent_name"]["value"] == "Jane Doe Insurance"
    assert fields_by_name["broker_or_agent_name"]["source_page_number"] == 2
    assert "business_description" not in fields_by_name


async def test_get_extraction_before_any_run_returns_not_run(client: AsyncClient) -> None:
    auth_body = await _register(client, email="ex2@example.com", organisation_name="Acme2")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    response = await client.get(f"/submissions/{submission['id']}/extraction")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_run"
    assert body["fields"] == []


async def test_extraction_with_no_documents_succeeds_with_no_fields(client: AsyncClient) -> None:
    auth_body = await _register(client, email="ex3@example.com", organisation_name="Acme3")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    response = await client.post(
        f"/submissions/{submission['id']}/extract",
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["fields"] == []


async def test_failed_extraction_preserves_previous_fields(
    client: AsyncClient, llm_gateway: FakeLLMGateway
) -> None:
    """A run that fails (model unreachable / bad output) must not wipe out
    fields a previous successful run already found — see
    ExtractionService's except branch, which returns early before ever
    calling delete_for_submission.
    """
    page_text = "Submission for Acme Roofing Co."
    llm_gateway.responses[page_text] = {"named_insured": "Acme Roofing Co."}

    auth_body = await _register(client, email="ex4@example.com", organisation_name="Acme4")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])
    pdf = build_minimal_pdf([page_text])
    await _upload(
        client, submission_id=submission["id"], csrf_token=auth_body["csrf_token"], pdf=pdf
    )

    first = await client.post(
        f"/submissions/{submission['id']}/extract",
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "succeeded"
    assert len(first.json()["fields"]) == 1

    llm_gateway.should_fail = True
    second = await client.post(
        f"/submissions/{submission['id']}/extract",
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )

    assert second.status_code == 200
    assert second.json()["status"] == "failed"
    assert len(second.json()["fields"]) == 1
    assert second.json()["fields"][0]["value"] == "Acme Roofing Co."


async def test_extraction_requires_csrf_token(client: AsyncClient) -> None:
    auth_body = await _register(client, email="ex5@example.com", organisation_name="Acme5")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    response = await client.post(f"/submissions/{submission['id']}/extract")

    assert response.status_code == 403


async def test_viewer_cannot_trigger_extraction(
    client: AsyncClient, second_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_body = await _register(client, email="ex6@example.com", organisation_name="Acme6")
    organisation_id = admin_body["active_organisation_id"]
    submission = await _create_submission(client, csrf_token=admin_body["csrf_token"])

    viewer = await UserRepository(db_session).create(
        email="ex6-viewer@example.com", full_name="Viewer", password_hash=hash_password(PASSWORD)
    )
    await OrganisationMembershipRepository(db_session).create(
        organisation_id=uuid.UUID(organisation_id), user_id=viewer.id, role=MembershipRole.VIEWER
    )
    login_response = await second_client.post(
        "/auth/login", json={"email": "ex6-viewer@example.com", "password": PASSWORD}
    )
    csrf_token = login_response.json()["csrf_token"]

    response = await second_client.post(
        f"/submissions/{submission['id']}/extract", headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 403


async def test_extraction_requires_submission_in_own_organisation(
    client: AsyncClient, second_client: AsyncClient
) -> None:
    org_a_body = await _register(client, email="ex7a@example.com", organisation_name="Org A")
    submission = await _create_submission(client, csrf_token=org_a_body["csrf_token"])

    org_b_body = await _register(second_client, email="ex7b@example.com", organisation_name="Org B")

    extract_response = await second_client.post(
        f"/submissions/{submission['id']}/extract",
        headers={"X-CSRF-Token": org_b_body["csrf_token"]},
    )
    get_response = await second_client.get(f"/submissions/{submission['id']}/extraction")

    assert extract_response.status_code == 404
    assert get_response.status_code == 404
