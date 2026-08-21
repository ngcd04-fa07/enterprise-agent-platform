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

**Status:** Stage 5 (Parsing/chunking) — done. Document ingestion isn't
checked above yet — upload, PDF parsing, chunking, and provenance all
exist, but embeddings/vector retrieval (Stage 6) don't, so nothing is
searchable yet.

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
- All three Alembic migrations (`0001_initial_schema`,
  `0002_add_authentication`, `0003_add_pages_and_chunks`) apply cleanly
  against real Postgres, and an `alembic revision --autogenerate` afterward
  produces an empty diff each time — proof the hand-written migrations
  exactly match the SQLAlchemy models, not just "look right."
- All 55 backend tests pass against real Postgres, including both
  cross-tenant-denial tests (`test_user_cannot_read_other_org_submission`,
  `test_user_cannot_modify_other_org_submission`), an RBAC test proving a
  viewer role is rejected from write endpoints, document upload/download
  tests (valid PDF accepted, wrong content-type/oversized/content-type
  mismatch all rejected, cross-org download denied), and PDF ingestion
  tests (correct per-page text extraction, chunk provenance, an
  unparseable PDF ending up `failed` rather than crashing the upload).
- A live docker-compose upload of a real 2-page PDF confirmed correct
  extracted text and page ordering end to end.
- Manual checks confirm the session cookie is `HttpOnly` with no `Secure`
  flag in development (would otherwise silently block the cookie over
  plain HTTP), CSRF is enforced in both directions (missing token → 403,
  correct token → success), and the raw session token never appears in a
  response body or server log — only its HMAC lives in the database.
- A live docker-compose check — register, create a submission, upload a
  real PDF, download it back, restart the API container, download again —
  confirmed uploaded documents are genuinely durable on the storage volume,
  not just cached in the running process.

Real bugs have been caught this way twice now, both invisible to mypy,
ruff, and a "green" test suite (DB tests correctly skip without Postgres):
Stage 2's enum `.name` vs `.value` persistence bug, and a Stage 5 bug
where an expired `updated_at` after an UPDATE crashed every document
upload (`MissingGreenlet` from an implicit lazy-refresh on a synchronous
attribute access). See `docs/architecture.md` for both — they're the
concrete reason this project treats "tests pass" as meaningless without a
real database behind it.

## Limitations

This is Stage 5 of an intentionally staged build. Documents are uploaded,
parsed page-by-page, and chunked with provenance, but nothing is
searchable yet — no embeddings, vector index, or retrieval exists
(Stage 6), no agent workflow exists, and the frontend has no UI yet beyond
the Stage 1 health check (Stage 7) — see the roadmap table in
[docs/architecture.md](docs/architecture.md).
