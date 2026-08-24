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
- [x] Document ingestion
- [x] Minimal end-to-end frontend (register/login, submissions, upload, search)
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
- [x] CI/CD

**Status:** Stage 8 (First milestone hardening) — done. One end-to-end
integration test walks the full user journey through the HTTP API, and CI
now genuinely verifies the system: it runs real migrations before the test
suite (a gap that had silently broken every CI run since Stage 6 — see
below) and builds + boots the full docker-compose stack on every push.
[Run 32779644596](https://github.com/ngcd04-fa07/enterprise-agent-platform/actions/runs/32779644596)
is the first fully green CI run in this project's history — all three jobs
(backend, docker-compose, frontend) passed.

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
- All four Alembic migrations (`0001_initial_schema`,
  `0002_add_authentication`, `0003_add_pages_and_chunks`,
  `0004_add_chunk_embeddings`) apply cleanly against real Postgres, and an
  `alembic revision --autogenerate` afterward produces an empty diff each
  time — proof the hand-written migrations exactly match the SQLAlchemy
  models, not just "look right."
- All 65 backend tests pass against real Postgres, including both
  cross-tenant-denial tests (`test_user_cannot_read_other_org_submission`,
  `test_user_cannot_modify_other_org_submission`), an RBAC test proving a
  viewer role is rejected from write endpoints, document upload/download
  tests (valid PDF accepted, wrong content-type/oversized/content-type
  mismatch all rejected, cross-org download denied), PDF ingestion tests
  (correct per-page text extraction, chunk provenance, an unparseable PDF
  ending up `failed` rather than crashing the upload), and search tests
  against the real embedding model.
- A live docker-compose upload of a real 2-page PDF confirmed correct
  extracted text and page ordering end to end.
- A live docker-compose **semantic** search check — not exact-text
  matching — is the strongest proof point so far: querying "how much did
  revenue grow" against three unrelated sentences (revenue, headcount,
  office location) correctly ranked the revenue sentence highest
  (score 0.73 vs. 0.63 and 0.48), using the real local embedding model
  against real pgvector.
- Manual checks confirm the session cookie is `HttpOnly` with no `Secure`
  flag in development (would otherwise silently block the cookie over
  plain HTTP), CSRF is enforced in both directions (missing token → 403,
  correct token → success), and the raw session token never appears in a
  response body or server log — only its HMAC lives in the database.
- One end-to-end integration test (`test_full_journey.py`) walks the full
  HTTP flow in a single test — register, create a submission, upload a PDF,
  confirm it's parsed/chunked/searchable, log out, confirm the session is
  gone — catching integration breaks between features that per-feature
  tests can't see.
- CI now actually runs migrations before the test suite (see the CI bug
  below) and builds + boots the full docker-compose stack, polling
  `/health` and the web app's landing page, on every push and PR.
- A live docker-compose check — register, create a submission, upload a
  real PDF, download it back, restart the API container, download again —
  confirmed uploaded documents are genuinely durable on the storage volume,
  not just cached in the running process.
- A full real-browser walkthrough against the docker-compose stack (Stage 7):
  register → create a submission → upload a real PDF → status reaches
  "ready" with no manual refresh → a semantic, non-exact-match search query
  returns correctly-ranked results with page number and score shown →
  log out → redirected to `/login` → a fresh, logged-out browser session
  navigating directly to a protected route is redirected rather than shown
  stale or broken data.

Real bugs have been caught this way four times now, all invisible to
mypy, ruff, and a "green" test suite (DB tests correctly skip without
Postgres): Stage 2's enum `.name` vs `.value` persistence bug, a Stage 5
bug where an expired `updated_at` after an UPDATE crashed every document
upload (`MissingGreenlet` from an implicit lazy-refresh on a synchronous
attribute access), a Stage 6 bug where a hand-created HNSW index
existed in the migration but not the SQLAlchemy model, so autogenerate's
drift-check — the thing meant to catch exactly this class of mistake —
would have proposed dropping it, a Stage 7 bug where Next.js bakes its
`rewrites()` proxy destination into the build output at `next build` time,
so the web Dockerfile needed `API_ORIGIN` passed as a build arg (not just a
runtime env var) for the docker-compose service-to-service origin to take
effect, and a Stage 8 bug where CI's Postgres service had never had
migrations applied, so the `vector` Postgres extension didn't exist and
every test touching `document_chunks` had been silently erroring in CI
since Stage 6 — invisible locally because local/remote verification always
ran against a docker-compose Postgres that already had migrations applied.
See `docs/architecture.md` for all five — they're the concrete reason this
project treats "tests pass" as meaningless without a real database (and,
now, a real browser, and a real from-scratch CI run) behind it.

## Limitations

This is Stage 8 of an intentionally staged build. No lexical/hybrid
retrieval or reranking exists yet (Stage 10), and no structured extraction
or agentic underwriting workflow exists yet — see the roadmap table in
[docs/architecture.md](docs/architecture.md).
