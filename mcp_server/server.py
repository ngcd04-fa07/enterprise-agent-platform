"""MCP server exposing the Enterprise Agent Platform's existing,
already-secured capabilities as tools — search, extraction/triage
results, and (role-permitting) triggering a new triage run or approving
one. Every tool is a thin wrapper over api_client.py, which calls the
real running API with a real session obtained via login.py — there is no
new auth mechanism and no new trust decision here: an MCP client can
never do anything the underlying session's role couldn't already do over
HTTP. See README.md for setup and docs/architecture.md for the design
rationale (why an MCP server, not a client, for Stage 13).

Run with: python3 server.py  (stdio transport — see README.md for how to
point Claude Desktop / Claude Code at it).
"""

import os
from typing import Any

from mcp.server.mcpserver import MCPServer

from api_client import UnderwritingApiClient

_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
_SESSION_TOKEN = os.environ["SESSION_TOKEN"]  # fails loudly if missing — see login.py
_CSRF_TOKEN = os.environ["CSRF_TOKEN"]

server = MCPServer(
    name="enterprise-agent-platform",
    instructions=(
        "Tools for the Enterprise Agent Platform (commercial insurance "
        "underwriting). Every tool acts as the currently logged-in user "
        "and organisation — it cannot see or affect any other "
        "organisation's data, and write actions are still subject to "
        "that user's role."
    ),
)

_client = UnderwritingApiClient(
    base_url=_API_BASE_URL, session_token=_SESSION_TOKEN, csrf_token=_CSRF_TOKEN
)


@server.tool()
async def list_submissions() -> list[dict[str, Any]]:
    """List all submissions in the current user's organisation."""
    return await _client.list_submissions()


@server.tool()
async def get_submission(submission_id: str) -> dict[str, Any]:
    """Get one submission's details by id."""
    return await _client.get_submission(submission_id)


@server.tool()
async def search_submission(submission_id: str, query: str, limit: int = 10) -> dict[str, Any]:
    """Hybrid (semantic + lexical) search over a submission's documents.
    Returns ranked chunks with page-level provenance.
    """
    return await _client.search_submission(submission_id, query=query, limit=limit)


@server.tool()
async def get_extraction(submission_id: str) -> dict[str, Any]:
    """Get the current structured-extraction results (named insured,
    coverage limit, etc.) for a submission, each with its source page.
    """
    return await _client.get_extraction(submission_id)


@server.tool()
async def list_agent_runs(submission_id: str) -> list[dict[str, Any]]:
    """List all underwriting-triage runs for a submission, most recent
    first.
    """
    return await _client.list_agent_runs(submission_id)


@server.tool()
async def get_agent_run(agent_run_id: str) -> dict[str, Any]:
    """Get one triage run's recommendation, summary, and full tool-call
    audit trail.
    """
    return await _client.get_agent_run(agent_run_id)


@server.tool()
async def trigger_triage(submission_id: str) -> dict[str, Any]:
    """Run underwriting triage on a submission: gathers evidence, reads
    extracted fields, applies deterministic rules, and produces a
    recommendation with a plain-English summary. Requires an
    admin/underwriter role — the agent never decides on its own to skip
    that check. Every run always requires separate human approval before
    it's considered reviewed.
    """
    return await _client.trigger_triage(submission_id)


@server.tool()
async def approve_agent_run(agent_run_id: str) -> dict[str, Any]:
    """Record human approval of a triage run's recommendation. Requires
    an admin role. Approving does not change the submission's status by
    itself — that remains a separate, deliberate action.
    """
    return await _client.approve_agent_run(agent_run_id)


if __name__ == "__main__":
    server.run(transport="stdio")
