# Enterprise Agent Platform

A production-oriented agentic AI platform for evidence-grounded,
high-consequence document workflows. Fictional use case: commercial
insurance underwriting document intelligence.

Full engineering rules for this repo live in [CLAUDE.md](CLAUDE.md).
Architecture decisions and rationale live in
[docs/architecture.md](docs/architecture.md).

## Capabilities

Only checked once actually implemented and verified in this repo.

- [ ] Multi-tenant architecture
- [ ] RBAC
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

**Status:** Stage 1 (development environment) — in progress.

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

The backend (FastAPI app, config, health endpoint, tests) has been installed
and run in this development environment: `ruff`, `mypy --strict`, and
`pytest` all pass. The frontend and the Docker Compose stack (Postgres +
pgvector, API container, web container) have been written against known-good
Next.js 15 / Docker conventions but have **not** been run end-to-end here —
this environment has no Node.js or Docker available. Run `docker compose up
--build` locally to verify the full stack; report back anything that fails
so it can be fixed.

## Limitations

This is Stage 1 of an intentionally staged build. No auth, tenant model,
document ingestion, retrieval, or agent workflow exists yet — see the
roadmap table in [docs/architecture.md](docs/architecture.md).
