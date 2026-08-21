# Enterprise Agent Platform

A production-oriented agentic AI platform for evidence-grounded,
high-consequence document workflows. Fictional use case: commercial
insurance underwriting document intelligence.

Full engineering rules for this repo live in [CLAUDE.md](CLAUDE.md).
Architecture decisions and rationale live in
[docs/architecture.md](docs/architecture.md).

## Capabilities

Only checked once actually implemented and verified in this repo.

- [x] Multi-tenant architecture
- [x] RBAC
- [ ] Document ingestion
- [ ] Hybrid retrieval
- [ ] Structured extraction
- [ ] Evidence-level citations
- [ ] Agentic underwriting workflow
- [ ] Human approval / review
- [ ] MCP integrations
- [ ] Permission-aware tools
- [ ] AI tracing / observability
- [ ] Automated evaluation
- [ ] Regression testing
- [ ] Model routing
- [ ] CI/CD

**Status:** Stage 3 (Auth/RBAC) — done.

## Repository layout

```
apps/api/     FastAPI backend
apps/web/     Next.js (App Router, TypeScript) frontend
docs/         Architecture, threat model, evaluation docs
.github/      CI workflows
docker-compose.yml
```

## Local development

Requires Docker and Docker Compose. Backend can also run standalone with
Python 3.12+; frontend standalone with Node 22+.

```bash
cp .env.example .env   # fill in SESSION_SECRET and Postgres credentials
docker compose up --build
```

- API: http://localhost:8000/health
- Web: http://localhost:3000

### Backend only

```bash
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
mypy app
pytest
```

### Frontend only

```bash
cd apps/web
npm install
npm run lint
npm run typecheck
npm run build
```

## Verification status

Everything below has actually been run, not just written and assumed
correct:

- Backend: `ruff`, `mypy --strict`, and `pytest` all pass.
- Frontend: `npm run lint`, `npm run typecheck`, and `npm run build` all
  pass.
- Full Docker Compose stack: `docker compose up --build` brings up Postgres
  (healthy), the API, and the web app; `GET /health` and the web app's
  server-rendered health display both confirm real db → api → web wiring.
- Both Alembic migrations (`0001_initial_schema`, `0002_add_authentication`)
  apply cleanly against real Postgres, and an `alembic revision
  --autogenerate` afterward produces an empty diff — proof the hand-written
  migrations exactly match the SQLAlchemy models, not just "look right."
- All 31 backend tests pass against real Postgres, including both
  cross-tenant-denial tests (`test_user_cannot_read_other_org_submission`,
  `test_user_cannot_modify_other_org_submission`) and an RBAC test proving a
  viewer role is rejected from write endpoints.
- Manual checks confirm the session cookie is `HttpOnly` with no `Secure`
  flag in development (would otherwise silently block the cookie over
  plain HTTP), CSRF is enforced in both directions (missing token → 403,
  correct token → success), and the raw session token never appears in a
  response body or server log — only its HMAC lives in the database.

A real bug was caught this way during Stage 2: SQLAlchemy was persisting
enum `.name` (`"DRAFT"`) instead of `.value` (`"draft"`), which passed
`ruff`, `mypy`, and a "green" test suite (the DB tests correctly skip
without Postgres) before a real-Postgres run surfaced it. See
`docs/architecture.md` for the full account — it's the concrete reason
this project treats "tests pass" as meaningless without a real database
behind it.

## Limitations

This is Stage 3 of an intentionally staged build. No document ingestion,
retrieval, or agent workflow exists yet, and the frontend has no login UI
yet (Stage 7) — see the roadmap table in
[docs/architecture.md](docs/architecture.md).
