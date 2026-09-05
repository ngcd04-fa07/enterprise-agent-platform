# Enterprise Agent Platform — MCP server

Exposes this platform's existing, already-secured API as MCP tools —
search, view extraction/triage results, and (role-permitting) trigger a
new triage run or approve one — so an MCP client (Claude Desktop, Claude
Code, or anything else that speaks MCP) can act on submissions on a real
user's behalf.

## Why this isn't a bypass of the app's own security

Every tool in `server.py` is a thin wrapper (`api_client.py`) around a
real HTTP call to the real running API, authenticated with a real session
obtained through the real `/auth/login` flow (see `login.py`). There is
no separate "MCP service account" or alternate auth path — an MCP client
can never do anything the underlying session's role couldn't already do
in the browser. Tenant isolation and RBAC are inherited unchanged from
the API itself; this layer makes zero new trust decisions. See
`docs/architecture.md`'s Stage 13 decision for the full reasoning
(including why this project chose to expose itself as an MCP *server*
rather than make its agent an MCP *client*).

## Setup

Requires a running instance of the API (`docker compose up` from the
repo root, or the native `apps/api` dev flow).

```bash
cd mcp_server
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Get a real session (you'll need an existing account — register one
through the web app or `POST /auth/register` first):

```bash
python3 login.py --api-base-url http://localhost:8000 --email you@example.com
```

This prints `SESSION_TOKEN` and `CSRF_TOKEN` — set both, along with
`API_BASE_URL`, as environment variables for whatever launches
`server.py`. For Claude Desktop/Code, that means adding an entry to its
MCP server config, e.g.:

```json
{
  "mcpServers": {
    "enterprise-agent-platform": {
      "command": "/absolute/path/to/mcp_server/.venv/bin/python3",
      "args": ["/absolute/path/to/mcp_server/server.py"],
      "env": {
        "API_BASE_URL": "http://localhost:8000",
        "SESSION_TOKEN": "<from login.py>",
        "CSRF_TOKEN": "<from login.py>"
      }
    }
  }
}
```

Sessions expire the same way a browser session would — re-run `login.py`
for fresh tokens when they do.

## Tools

| Tool | Role required | What it does |
|---|---|---|
| `list_submissions` | any | List submissions in the current organisation |
| `get_submission` | any | Get one submission's details |
| `search_submission` | any | Hybrid (semantic + lexical) search with page-level provenance |
| `get_extraction` | any | Current structured-extraction results |
| `list_agent_runs` | any | List triage runs for a submission |
| `get_agent_run` | any | One triage run's recommendation, summary, and audit trail |
| `trigger_triage` | admin / underwriter | Run a new underwriting-triage pass |
| `approve_agent_run` | admin | Record human approval of a triage run |

"Role required" is enforced by the underlying API, not by this server —
listed here for reference, not because this layer checks it itself.

## Testing

```bash
pytest
```

Unit tests (`tests/test_api_client.py`) verify request/response mapping
against a mocked transport — no live API needed. Real end-to-end behavior
(a real login, a real submission, every tool called for real against a
running API, cross-tenant denial, and MCP-level error handling) was
verified manually; see `docs/architecture.md` for what was checked.
