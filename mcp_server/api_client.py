"""Thin HTTP client wrapping the real Enterprise Agent Platform API. Every
method here is a straight pass-through to an existing, already-secured
endpoint — no new trust decision exists at this layer. Authentication is
a real session obtained through the real /auth/login flow (see login.py),
so every call is subject to exactly the same tenant-scoping and RBAC
enforcement as a browser session — an MCP client can never do anything
the underlying session's role couldn't already do over HTTP.
"""

from typing import Any

import httpx


class ApiError(Exception):
    """Raised with a message meant to be read directly by whoever is
    driving the MCP client (a person, or a model relaying it to one) —
    not a raw HTTP status code.
    """


class UnderwritingApiClient:
    def __init__(
        self,
        *,
        base_url: str,
        session_token: str,
        csrf_token: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # transport is a test-only seam (httpx.MockTransport) — production
        # callers never pass it, so real traffic always goes over the
        # network via httpx's default transport.
        self._client = httpx.AsyncClient(
            base_url=base_url,
            cookies={"session_token": session_token},
            headers={"X-CSRF-Token": csrf_token},
            timeout=30.0,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._client.request(method, path, **kwargs)
        if response.status_code == 401:
            raise ApiError("Session expired or invalid — run login.py again to get a fresh one.")
        if response.status_code == 403:
            raise ApiError("This user's role doesn't permit that action.")
        if response.status_code == 404:
            raise ApiError("Not found — it may not exist, or belongs to a different organisation.")
        if response.status_code >= 400:
            raise ApiError(f"API request failed ({response.status_code}): {response.text}")
        if response.status_code == 204:
            return None
        return response.json()

    async def list_submissions(self) -> list[dict[str, Any]]:
        result = await self._request("GET", "/submissions")
        return list(result)

    async def get_submission(self, submission_id: str) -> dict[str, Any]:
        result = await self._request("GET", f"/submissions/{submission_id}")
        return dict(result)

    async def search_submission(
        self, submission_id: str, *, query: str, limit: int = 10
    ) -> dict[str, Any]:
        result = await self._request(
            "POST",
            f"/submissions/{submission_id}/search",
            json={"query": query, "limit": limit},
        )
        return dict(result)

    async def get_extraction(self, submission_id: str) -> dict[str, Any]:
        result = await self._request("GET", f"/submissions/{submission_id}/extraction")
        return dict(result)

    async def list_agent_runs(self, submission_id: str) -> list[dict[str, Any]]:
        result = await self._request("GET", f"/submissions/{submission_id}/agent-runs")
        return list(result)

    async def get_agent_run(self, agent_run_id: str) -> dict[str, Any]:
        result = await self._request("GET", f"/agent-runs/{agent_run_id}")
        return dict(result)

    async def trigger_triage(self, submission_id: str) -> dict[str, Any]:
        result = await self._request("POST", f"/submissions/{submission_id}/agent-runs")
        return dict(result)

    async def approve_agent_run(self, agent_run_id: str) -> dict[str, Any]:
        result = await self._request("POST", f"/agent-runs/{agent_run_id}/approve")
        return dict(result)
