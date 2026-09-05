"""Verifies UnderwritingApiClient's request/response mapping against a
mocked transport — no real API server needed. Real end-to-end behavior
against the actual running API is verified manually (see
docs/architecture.md, MCP decision) since this is a small, standalone
dev tool without its own CI job.
"""

import json
from collections.abc import Callable

import httpx
import pytest

from api_client import ApiError, UnderwritingApiClient


def _client_with(
    handler: Callable[[httpx.Request], httpx.Response],
) -> UnderwritingApiClient:
    return UnderwritingApiClient(
        base_url="http://testserver",
        session_token="test-session-token",
        csrf_token="test-csrf-token",
        transport=httpx.MockTransport(handler),
    )


async def test_list_submissions_sends_get_with_session_cookie() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=[{"id": "abc", "title": "Test"}])

    client = _client_with(handler)
    result = await client.list_submissions()

    assert result == [{"id": "abc", "title": "Test"}]
    request = captured["request"]
    assert request.method == "GET"
    assert request.url.path == "/submissions"
    assert "session_token=test-session-token" in request.headers.get("cookie", "")


async def test_trigger_triage_sends_post_with_csrf_header() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(201, json={"id": "run-1", "status": "completed"})

    client = _client_with(handler)
    result = await client.trigger_triage("sub-1")

    assert result == {"id": "run-1", "status": "completed"}
    request = captured["request"]
    assert request.method == "POST"
    assert request.url.path == "/submissions/sub-1/agent-runs"
    assert request.headers.get("x-csrf-token") == "test-csrf-token"


async def test_search_submission_sends_query_and_limit_in_body() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"results": [], "strategy": "hybrid", "latency_ms": 1.0})

    client = _client_with(handler)
    await client.search_submission("sub-1", query="revenue growth", limit=5)

    body = json.loads(captured["body"])
    assert body == {"query": "revenue growth", "limit": 5}


@pytest.mark.parametrize(
    ("status_code", "expected_message_fragment"),
    [
        (401, "Session expired"),
        (403, "role doesn't permit"),
        (404, "Not found"),
    ],
)
async def test_error_status_codes_raise_readable_api_error(
    status_code: int, expected_message_fragment: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"detail": "irrelevant"})

    client = _client_with(handler)

    with pytest.raises(ApiError, match=expected_message_fragment):
        await client.get_submission("sub-1")


async def test_approve_agent_run_returns_parsed_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/agent-runs/run-1/approve"
        return httpx.Response(200, json={"id": "run-1", "approved_at": "2026-01-01T00:00:00Z"})

    client = _client_with(handler)
    result = await client.approve_agent_run("run-1")

    assert result["approved_at"] == "2026-01-01T00:00:00Z"
