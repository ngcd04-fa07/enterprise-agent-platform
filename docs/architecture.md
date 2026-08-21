# Architecture

Status labels used throughout this document and the README: **Implemented**,
**In progress**, **Planned**. Nothing below is marked Implemented until code
exists and has been run.

## System overview (target — Planned)

```mermaid
flowchart TD
    FE[Next.js / React frontend] --> API[FastAPI API]
    API --> AUTH[Auth / RBAC]
    API --> TENANT[Organisation / Tenant boundary]
    API --> SUB[Submission service]
    API --> ING[Document ingestion]
    ING --> STORE[Object storage abstraction]
    ING --> PARSE[Parsing / chunking / embeddings]
    API --> DB[(PostgreSQL + pgvector)]
    API --> RET[Retrieval: lexical / vector / hybrid / rerank]
    API --> AGENT[Underwriting workflow / agent]
    AGENT --> TOOLS[Typed tools / MCP]
    AGENT --> GATEWAY[LLM gateway]
    GATEWAY --> TRACE[Trace / observability]
    AGENT --> REVIEW[Human review]
    TRACE --> EVAL[Evaluation platform]
```

This is a **modular monolith**: one FastAPI application with clearly bounded
internal modules (`api/auth/core/db/models/schemas/repositories/services/
ingestion/retrieval/agents/tools/llm/evals/observability`), not separate
deployable services. Reconsider only if a concrete scaling or team boundary
forces it — not before.

---

## Decision: Repository layout

**Context.** Need a structure that scales through ~20 roadmap stages without
forcing premature service splits or empty placeholder packages.

**Options considered.**
- Single flat FastAPI app, no monorepo packages.
- Monorepo with `apps/api`, `apps/web`, and shared `packages/*`.
- Full microservices split per domain.

**Decision.** Monorepo: `apps/api` (FastAPI), `apps/web` (Next.js),
`packages/*` created only when a package has real shared consumers (e.g.
`agent_core`, `retrieval`, `llm_gateway` once both the API and eval/benchmark
tooling need to import them). `benchmarks/`, `infra/`, `docs/` at the root.

**Why.** Matches the target directory layout in the project brief, keeps
backend/frontend independently testable/deployable, and avoids microservice
operational overhead this project doesn't need.

**Consequences.** `packages/*` will start mostly empty and fill in from
Stage 9 onward (structured extraction) and Stage 11 (retrieval benchmark) —
we will not scaffold empty packages ahead of a real consumer.

---

## Decision: Authentication approach

**Context.** Need to choose between HTTP-only cookie sessions, stateless
JWT, or an external auth provider (Auth0/Clerk/etc.), evaluated against this
project's actual deployment topology, not FastAPI defaults.

**Options considered.**

| Option | CSRF | XSS exposure | Revocation | Local dev | Operational complexity |
|---|---|---|---|---|---|
| Server-side sessions, HTTP-only cookie | Needs same-site/CSRF token | Low (token never in JS) | Immediate (delete session row) | Simple | Low |
| Stateless JWT (Authorization header) | Not applicable | Higher if stored in localStorage; lower via memory-only | Hard without a revocation list (defeats "stateless" benefit) | Simple | Low, but revocation adds a store anyway |
| External auth provider (Auth0/Clerk) | Handled by provider | Depends on integration | Provider-managed | Extra service dependency | Higher; another vendor to configure/demo |

**Decision.** Server-side sessions via HTTP-only, `Secure`, `SameSite=Lax`
cookies, backed by a `sessions` table in PostgreSQL (session id, user id,
issued/expires, revoked flag). CSRF protection via a double-submit token on
state-changing requests.

**Why.** Confirmed deployment topology: frontend and API are served under
the same origin (Next.js rewrites / shared reverse proxy in prod, same-origin
in local dev). Under same-origin, cookie sessions are the simplest option
that is secure by construction — no token ever touches JavaScript (mitigates
XSS token theft), revocation is a single-row update (unlike JWT, which needs
its own denylist to revoke — at which point it isn't meaningfully simpler
than sessions), and `SameSite=Lax` + a CSRF token on mutating requests fully
covers CSRF for this topology without cross-origin CORS complexity. An
external provider is not justified: it adds a vendor dependency and setup
friction for a portfolio project without solving a problem session auth
doesn't already solve here.

If a genuinely separate-origin deployment is introduced later (e.g. a
separately hosted marketing site), this decision should be revisited — that
is a materially different threat/ops profile and is explicitly out of scope
until it's real.

**Consequences.** Authentication (who you are) is implemented via session
cookie + `sessions` table. Authorization (what you can do) is a fully
separate server-side check (RBAC + tenant scoping) evaluated on every
request — a valid session never implies access to a given resource.

---

## Decision: Object storage abstraction

**Context.** Need to store original uploaded documents (PDFs, spreadsheets)
separately from relational metadata, without coupling ingestion code to one
cloud SDK.

**Decision (interface only at this stage).** A small `ObjectStorage`
interface — `put_object`, `get_object`, `delete_object`,
`generate_access_url` — with a filesystem-backed implementation for local
dev and an S3-compatible implementation for deployment. Concrete
implementation lands in Stage 4 (Upload/storage), not now.

**Why.** Keeps ingestion/service code storage-agnostic; swapping filesystem
for S3-compatible storage should only touch the implementation, never
callers. Avoids introducing MinIO/AWS SDK dependencies before there's a real
upload path to exercise them.

**Stage 4 update — concrete implementation.** `FilesystemObjectStorage`
(`app/storage/filesystem.py`) is now real: keys are always server-generated
(`{organisation_id}/{uuid4()}.pdf`), never derived from a client filename,
and `_resolve_path` independently verifies every resolved path stays under
the storage root as defense in depth even though callers can't currently
supply an unsafe key. `put_object`/`get_object`/`delete_object` wrap
blocking file I/O in `asyncio.to_thread` so the async event loop is never
blocked — the interface is async throughout specifically so a future
`aioboto3`-backed S3 implementation is a drop-in swap.

`generate_access_url()` deliberately raises `NotImplementedError` for the
filesystem backend rather than returning something that looks like a URL
but isn't safely usable: there's no public object store to sign a URL
against yet, and building a fake local signing scheme just to satisfy the
interface shape would be exactly the kind of half-finished feature
`CLAUDE.md` warns against. Documents are instead served through the
authenticated `GET /documents/{id}/content` endpoint, which reuses the
existing session/RBAC/tenant checks — arguably a better safe-access story
for local dev than a bare signed URL would be anyway. This method becomes
meaningful once a real S3-compatible backend exists (Stage 21).

**MinIO was considered and rejected for now.** It would make presigned
URLs "real" locally, but adds a new docker-compose service and an AWS SDK
dependency to rehearse a code path (`generate_access_url`) that isn't
reachable from anywhere yet — no ingestion pipeline exists to consume a
document by URL rather than by direct `get_object` call. Revisit if/when
something actually needs an out-of-band URL rather than an authenticated
download.

---

## Decision: Multi-tenant isolation strategy

**Context.** Cross-tenant data leakage is the single highest-severity risk
class in this system (documents may contain sensitive financial data).

**Decision.** Application-layer enforcement first: every repository method
that reads/writes tenant-owned rows requires an `organisation_id` derived
from the authenticated session's active membership — never from a request
body/query param. Service layer never accepts a bare resource ID without
also checking it resolves within the caller's organisation. Row-Level
Security (RLS) in PostgreSQL is a **candidate defense-in-depth layer**,
deferred until the application-layer boundary is implemented and tested
(explicitly flagged in the brief as "evaluate later, don't introduce
automatically").

**Why.** Application-layer checks are necessary regardless of RLS (RLS
alone doesn't stop business-logic bugs like leaking a cross-tenant ID in an
API response), and are simpler to write tests against first. RLS adds real
value as a second layer but also adds operational complexity (session
variables per connection, policy maintenance) that isn't justified until the
first layer is proven and there's a concrete incident class it would catch
that tests aren't already catching.

**Consequences.** Every new tenant-owned model/endpoint must ship with at
least one cross-tenant-denial test before being considered done (see
`CLAUDE.md` security rules).

---

## Decision: Background job execution

**Status.** Still deferred through Stage 5. Per the brief, Celery/Redis
must not be introduced by default — and this is the section that decides
when something *is* introduced.

**Stage 5 consideration.** Ingestion (parse PDF → chunk → persist) now
does real work inside the upload request. `FastAPI BackgroundTasks` was
considered specifically for this, and rejected **for now**: making it
correct requires the background task to open its own DB session/
connection distinct from the request's — which is exactly right in
production, but breaks this project's test-isolation strategy (each test
runs inside an uncommitted, savepoint-backed transaction on one shared
connection; a background task's separate connection would never see that
transaction's writes, since Postgres only ever shows committed data across
connections). Solving that properly needs a dependency-injectable session
factory the test suite can override — real, buildable complexity, not
currently justified by what it protects: ingestion here is small
test/demo PDFs and pure-CPU parsing/chunking, genuinely fast.

**Decision.** Process synchronously within the upload request
(`IngestionService`, called directly from the upload route) until
something makes that a real problem — the leading candidate is Stage 6's
embedding API calls, which are genuinely slow and involve real network
I/O, unlike PDF parsing. At that point, compare `BackgroundTasks` (with
the session-factory-override work above), a DB-backed job table, and
Redis/RQ against actual latency numbers, not speculation.

---

## Decision: Stage 2 API surface — repositories/services now, HTTP endpoints deferred

**Context.** The roadmap lists "CRUD" under Stage 2 (core domain) but auth
under Stage 3. `CLAUDE.md` forbids trusting a client-supplied
`organisation_id`; tenant context must come from an authenticated session's
membership, which doesn't exist until Stage 3 wires up auth.

**Decision.** Stage 2 delivers models, an Alembic migration, and a fully
tested repository/service layer (`OrganisationService`,
`SubmissionService`, plus repositories for `Organisation`, `User`,
`OrganisationMembership`, `Submission`, `Document`). No HTTP endpoints are
exposed yet. `SubmissionRepository`/`SubmissionService` require
`organisation_id` as an explicit parameter on every read/write and return
the same "not found" outcome whether a submission doesn't exist or belongs
to a different organisation — this is exercised directly by
`test_tenant_isolation.py` at the service layer.

**Why.** Building a real HTTP CRUD API now would mean either accepting
`organisation_id` from the client (a security violation) or building a
throwaway auth shim that Stage 3 immediately replaces (a half-finished
implementation). Testing the isolation boundary at the service layer first
means Stage 3's auth work sits on top of a layer that already can't leak
across tenants, rather than being the only thing standing between a bug and
a data leak.

**Consequences.** Stage 3 exposes `POST/GET /submissions` etc. by wrapping
these services with a dependency that derives `organisation_id` from the
session — no new business logic, just wiring.

## Decision: User model excludes credentials; Document has no service yet

- `User` (Stage 2) has no password field. Credential storage belongs to
  Stage 3 (Auth/RBAC), which owns the authentication mechanism end to end.
- `Document` has a model + repository but no service/API. Real document
  creation needs the object storage abstraction (Stage 4) to produce a
  `storage_key`; wiring an endpoint that fakes that now would be a
  half-finished feature. The repository exists so Stage 4/5 build on an
  already-tested persistence layer.

## Decision: Alembic runs via the async template

Migrations use `async_engine_from_config` + `connection.run_sync(...)`
(Alembic's standard async template) against the same `asyncpg` driver the
app uses at runtime, rather than introducing a second sync driver
(e.g. psycopg) just for migrations. One less dependency, one connection
string, no behavioral gap between "how the app connects" and "how
migrations connect."

## Gotcha: pytest against a dev DB leaves `alembic_version` lying

If you run `pytest` (with `DATABASE_URL` pointed at your local dev
Postgres, e.g. via `docker compose up -d db`) and then try to use that
same database with a live `uvicorn`/docker-compose `api` process, you'll
hit `relation "users" does not exist` even though `alembic upgrade head`
reports the schema is already at head. Cause: `tests/conftest.py`'s
session-scoped `db_engine` fixture creates the schema with
`Base.metadata.create_all()` and tears it down with
`Base.metadata.drop_all()` — deliberately, for fast test isolation — but
`drop_all()` doesn't touch the `alembic_version` table (it isn't part of
`Base.metadata`), so Alembic is left believing the schema is current when
every domain table is actually gone. This is intentional test design, not
a bug — just run `docker compose down -v db && docker compose up -d db &&
alembic upgrade head` to get a real schema back before hitting a live
server against the same database pytest just used.

## Decision: "Active organisation" lives on the session, not the URL

**Context.** A user can belong to multiple organisations (multiple
`OrganisationMembership` rows). Every tenant-scoped endpoint needs an
unambiguous `organisation_id` to scope its query — and per `CLAUDE.md`,
that can never come from trusting a client-supplied value outright.

**Decision.** `Session.active_organisation_id` tracks which org a session
is currently acting within. `GET/POST /submissions` etc. take no
`organisation_id` in the path or body — a `get_current_membership`
dependency resolves it from the session server-side, then verifies (via a
real DB lookup) that a membership actually exists for that user in that
org before returning it. RBAC (`require_role`) is layered on top of that
same membership's `role`.

**Why.** This matches the API shapes in the original brief (`POST
/submissions`, not `POST /organisations/{id}/submissions`) and mirrors how
org-switcher apps work generally: pick an active org once, then every
request implicitly operates within it. Critically, "the client sent an
org_id" and "the server trusts it" are still two different things even in
designs that DO put org_id in the path — the actual security property is
the DB membership check, not where in the request the id appears. Putting
it on the session just means callers don't have to.

**Consequences.** Switching organisations needs its own endpoint (not
built yet — no UI needs it before Stage 7's frontend exists to drive it).
Every write in `SubmissionService`/`DocumentRepository` still requires an
explicit `organisation_id` parameter at the repository/service layer —
this decision only changes how the HTTP layer derives that value, not the
tenant-isolation contract the service layer already enforces (see Stage 2
decision above).

## Decision: CSRF via double-submit token, no second cookie

**Context.** Stage 0 committed to "CSRF protection via a double-submit
token" for the cookie-session auth model.

**Decision.** The session's `csrf_token` (a random value, stored
server-side, unrelated to the session token itself) is returned in the
JSON body of `/auth/register`, `/auth/login`, and `/auth/me` — not as a
second cookie. The frontend is expected to hold onto it and echo it back
as an `X-CSRF-Token` header on every mutating request; `require_csrf`
compares it against the session row using `secrets.compare_digest`
(constant-time).

**Why.** The classic double-submit pattern uses two cookies (one
HttpOnly, one JS-readable) specifically so a same-site page can read the
second cookie via JS and echo it as a header. Since the CSRF token here is
already returned in a JSON response body — which cross-site attackers
can't read due to the same-origin policy, regardless of cookies — a
second cookie adds no additional protection over just handing the token
to the frontend directly. One fewer cookie to manage.

## Decision: SESSION_SECRET keys an HMAC, not just present for future use

`hash_token()` (app/auth/tokens.py) computes `HMAC-SHA256(SESSION_SECRET,
raw_token)` rather than a bare `SHA256(raw_token)`. The raw token already
has 256 bits of entropy from `secrets.token_urlsafe`, so this isn't
protecting against brute-forcing the hash — it gives `SESSION_SECRET` (present
in config since Stage 0/1 but previously unused) a genuine purpose:
rotating it immediately invalidates every stored session at once, since
every `hash_token` comparison starts failing. A deliberate "revoke all
sessions" operational lever, not just leftover config.

## Bug: HNSW index existed only in the migration, not the model

**What happened.** Migration 0004 hand-created the
`ix_document_chunks_embedding_hnsw` index via `op.create_index(...)`, but
`app/models/document_chunk.py` never declared a matching SQLAlchemy
`Index` (there's no `mapped_column(index=True)` equivalent for
Postgres-specific index kinds like HNSW). Since the model is autogenerate's
source of truth, `alembic revision --autogenerate` saw an index in the
database that the model didn't know about and proposed dropping it —
genuine drift, not a pgvector-type false positive.

**Fix.** Declared the same index explicitly in `__table_args__` via
`sa.Index(..., postgresql_using="hnsw", postgresql_ops={"embedding":
"vector_cosine_ops"})`, matching the migration exactly. Confirmed via a
second autogenerate pass: empty diff.

## Bug: expired `updated_at` crashed every document upload

**What happened.** Stage 5's `IngestionService` calls
`DocumentRepository.update_status` twice per upload (→ `processing`, then
→ `ready`/`failed`) within the same request, and the route immediately
serializes the same ORM object via `DocumentRead.model_validate(document)`.
SQLAlchemy's default `eager_defaults` setting only re-fetches
server-generated column values (like `TimestampMixin.updated_at`, which
has `onupdate=func.now()`) via `RETURNING` on **INSERT** — not on UPDATE.
After the second `update_status` flush, `updated_at` was left in an
expired state; Pydantic's synchronous attribute access on it triggered an
implicit lazy-refresh, which can't await the async DB round-trip and
raises `MissingGreenlet`. This crashed every valid-PDF upload (7 tests) —
caught only by a real-Postgres verification pass, exactly like the Stage
2 enum bug, since nothing about this is visible to mypy, ruff, or a
non-DB test run.

**Fix.** `TimestampMixin` now sets `__mapper_args__ = {"eager_defaults":
True}`, forcing `RETURNING` on UPDATE too, so `updated_at` stays populated
in-memory the instant `flush()` returns. Applies to every model using the
mixin, not just `Document`.

## Gotcha: the API container didn't run migrations on startup

**What happened.** `apps/api/Dockerfile` only `COPY`'d `app/`, not
`alembic.ini`/`alembic/`, and its `CMD` only ever started `uvicorn` — a
fresh `docker compose up` never actually applied migrations, silently
relying on whoever ran `docker compose up -d db` locally having also run
`alembic upgrade head` by hand at some point. Found during Stage 5
verification when a genuinely fresh volume left the api container serving
against a database with no tables.

**Fix.** `Dockerfile` now copies `alembic.ini`/`alembic/` into the image
and its `CMD` runs `alembic upgrade head && uvicorn ...` — migrations
apply automatically on container start.

**Consequence to revisit at Stage 21.** This is correct and simple for a
single-instance dev/demo deployment. A real multi-replica production
deployment would have multiple containers racing to run migrations
simultaneously on every deploy — that needs migrations as a separate
release step (a one-off job before replicas start), not part of each
replica's own startup command.

## Bug: SQLAlchemy Enum columns persisted `.name`, not `.value`

**What happened.** The initial `str, enum.Enum` / `enum.StrEnum` models
(`SubmissionStatus`, `MembershipRole`, `DocumentStatus`) used lowercase
values (`"draft"`, `"admin"`, `"uploaded"`) and the hand-written migration
created matching lowercase Postgres enum labels. `ruff`, `mypy --strict`,
and every test passed — because the DB-dependent tests all ran in an
environment with no reachable Postgres and skipped cleanly. Only when a
real Postgres instance was available (via a separate verification pass —
see below) did the real bug surface: `sa.Enum(SomeEnum, name=...)`
defaults to persisting each member's `.name` (`"DRAFT"`), not `.value`
(`"draft"`), unless `values_callable` is passed. Every insert/update
through these three columns would have failed at runtime with
`InvalidTextRepresentationError`, in an environment where mypy, ruff, and
the full non-DB test suite were all green.

**Fix.** Added `str_enum_column()` in `app/models/base.py` — a small
helper that always passes `values_callable=lambda e: [m.value for m in
e]`, used by all three enum columns, so the correct call is the only call
available. Also added `compare_type=True` to `alembic/env.py`'s migration
context — without it, `alembic revision --autogenerate` silently ignores
column-*type* drift (which is exactly what this bug was) and only compares
table/column/constraint presence, so the autogenerate drift-check that's
supposed to catch hand-written-migration mistakes wouldn't have caught
this one either.

**Why this matters for how this project is verified.** This is the concrete
argument for why `docs/architecture.md`'s "never claim unverified success"
rule is load-bearing rather than a formality: static analysis and a
"passing" test suite were both green while a real, first-write-fails bug
sat in the database layer, because the tests were (correctly) skipping
instead of exercising real Postgres. It's also why DB-dependent tests are
written to skip loudly with a clear reason when unreachable, rather than
silently — and why this project always follows up a "tests pass" claim
with a real Postgres run before treating the DB layer as done.

## Decision: Timestamps are timezone-aware

`TimestampMixin` uses `DateTime(timezone=True)` (Postgres `TIMESTAMPTZ`),
not the naive `TIMESTAMP` SQLAlchemy would otherwise default to. An audit
trail with ambiguous timestamps is a known, easy-to-miss footgun — worth
fixing before the first migration exists rather than after.

## Decision: Upload validation is layered, not a single check

**Decision.** `DocumentService.upload_document` checks, in order:
declared `Content-Type` against an allowlist (`application/pdf` only, per
the brief's "PDF first" scope), size against `MAX_UPLOAD_SIZE_BYTES`, and
finally the actual file bytes against the PDF magic number (`%PDF-`) —
rejecting a mismatch even if the declared content-type was correct.

**Why.** Per `CLAUDE.md`/the threat model, a filename extension or
declared `Content-Type` is client-asserted and never trustworthy alone —
a client can label anything `application/pdf`. Checking magic bytes is a
cheap, dependency-free way to catch that class of mistake/abuse without
needing a full PDF parser (parsing itself is Stage 5). Order matters:
reject cheap/obvious mismatches (content-type, size) before touching the
file's actual bytes.

**Consequences.** This only proves the file *starts like* a PDF, not that
it's a well-formed one — genuinely malformed or malicious PDFs (parser
exploits, decompression bombs) are Stage 5's problem once real parsing
exists, and are tracked in `docs/threat-model.md` when that's written.
Stage 5 confirms this: `IngestionService` catches parse failures against
genuinely malformed content and marks the document `failed` rather than
crashing the request — the upload itself still succeeds, since the file
*is* safely stored either way.

## Decision: PDF parser — `pypdf`

**Options considered:** `pypdf` (pure Python, BSD license), `pdfplumber`
(pdfminer.six-based, better layout/table awareness, heavier), `PyMuPDF`
(fast, but AGPL-licensed — a real consideration for a project meant to be
defensible in interviews), `pdfminer.six` directly (lower-level, more code
to own).

**Decision.** `pypdf` for baseline per-page text extraction.

**Why.** Lowest dependency footprint, permissive license, and "extract
text per page" is genuinely all Stage 5 needs — table/layout-aware
extraction is a real future upgrade (structured extraction, Stage 9) but
not required for a chunking baseline. Revisit if extraction quality on
real-world PDFs (multi-column layouts, tables) proves inadequate.

## Decision: Chunking is per-page, character-based, not token-based

**Decision.** `chunk_text()` splits one page's text at a time — chunks
never span pages — using fixed character windows
(`DEFAULT_CHUNK_SIZE_CHARS = 2000`, `DEFAULT_CHUNK_OVERLAP_CHARS = 400`)
rather than counting tokens.

**Why per-page:** `DocumentChunk.page_id` is a single foreign key, not a
list — a chunk needs exactly one page of provenance. Chunking within page
boundaries makes that unambiguous for free; cross-page chunking would
need a design for multi-page provenance that nothing here currently
needs.

**Why character-based, not token-based:** the brief's own example baseline
is expressed in tokens (500/100 overlap), but "a token" is defined by
whatever tokenizer the embedding model uses — and no embedding provider is
chosen yet (that's Stage 6). Committing to a tokenizer now (e.g. `tiktoken`)
would tie chunking to a specific provider before there's a reason to.
~4 characters/token is a commonly-cited rough heuristic for English text,
so 2000/400 characters approximates the brief's 500/100 tokens without the
dependency. This is explicitly a naive baseline — no sentence/paragraph
awareness — meant to be benchmarked against smarter chunkers later
(Stage 11), not a permanent design.

## Decision: Embedding provider — local `fastembed`, not `sentence-transformers`/API providers

**Context.** The brief wants exactly one real embedding provider behind
the `EmbeddingProvider` abstraction — no API key required was the explicit
choice here (over OpenAI/Voyage), so verification (this project's own
agents included) can exercise the real thing end to end without secrets.

**Options considered:** `sentence-transformers` (the "local model" option
initially named) pulls in `torch`, a genuinely heavy dependency (hundreds
of MB to 2GB+); `fastembed` (Qdrant's library) uses ONNX Runtime instead,
achieving the same "local, free, offline-after-first-use" intent for a
much lighter footprint (~350MB total venv including it, vs. what torch
alone would add).

**Decision.** `fastembed`, default model `BAAI/bge-small-en-v1.5`
(384 dimensions). This is a substitution for literally
"sentence-transformers," not the underlying choice — the user chose
"local model, no API key, no cost," and `fastembed` satisfies that intent
more efficiently. Flagged here explicitly per `CLAUDE.md`'s "important
architectural decisions must be visible and justified."

**Why the query/document asymmetry matters.** `EmbeddingProvider` has
separate `embed_query`/`embed_documents` methods, not one — BGE models
specifically recommend an instruction prefix on the query side only;
fastembed exposes this via distinct `query_embed`/`passage_embed` calls.
Collapsing these into one method would silently produce worse retrieval
quality for exactly the model chosen here.

**Consequence — model warm-up.** Loading the model takes a few seconds
(one-time download on first-ever run, then loading weights into memory on
each process start). `app/main.py`'s lifespan handler calls
`get_embedding_provider()` at startup specifically so this cost lands
once, at boot, rather than surprising whichever user happens to upload or
search first.

## Decision: pgvector column + HNSW index, cosine distance

**Decision.** `DocumentChunk.embedding` is a `pgvector` `Vector(384)`
column (migration 0004), with an HNSW index using `vector_cosine_ops`.
Enabling the extension (`CREATE EXTENSION IF NOT EXISTS vector`) happens
in this migration, not earlier — the pgvector *extension binary* has
shipped in the Docker image since Stage 1 (see that stage's dependency
log), but the SQL-level `CREATE EXTENSION` call is what actually registers
its types/operators in a given database, and there was nothing to index
before this stage.

**Why HNSW over IVFFlat:** IVFFlat needs a `lists` parameter tuned to
expected row count ahead of time and degrades until enough rows exist to
train it well; HNSW has no such cold-start tuning problem and generally
gives better recall/latency for small-to-medium datasets, at the cost of
slower index builds — a fine trade for this project's scale.

**Why cosine, not L2/inner-product:** `bge-small-en-v1.5` (like most
sentence-embedding models) is trained/evaluated for cosine similarity;
matching the index's distance operator to what the model actually
optimizes for is what makes nearest-neighbor search meaningful.

**Embedding column is nullable.** A chunk could in principle exist before
its embedding is computed (a future partial-failure/backfill path); the
current `IngestionService` always computes it before persisting, but
nothing forces that invariant at the schema level, so `search_similar`
explicitly filters `embedding IS NOT NULL` rather than assuming it.

## Decision: Search API and test strategy — real model vs. fake

**Decision.** `POST /submissions/{id}/search` embeds the query and
returns cosine-nearest chunks, tenant/submission-scoped, each with
`document_id`, `page_number`, `text`, and `score` (`1 - distance`) — a
source-aware result per the brief's "click a citation, see the source
page" goal, even though the citation UI itself is Stage 7+. The response
also carries `strategy` (`"vector"`, forward-compatible with Stage 10's
hybrid retrieval) and `latency_ms`, per the brief's "retrieval should
expose scores, source, strategy, latency."

**Test strategy.** HTTP-level tests (`test_search_api.py`,
`test_document_ingestion_api.py`, etc.) use `FakeEmbeddingProvider`
(`tests/fake_embeddings.py`) — a deterministic hash-based stand-in at the
*same* 384 dimensions as the real column, so it's valid against the real
pgvector schema but requires no model download and adds no per-test
latency. Its determinism gives a genuinely meaningful assertion for free:
querying with text identical to a stored chunk yields distance 0 (score
1.0), which is what `test_search_returns_exact_text_match_as_top_result`
checks. Real embedding *quality* (does "revenue growth" score higher
against a relevant sentence than an irrelevant one?) is verified
separately in `test_fastembed_provider.py`, against the actual model —
skipping cleanly if it can't load, the same pattern already used for
DB-dependent tests.

## Dependency decisions log

Recorded as they're actually added, with justification, per the dependency
policy in the brief.

**Stage 1 backend (`apps/api`):** FastAPI, Pydantic v2 + pydantic-settings,
SQLAlchemy 2.x (async) + asyncpg + greenlet (required by SQLAlchemy's async
engine — missing it fails connections at runtime, not at import time; caught
by manually exercising the health endpoint, not by the unit test suite,
since the test suite overrides the DB dependency), pytest + pytest-asyncio +
httpx (ASGI transport, no running server needed for tests), ruff, mypy
(`strict = true`). Alembic deliberately **not** added yet — no models exist
to migrate; it lands in Stage 2.

**Stage 1 frontend (`apps/web`):** Next.js 15 (App Router) + React 19 +
TypeScript, eslint (flat config via `eslint-config-next`). No UI component
library added yet — not justified by a single scaffold page.

**Stage 1 infra:** `pgvector/pgvector:pg16` Docker image for Postgres (ships
the pgvector extension pre-installed, avoiding a manual `CREATE EXTENSION`
step in an init script for something we need from Stage 6 onward anyway).

**Stage 2 backend:** `alembic` (migrations, async template — see decision
above). `pytest_asyncio` fixtures added for a real-Postgres test layer
(session-scoped engine, per-test transaction rollback, skips cleanly when
no Postgres is reachable rather than failing).

**Stage 3 backend:** `argon2-cffi` (Argon2id password hashing — current
OWASP-recommended default, ahead of bcrypt/PBKDF2). `email-validator`
(justifies Pydantic's `EmailStr` for the one place we validate an email
address, rather than hand-rolling regex validation).

**Stage 4 backend:** `python-multipart` (required by Starlette/FastAPI to
parse multipart file uploads — not optional once `UploadFile` is used).
No object-storage SDK added — see the object storage decision above for
why MinIO/S3 is deferred.

**Stage 5 backend:** `pypdf` (PDF text extraction — see decision above).
No tokenizer library added (chunking is character-based, deliberately, to
avoid committing to a tokenizer before Stage 6 picks an embedding
provider) and no PDF-authoring library added (test fixtures build minimal
valid PDF bytes by hand in `tests/pdf_fixtures.py` instead).

**Stage 6 backend:** `fastembed` (local embeddings — see decision above,
including why it replaced the initially-named `sentence-transformers`)
and `pgvector` (the Python package providing SQLAlchemy's `Vector` type —
distinct from the Postgres extension of the same name, which the
`pgvector/pgvector` Docker image already ships).

---

## Roadmap

Stage 0 (this document + `CLAUDE.md`) is in progress. Stages 1–21 as defined
in the project brief; each stage stops for explicit go-ahead before the next
begins. Not reproduced here in full to avoid drift — the authoritative stage
list is the one the user provided; this file records decisions made *within*
each stage as it happens, plus a status line per stage below.

| Stage | Name | Status |
|---|---|---|
| 0 | Architecture/bootstrap planning | Done |
| 1 | Development environment | Done — backend (ruff/mypy/pytest) and frontend (lint/typecheck/build) verified locally; full Docker Compose stack (db healthy, api, web) built and run end-to-end, `/health` confirmed reaching real Postgres, web page confirmed rendering live API data |
| 2 | Core domain | Done — models, migration, repository/service layer verified against real Postgres (11/11 tests, empty autogenerate drift); a real enum-persistence bug found and fixed along the way (see below) |
| 3 | Auth/RBAC | Done — verified against real Postgres: both migrations apply cleanly, autogenerate drift-check empty, all 31 tests pass (incl. both named cross-tenant tests and RBAC), manual checks confirm HttpOnly cookie with no Secure flag in dev, CSRF enforced both ways, raw session token never appears in a response body or log |
| 4 | Upload/storage | Done — all 44 tests pass against real Postgres; a live docker-compose check (upload → volume-backed file → API container restart → re-download) confirmed the filesystem storage backend is genuinely durable, not just in-process |
| 5 | Parsing/chunking | Done — all 55 tests pass against real Postgres; migration 0003 verified via empty autogenerate drift; a real bug found and fixed (expired `updated_at` crashing every upload — see below); a live docker-compose upload of a real 2-page PDF confirmed correct extracted text and page ordering; API container now runs migrations on startup |
| 6 | Embeddings/vector retrieval | Done — all 62 tests pass against real Postgres (including the real fastembed model); migration 0004 verified via autogenerate drift (after fixing a genuine gap — the HNSW index existed only in the migration, not the model, see below); a live docker-compose semantic search (query "how much did revenue grow" against 3 unrelated sentences) correctly ranked the revenue sentence highest (0.73 vs. 0.63/0.48) — real semantic search, not exact-match, proven end-to-end |
| 7 | Minimal frontend | Planned |
| 8 | First milestone hardening | Planned |
| 9–21 | Structured extraction → deployment/polish | Planned |
