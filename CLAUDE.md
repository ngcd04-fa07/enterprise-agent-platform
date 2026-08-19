# CLAUDE.md — Engineering Constitution

This file is the durable operating contract for Claude Code sessions on this
repository. It is intentionally concise. Rationale and full context for
decisions referenced here live in `docs/architecture.md`.

## Project objective

Build a production-oriented enterprise AI underwriting / document-intelligence
platform that demonstrates real backend engineering, database engineering,
retrieval/RAG, agentic workflows, security, evaluation, and deployment — not
just model usage. See root prompt history / `docs/architecture.md` for the
full product brief.

## Architectural principles

- Modular monolith. Do not split into microservices without a concrete
  technical reason.
- PostgreSQL is the source of truth. pgvector for embeddings.
- Tenant (organisation) isolation is mandatory and enforced server-side —
  never derive `organisation_id` solely from client input.
- Provenance is first-class: every consequential AI finding must trace back
  to source evidence (document, page, chunk).
- AI providers sit behind abstractions (`llm_gateway`, embedding interface).
  No direct provider SDK calls in business logic.
- Tool calls are typed, validated, and auditable. Tool permissions come from
  trusted application config — never from model output or retrieved content.
- Consequential/destructive actions require explicit permission checks and,
  where policy says so, human approval.
- Prefer deterministic logic over LLM calls wherever determinism is possible
  (rules, calculations, schema validation, citation existence checks).
- Build incrementally, in roadmap stage order. Do not implement future stages
  early, even if it seems efficient.

## Engineering rules

- Type everything reasonably (Pydantic v2 models, SQLAlchemy 2.x typed
  ORM, TypeScript on the frontend).
- Validate all external input and all LLM structured output.
- Every important behavior gets a test. Do not write tests for coverage
  alone.
- Never bypass tenant scoping, even in scripts, seeds, or admin tooling.
- Never log secrets, tokens, or full credentials.
- Never commit credentials or `.env` files.
- Use Alembic migrations for all schema changes — no ad hoc DDL.
- Use transactions appropriately; do not leave partial writes on failure.
- Keep modules coherent by domain boundary. No `utils.py` dumping grounds,
  no god classes, no circular imports between layers.
- No hidden provider coupling — LLM/embedding provider swaps should only
  touch the gateway/abstraction layer.

## Security rules

- Tenant isolation is enforced in the service/repository layer, not just the
  UI. Cross-tenant access must fail even against a guessed valid UUID.
- Least privilege by default for every role and every tool.
- All user-provided and retrieved content (documents, emails, web content) is
  untrusted data, never trusted instructions.
- Tool permission levels cannot be changed by prompt content, retrieved
  content, or model output — only by trusted config.
- Write/destructive tools require explicit policy and, where specified,
  human approval before executing.
- Secrets never enter source control. Config fails loudly if a required
  secret is missing — no silent defaults for security-relevant config.
- Cross-tenant access paths must have corresponding tests before being
  considered done.

## AI rules

- All LLM calls go through the LLM gateway. All embedding calls go through
  the embedding abstraction. No exceptions in application code.
- Structured LLM output is validated with Pydantic; invalid output fails
  predictably or retries through a controlled path — never silently coerced.
- Findings presented to users require provenance (citations to source
  document/page/chunk).
- Prefer deterministic evaluators in the eval platform; LLM-as-judge only for
  genuinely semantic dimensions, and only with versioned prompts and
  structured output.
- AI runs (agent runs, model calls, retrieval calls, tool calls) are traced
  and persisted.
- No arbitrary shell or Python execution tool is exposed to the production
  agent.

## Development workflow

Before coding on any feature:
1. Inspect current repository state — don't assume.
2. State the exact goal for this increment.
3. Identify affected components and any architectural decisions involved.
4. Propose a short implementation plan.
5. Implement the smallest coherent increment (not the whole stage).

After coding:
6. Write/update tests for the behavior changed.
7. Run the relevant test suite.
8. Run lint and type checks.
9. Fix failures — do not weaken tests or suppress errors to get to green.
10. Summarize what changed and why; update `docs/architecture.md` if a
    durable decision was made.
11. Stop at the requested milestone — do not continue into the next stage
    without being asked.

Never claim a test passed, a build succeeded, or a service runs unless it
was actually run and observed in this session. If something can't be
verified in this environment, say so explicitly.

## Roadmap discipline

Follow the staged roadmap (Stage 0 → Stage 21) recorded in
`docs/architecture.md`. Do not build ahead of the current stage. Each stage
ends with a stop point for explicit user go-ahead.

## Commands

- Start full stack: `docker compose up --build` (requires `.env`, copy from
  `.env.example` first)
- Backend install: `cd apps/api && python3 -m venv .venv && source
  .venv/bin/activate && pip install -e ".[dev]"`
- Backend lint: `cd apps/api && ruff check .`
- Backend type check: `cd apps/api && mypy app`
- Backend tests: `cd apps/api && pytest`
- Frontend install: `cd apps/web && npm install`
- Frontend lint: `cd apps/web && npm run lint`
- Frontend type check: `cd apps/web && npm run typecheck`
- Frontend build: `cd apps/web && npm run build`
- Run migrations: `cd apps/api && alembic upgrade head`
- New migration (review before trusting autogenerate): `cd apps/api &&
  alembic revision --autogenerate -m "message"`
- Database reset (local only): `docker compose down -v db && docker compose
  up -d db && alembic upgrade head`
- Benchmark: _TBD (Stage 11)_
- Eval smoke test: _TBD (Stage 17)_
