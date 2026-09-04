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


async def _extract(client: AsyncClient, *, submission_id: str, csrf_token: str) -> dict[str, Any]:
    response = await client.post(
        f"/submissions/{submission_id}/extract", headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_triage_with_complete_fields_recommends_approve(
    client: AsyncClient, llm_gateway: FakeLLMGateway
) -> None:
    page_text = (
        "Submission for Acme Roofing Co. Business description: commercial roofing. "
        "Requested effective date 2026-01-01. Requested limit $1,000,000. "
        "Submitted by broker Coastal Insurance Brokers."
    )
    llm_gateway.responses[page_text] = {
        "named_insured": "Acme Roofing Co.",
        "business_description": "commercial roofing",
        "requested_effective_date": "2026-01-01",
        "requested_coverage_limit": "$1,000,000",
        "broker_or_agent_name": "Coastal Insurance Brokers",
    }
    llm_gateway.default_response = {"summary": "Submission appears complete and in good order."}

    auth_body = await _register(client, email="ag1@example.com", organisation_name="Acme")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])
    pdf = build_minimal_pdf([page_text])
    await _upload(
        client, submission_id=submission["id"], csrf_token=auth_body["csrf_token"], pdf=pdf
    )
    await _extract(client, submission_id=submission["id"], csrf_token=auth_body["csrf_token"])

    response = await client.post(
        f"/submissions/{submission['id']}/agent-runs",
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["recommendation"] == "approve"
    assert body["summary"] == "Submission appears complete and in good order."
    assert body["requires_human_approval"] is True
    assert body["approved_at"] is None
    tool_names = [call["tool_name"] for call in body["tool_calls"]]
    assert tool_names == [
        "gather_evidence",
        "read_extracted_fields",
        "apply_underwriting_rules",
        "synthesize_summary",
    ]
    assert [call["sequence_index"] for call in body["tool_calls"]] == [1, 2, 3, 4]


async def test_triage_with_missing_named_insured_recommends_refer(
    client: AsyncClient, llm_gateway: FakeLLMGateway
) -> None:
    page_text = "This document mentions nothing about who the applicant is."
    llm_gateway.default_response = {"summary": "Named insured is missing."}

    auth_body = await _register(client, email="ag2@example.com", organisation_name="Acme2")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])
    pdf = build_minimal_pdf([page_text])
    await _upload(
        client, submission_id=submission["id"], csrf_token=auth_body["csrf_token"], pdf=pdf
    )
    await _extract(client, submission_id=submission["id"], csrf_token=auth_body["csrf_token"])

    response = await client.post(
        f"/submissions/{submission['id']}/agent-runs",
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )

    assert response.status_code == 201
    assert response.json()["recommendation"] == "refer"


async def test_triage_with_no_documents_recommends_refer_and_flags_no_evidence(
    client: AsyncClient, llm_gateway: FakeLLMGateway
) -> None:
    llm_gateway.default_response = {"summary": "No documentation on file."}

    auth_body = await _register(client, email="ag3@example.com", organisation_name="Acme3")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    response = await client.post(
        f"/submissions/{submission['id']}/agent-runs",
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["recommendation"] == "refer"
    evidence_call = body["tool_calls"][0]
    assert evidence_call["tool_name"] == "gather_evidence"
    assert '"chunk_count": 0' in evidence_call["output_summary"]


async def test_failed_synthesis_produces_failed_run_with_no_recommendation(
    client: AsyncClient, llm_gateway: FakeLLMGateway
) -> None:
    llm_gateway.should_fail = True

    auth_body = await _register(client, email="ag4@example.com", organisation_name="Acme4")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    response = await client.post(
        f"/submissions/{submission['id']}/agent-runs",
        headers={"X-CSRF-Token": auth_body["csrf_token"]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert body["recommendation"] is None
    assert body["summary"] is None
    assert body["error_message"] is not None
    # The first three deterministic steps still ran and were logged before
    # the LLM call failed — only synthesize_summary is missing.
    tool_names = [call["tool_name"] for call in body["tool_calls"]]
    assert tool_names == ["gather_evidence", "read_extracted_fields", "apply_underwriting_rules"]


async def test_admin_can_approve_a_run(client: AsyncClient, llm_gateway: FakeLLMGateway) -> None:
    llm_gateway.default_response = {"summary": "ok"}
    auth_body = await _register(client, email="ag5@example.com", organisation_name="Acme5")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])
    run = (
        await client.post(
            f"/submissions/{submission['id']}/agent-runs",
            headers={"X-CSRF-Token": auth_body["csrf_token"]},
        )
    ).json()

    response = await client.post(
        f"/agent-runs/{run['id']}/approve", headers={"X-CSRF-Token": auth_body["csrf_token"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approved_at"] is not None


async def test_underwriter_cannot_approve_a_run(
    client: AsyncClient, second_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_body = await _register(client, email="ag6@example.com", organisation_name="Acme6")
    organisation_id = admin_body["active_organisation_id"]
    submission = await _create_submission(client, csrf_token=admin_body["csrf_token"])
    run = (
        await client.post(
            f"/submissions/{submission['id']}/agent-runs",
            headers={"X-CSRF-Token": admin_body["csrf_token"]},
        )
    ).json()

    underwriter = await UserRepository(db_session).create(
        email="ag6-uw@example.com", full_name="Underwriter", password_hash=hash_password(PASSWORD)
    )
    await OrganisationMembershipRepository(db_session).create(
        organisation_id=uuid.UUID(organisation_id),
        user_id=underwriter.id,
        role=MembershipRole.UNDERWRITER,
    )
    login_response = await second_client.post(
        "/auth/login", json={"email": "ag6-uw@example.com", "password": PASSWORD}
    )
    csrf_token = login_response.json()["csrf_token"]

    response = await second_client.post(
        f"/agent-runs/{run['id']}/approve", headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 403


async def test_viewer_cannot_trigger_a_triage_run(
    client: AsyncClient, second_client: AsyncClient, db_session: AsyncSession
) -> None:
    admin_body = await _register(client, email="ag7@example.com", organisation_name="Acme7")
    organisation_id = admin_body["active_organisation_id"]
    submission = await _create_submission(client, csrf_token=admin_body["csrf_token"])

    viewer = await UserRepository(db_session).create(
        email="ag7-viewer@example.com", full_name="Viewer", password_hash=hash_password(PASSWORD)
    )
    await OrganisationMembershipRepository(db_session).create(
        organisation_id=uuid.UUID(organisation_id), user_id=viewer.id, role=MembershipRole.VIEWER
    )
    login_response = await second_client.post(
        "/auth/login", json={"email": "ag7-viewer@example.com", "password": PASSWORD}
    )
    csrf_token = login_response.json()["csrf_token"]

    response = await second_client.post(
        f"/submissions/{submission['id']}/agent-runs", headers={"X-CSRF-Token": csrf_token}
    )

    assert response.status_code == 403


async def test_agent_run_requires_csrf_token(client: AsyncClient) -> None:
    auth_body = await _register(client, email="ag8@example.com", organisation_name="Acme8")
    submission = await _create_submission(client, csrf_token=auth_body["csrf_token"])

    response = await client.post(f"/submissions/{submission['id']}/agent-runs")

    assert response.status_code == 403


async def test_agent_run_requires_submission_in_own_organisation(
    client: AsyncClient, second_client: AsyncClient, llm_gateway: FakeLLMGateway
) -> None:
    llm_gateway.default_response = {"summary": "ok"}
    org_a_body = await _register(client, email="ag9a@example.com", organisation_name="Org A")
    submission = await _create_submission(client, csrf_token=org_a_body["csrf_token"])
    run = (
        await client.post(
            f"/submissions/{submission['id']}/agent-runs",
            headers={"X-CSRF-Token": org_a_body["csrf_token"]},
        )
    ).json()

    org_b_body = await _register(second_client, email="ag9b@example.com", organisation_name="Org B")

    trigger_response = await second_client.post(
        f"/submissions/{submission['id']}/agent-runs",
        headers={"X-CSRF-Token": org_b_body["csrf_token"]},
    )
    list_response = await second_client.get(f"/submissions/{submission['id']}/agent-runs")
    get_response = await second_client.get(f"/agent-runs/{run['id']}")
    approve_response = await second_client.post(
        f"/agent-runs/{run['id']}/approve", headers={"X-CSRF-Token": org_b_body["csrf_token"]}
    )

    assert trigger_response.status_code == 404
    assert list_response.status_code == 404
    assert get_response.status_code == 404
    # org_b_body's user is an admin of their own org (registering always
    # creates the user as admin), so this clears RBAC and hits tenant
    # isolation instead — 404, not 403.
    assert approve_response.status_code == 404
