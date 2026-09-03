# Enterprise Agent Platform

**A production-oriented, agentic AI platform for evidence-grounded, high-consequence document workflows.**
Fictional use case: commercial insurance underwriting document intelligence — every AI finding traces back to a source document, page, and chunk.

[![CI](https://github.com/ngcd04-fa07/enterprise-agent-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/ngcd04-fa07/enterprise-agent-platform/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?logo=postgresql&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

---

## Why this exists

Most AI demo projects stop at "call the model and print the answer." This one is built to demonstrate the engineering that has to exist *around* the model in a real product: multi-tenant data isolation, provenance-backed retrieval, typed and validated tool calls, a real Postgres schema with migrations, and a CI pipeline that's actually been made to fail and then fixed — not just written and assumed to work.

It's built as a staged, reviewable roadmap (Stage 0 → Stage 21), currently through **Stage 9 of 21** — auth/RBAC through a working end-to-end retrieval UI, hardened with CI and a full-journey integration test, now with the first real LLM integration: schema-validated structured extraction from a local, open-source model. Hybrid retrieval, agentic workflows, MCP tool integrations, and observability are the next stages.

## Table of contents

- [Architecture](#architecture)
- [Engineering highlights](#engineering-highlights)
- [Capabilities](#capabilities)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Repository layout](#repository-layout)
- [Verification & testing](#verification--testing)
- [Documentation](#documentation)
- [Limitations](#limitations)

## Architecture

```mermaid
flowchart LR
    subgraph Client
        Browser
    end

    subgraph "apps/web — Next.js"
        UI["React UI\n(login · submissions · upload · search)"]
    end

    subgraph "apps/api — FastAPI (modular monolith)"
        Auth["Auth / RBAC\ncookie session + CSRF"]
        Sub["Submissions"]
        Ing["Ingestion\nparse → chunk → embed"]
        Ret["Retrieval\nvector search"]
        Ext["Extraction\nper-chunk structured output"]
    end

    subgraph Storage
        PG[("PostgreSQL\n+ pgvector (HNSW)")]
        FS[("Object storage\n(filesystem, swappable)")]
        EMB["Local embedding model\n(fastembed, no API key)"]
        LLM["Local LLM via Ollama\n(qwen2.5:3b, no API key)"]
    end

    Browser -->|"same-origin /api/*"| UI
    UI -->|HttpOnly cookie session| Auth
    Auth --> Sub
    Sub --> Ing
    Ing --> FS
    Ing --> EMB
    Ing --> PG
    Sub --> Ret
    Ret --> PG
    Sub --> Ext
    Ext --> LLM
    Ext --> PG

    style PG fill:#4169E1,color:#fff
    style EMB fill:#009688,color:#fff
    style LLM fill:#009688,color:#fff
```

Every arrow into Postgres carries `organisation_id` scoping enforced at the **repository layer**, not just the route — cross-tenant access fails even against a correctly-guessed UUID. See [Engineering highlights](#engineering-highlights).

## Engineering highlights

What this project is actually meant to demonstrate, beyond "it works":

- **Tenant isolation enforced in SQL, not in the UI.** Every query touching submissions, documents, pages, or vector chunks filters `organisation_id` inside the `WHERE` clause — including the pgvector similarity search itself. Backed by explicit cross-tenant-denial tests, not just code review.
- **Provenance is structural, not cosmetic.** Every chunk carries `document_id` / `page_id` / `submission_id` / `organisation_id`; every search result can be traced back to an exact page.
- **Security-conscious auth by default.** Argon2id password hashing, HMAC-hashed session tokens (never stored raw), `HttpOnly` cookies, double-submit CSRF on every state-changing route, server-derived organisation/role on every request — no client-supplied `organisation_id` or `role` is ever trusted.
- **Deterministic-first.** Chunking, validation, and provenance are plain code, not LLM calls. Extraction provenance in particular is never *asked* of the model — each field is extracted one chunk at a time, so the source chunk is always the one actually being read, not a citation that needs a trust-but-verify check.
- **Verification over vibes.** Every stage has been checked against a *real* Postgres instance, a *real* embedding model, and now a *real* local LLM — not just a green test suite. This discipline has caught seven real, reproducible bugs invisible to `mypy`/`ruff`/a passing local test run, plus honest reporting of a real model-reliability gap (a 3B local model correctly extracted 3 of 5 target fields from a test submission, with zero hallucinated values). Full writeups in [`docs/architecture.md`](docs/architecture.md).
- **No hidden provider coupling.** LLM and embedding calls are abstracted behind a gateway interface — swapping providers touches one file, not business logic.

## Capabilities

Only checked once actually implemented **and verified** in this repo — see [Verification & testing](#verification--testing).

| | Capability |
|---|---|
| ✅ | Multi-tenant architecture (org-scoped, enforced server-side) |
| ✅ | RBAC (admin / underwriter / reviewer / viewer) |
| ✅ | Document ingestion (PDF → pages → chunks, with provenance) |
| ✅ | Vector search (pgvector, HNSW, real semantic-not-exact-match verified) |
| ✅ | End-to-end frontend (register, login, submissions, upload, search) |
| ✅ | CI/CD (lint, types, tests, Docker build & boot, on every push) |
| ✅ | Structured extraction (local open-source LLM, per-chunk, deterministic provenance) |
| ⬜ | Hybrid (lexical + vector) retrieval |
| ⬜ | Evidence-level citations in the UI |
| ⬜ | Agentic underwriting workflow |
| ⬜ | Human approval / review queue |
| ⬜ | MCP integrations |
| ⬜ | Permission-aware tool calling |
| ⬜ | AI tracing / observability |
| ⬜ | Automated evaluation harness |
| ⬜ | Model routing |

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2.x (async) | Typed end-to-end, async-native, no framework magic hiding the SQL |
| Database | PostgreSQL + pgvector (HNSW, cosine) | One source of truth for relational *and* vector data — no separate vector DB to keep in sync |
| Embeddings | `fastembed` (local ONNX, `bge-small-en-v1.5`) | Real semantic search with zero API key / external dependency |
| LLM (structured extraction) | Ollama, `qwen2.5:3b` (local, open-source) | Real schema-validated generation with zero API key / per-call cost |
| Auth | Argon2id + HMAC-hashed cookie sessions + CSRF | No JWT-in-localStorage XSS surface; server-side revocation |
| Frontend | Next.js 15 (App Router) + TypeScript | Same-origin API proxy keeps the session cookie first-party |
| Migrations | Alembic (async), autogenerate-diff-verified | Every migration checked to produce an empty diff against the models |
| CI/CD | GitHub Actions | Lint, types, tests against real Postgres, full Docker Compose boot — every push |

## Quick start

Requires Docker and Docker Compose. (Backend can also run standalone with Python 3.12+; frontend standalone with Node 22+.) Structured extraction additionally needs [Ollama](https://ollama.com) running locally (`ollama serve`) with a model pulled (`ollama pull qwen2.5:3b`) — everything else works without it; extraction just returns a clean `"failed"` status until it's available. See `.env.example` for `OLLAMA_BASE_URL`/`OLLAMA_MODEL`.

```bash
git clone https://github.com/ngcd04-fa07/enterprise-agent-platform.git
cd enterprise-agent-platform
cp .env.example .env   # fill in SESSION_SECRET and Postgres credentials
docker compose up --build
```

- API: [http://localhost:8000/health](http://localhost:8000/health)
- Web: [http://localhost:3000](http://localhost:3000)

<details>
<summary><strong>Backend only</strong></summary>

```bash
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
mypy app
pytest
```

</details>

<details>
<summary><strong>Frontend only</strong></summary>

```bash
cd apps/web
npm install
npm run lint
npm run typecheck
npm run build
```

</details>

## Repository layout

```
apps/api/     FastAPI backend — routes → services → repositories → models
apps/web/     Next.js (App Router, TypeScript) frontend
docs/         Architecture decisions, rationale, verification log
.github/      CI workflows
docker-compose.yml
```

## Verification & testing

**Status:** Stage 9 (Structured extraction) — done. 82 backend tests pass against a real Postgres instance, CI builds and boots the full Docker Compose stack on every push ([latest green run](https://github.com/ngcd04-fa07/enterprise-agent-platform/actions/workflows/ci.yml)), and the full user journey (register → submission → upload → parse → chunk → embed → search → extract → logout) has been walked both by automated tests and live against a real local LLM. Stage 8 also passed a release-candidate audit of Stages 1-8 before Stage 9 began; see [`docs/architecture.md`](docs/architecture.md) for the full writeup.

<details>
<summary><strong>Full verification log — what was actually run, and seven real bugs it caught</strong></summary>

- Backend: `ruff`, `ruff format --check`, `mypy --strict`, and `pytest` all pass.
- Frontend: `npm run lint`, `npm run typecheck`, and `npm run build` all pass.
- Full Docker Compose stack: `docker compose up --build` brings up Postgres (healthy), the API, and the web app end to end.
- All five Alembic migrations apply cleanly against real Postgres, and `alembic revision --autogenerate` afterward produces an empty diff every time — proof the hand-written migrations exactly match the SQLAlchemy models.
- All 82 backend tests pass against real Postgres, including cross-tenant-denial tests at both the HTTP layer and the repository layer (two real organisations' data present simultaneously, proving the SQL filter itself — not just an earlier ownership check), an RBAC test proving a viewer role is rejected from write endpoints, document upload/download validation tests, PDF ingestion tests (per-page extraction, chunk provenance, graceful failure on an unparseable PDF, atomicity on partial failure), search bounding/validation tests, search tests against the real embedding model, and extraction tests (merge-order/provenance proof, failed-run field preservation) against both a fake and the real Ollama model.
- A live Docker Compose **semantic** search check — not exact-text matching — is the strongest single proof point for retrieval: querying *"how much did revenue grow"* against three unrelated sentences correctly ranked the revenue sentence highest (score 0.73 vs. 0.63 and 0.48), using the real local embedding model against real pgvector.
- A live end-to-end **structured extraction** check against the real local LLM (not the fake): a realistic 2-page underwriting submission correctly yielded 3 of 5 target fields — broker name, business description, coverage limit — each verbatim and citing the exact correct source page, with zero hallucinated values, confirmed via `GET /submissions/{id}/extraction` and direct `psql` inspection of the persisted rows.
- A live two-organisation attack test against the running Docker Compose stack (not the test suite): a real second organisation's session, holding real UUIDs from the first, was denied on every read/write path tried (submissions, documents, pages, content, search) — all `404`, no existence leak — while a search for the first org's exact text run inside the second org's own submission returned zero results.
- Manual checks confirm the session cookie is `HttpOnly`, CSRF is enforced in both directions, and the raw session token never appears in a response body or log — only its HMAC lives in the database.
- A live Docker Compose durability check — upload, download, restart the API container, download again — confirmed uploaded documents persist on the storage volume, not just in-process memory.
- A full real-browser walkthrough against the Docker Compose stack: register → create a submission → upload a real PDF → status reaches "ready" with no manual refresh → a semantic, non-exact-match search returns correctly-ranked results with page number and score → log out → redirected to `/login` → direct navigation to a protected route while logged out redirects, no stale data.

**Real bugs caught by insisting on a real database, a real browser, and a release-candidate audit instead of trusting a green test suite:**

1. A SQLAlchemy `Enum` column persisting `.name` instead of `.value`.
2. An expired `updated_at` after an `UPDATE` crashing every document upload (`MissingGreenlet`).
3. A hand-created pgvector HNSW index that existed in the migration but not the SQLAlchemy model — autogenerate's own drift-check would have proposed dropping it.
4. Next.js baking its `rewrites()` proxy destination into the build output at *build* time, so the Docker build needed `API_ORIGIN` passed as a build arg, not just a runtime env var.
5. CI's Postgres service never had migrations applied, so the `vector` extension didn't exist and every chunk-related test had been silently erroring in CI since Stage 6 — invisible locally because every manual verification ran against a Postgres that already had migrations applied.
6. A failed document ingestion could leave partially-persisted `DocumentPage`/`DocumentChunk` rows committed alongside the `failed` status — reproduced directly, fixed with a SAVEPOINT around the parse/chunk/embed block.
7. A file could be orphaned on disk if the database row failed to persist after a successful storage write — reproduced directly (forced an FK violation), fixed with a compensating delete.

Full writeups of all seven: [`docs/architecture.md`](docs/architecture.md).

</details>

## Documentation

- [`CLAUDE.md`](CLAUDE.md) — the durable engineering constitution (architecture principles, security rules, workflow discipline) this repo is built under.
- [`docs/architecture.md`](docs/architecture.md) — decision log, roadmap status table, and every bug found in verification, with root cause and fix.

## Limitations

This is Stage 9 of an intentionally staged 21-stage build. No lexical/hybrid retrieval or reranking exists yet (Stage 10), and no agentic underwriting workflow exists yet — see the roadmap table in [`docs/architecture.md`](docs/architecture.md). Structured extraction targets a small, fixed set of fields (not open-ended extraction), runs synchronously per request (same tradeoff as document ingestion), and — being a local 3B-parameter model rather than a frontier one — correctly leaves a field null more often than a hosted model would, at the benefit of never fabricating a value. Ollama isn't containerized in Docker Compose (see the LLM provider decision in `docs/architecture.md`), so extraction only works end-to-end via the native (non-Docker) dev flow unless you separately point `OLLAMA_BASE_URL` at a reachable instance.
