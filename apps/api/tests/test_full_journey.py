"""One end-to-end test walking the full user journey through the HTTP API in
a single flow, mirroring what Stage 7's browser verification exercised
manually: register -> create a submission -> upload a PDF -> confirm it's
parsed, chunked and searchable -> log out -> confirm the session is gone.

The per-feature test modules (test_auth_api.py, test_document_ingestion_api.py,
test_search_api.py, ...) already cover edge cases and failure paths in
isolation; this test exists to catch integration breaks between those pieces
that per-feature tests, each starting from a fresh registration, cannot see.
"""

from httpx import AsyncClient

from tests.pdf_fixtures import build_minimal_pdf

PASSWORD = "correct horse battery staple"


async def test_full_user_journey(client: AsyncClient) -> None:
    register_response = await client.post(
        "/auth/register",
        json={
            "email": "journey@example.com",
            "full_name": "Journey User",
            "password": PASSWORD,
            "organisation_name": "Journey Insurance",
        },
    )
    assert register_response.status_code == 201, register_response.text
    auth_body = register_response.json()
    csrf_token = auth_body["csrf_token"]
    assert "session_token" in client.cookies

    submission_response = await client.post(
        "/submissions",
        json={"title": "Q3 Renewal"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert submission_response.status_code == 201, submission_response.text
    submission_id = submission_response.json()["id"]

    pdf = build_minimal_pdf(["Revenue grew by twelve percent this quarter."])
    upload_response = await client.post(
        f"/submissions/{submission_id}/documents",
        files={"file": ("financials.pdf", pdf, "application/pdf")},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert upload_response.status_code == 201, upload_response.text
    document_id = upload_response.json()["id"]
    assert upload_response.json()["status"] == "ready"

    documents_response = await client.get(f"/submissions/{submission_id}/documents")
    assert documents_response.status_code == 200
    documents = documents_response.json()
    assert len(documents) == 1
    assert documents[0]["id"] == document_id
    assert documents[0]["status"] == "ready"

    pages_response = await client.get(f"/documents/{document_id}/pages")
    assert pages_response.status_code == 200
    assert "Revenue grew" in pages_response.json()[0]["text"]

    search_response = await client.post(
        f"/submissions/{submission_id}/search",
        json={"query": "Revenue grew by twelve percent this quarter."},
    )
    assert search_response.status_code == 200
    search_body = search_response.json()
    assert len(search_body["results"]) == 1
    assert search_body["results"][0]["document_id"] == document_id
    assert search_body["results"][0]["page_number"] == 1

    me_response = await client.get("/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["user"]["email"] == "journey@example.com"

    logout_response = await client.post("/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert logout_response.status_code == 204

    me_after_logout = await client.get("/auth/me")
    assert me_after_logout.status_code == 401

    search_after_logout = await client.post(
        f"/submissions/{submission_id}/search", json={"query": "anything"}
    )
    assert search_after_logout.status_code == 401
