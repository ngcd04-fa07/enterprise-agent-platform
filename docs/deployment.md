# Public demo deployment guide

This is a step-by-step runbook for standing up a **public, read-mostly demo**
of this platform — separate from the local Docker Compose setup described in
the README, and separate from any real production deployment. It exists for
one purpose: a stable, clickable link for recruiters/reviewers, restricted to
synthetic data and a hard cost ceiling.

**None of this has been run against real accounts in this repository's own
verification history** (unlike everything else documented in
`docs/architecture.md`) — the provider choices below (Render, Neon,
Cloudflare R2, Groq) were made deliberately conservatively (all have usable
free tiers), but you should verify each step as you go rather than trusting
this guide blindly. Where a detail depends on how a third-party dashboard
looks today, that's flagged explicitly.

## What's different about the demo deployment

- **`DEMO_MODE=true`** (app/core/config.py): disables `POST /auth/register`
  entirely (one fixed, pre-seeded account only — see below) and applies a
  tight per-IP rate limit to the two routes that spend LLM tokens
  (extraction, triage trigger) — see `app/security/demo_guard.py`.
- **`LLM_PROVIDER=groq`**: no Ollama instance to reach in this deployment, so
  `app/llm_gateway/groq_gateway.py` is used instead, behind the same
  `LLMGateway` interface — see its docstring for why this is a stated,
  temporary exception to the project's local-model architecture, not a
  replacement for it.
- **`STORAGE_BACKEND=s3`** against Cloudflare R2, not the filesystem backend
  — same `S3ObjectStorage` class (Stage 21) already tested against real
  MinIO, just pointed at a different S3-compatible endpoint.
- **An external Postgres (Neon)**, not Render's own free Postgres — Render's
  free Postgres expires after a fixed period; a database that can silently
  disappear is not acceptable for anything meant to stay up as a portfolio
  link.
- **One pre-seeded synthetic submission** (`scripts/seed_demo_data.py`), run
  once after deployment — see that script's docstring for exactly what it
  creates.

## Prerequisites

- A GitHub account with this repository pushed to it (Render deploys from a
  git repo).
- Accounts (all free-tier to start) with: [Render](https://render.com),
  [Neon](https://neon.tech), [Cloudflare](https://dash.cloudflare.com) (for
  R2), [Groq](https://console.groq.com).

## Step 1 — Neon: Postgres with pgvector

1. Create a new Neon project (any region close to where Render will run —
   check Render's own region options first so you can pick a nearby Neon
   region and avoid unnecessary cross-region latency).
2. Neon's default database already ships with the `pgvector` extension
   available; this project's own migration `0004` runs `CREATE EXTENSION IF
   NOT EXISTS vector` itself, so no manual `CREATE EXTENSION` step should be
   needed — just confirm after migrations run (Step 6) that
   `SELECT * FROM pg_extension WHERE extname = 'vector';` returns a row, from
   Neon's own SQL editor.
3. Copy the connection string Neon gives you. It looks like:
   ```
   postgresql://<user>:<password>@<host>.neon.tech/<database>?sslmode=require
   ```
4. This project's `DATABASE_URL` needs the `+asyncpg` driver, and asyncpg
   expects `ssl=require` rather than libpq's `sslmode=require`:
   ```
   postgresql+asyncpg://<user>:<password>@<host>.neon.tech/<database>?ssl=require
   ```
   If this specific query-string form doesn't work against asyncpg when you
   try it, the fallback is to drop the query string entirely and instead set
   `PGSSLMODE`-equivalent behavior via `?ssl=true`, or as a last resort
   terminate TLS yourself — verify by actually connecting (Step 6) rather
   than assuming this exact string is correct.

## Step 2 — Cloudflare R2: object storage

1. In the Cloudflare dashboard, create an R2 bucket (e.g.
   `enterprise-agent-demo-documents`).
2. Create an R2 API token scoped to just that bucket (Object Read & Write) —
   not an account-wide token.
3. Note down: the **Account ID**, the token's **Access Key ID** and **Secret
   Access Key**, and the bucket's S3 API endpoint, which is:
   ```
   https://<account-id>.r2.cloudflarestorage.com
   ```
4. `app/storage/s3.py`'s `S3ObjectStorage` (via `boto3`) reads credentials
   from boto3's standard credential chain — for Render this means setting
   `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as plain environment
   variables on the API service (not a project-specific setting — see
   `app/storage/factory.py`'s comment on why credentials were deliberately
   never made a `Settings` field).

## Step 3 — Groq: hosted LLM API key

1. Create an API key at [console.groq.com](https://console.groq.com).
2. That's it — no bucket/database provisioning needed. Note the key for
   Step 4.

## Step 4 — Render: the API service

Create a new Render **Web Service**, connected to this repo, Docker runtime,
Dockerfile path `apps/api/Dockerfile`.

**Start command override** (Render lets you override a Dockerfile's `CMD`
per service, in the dashboard's Start Command field — you do not need to
edit `apps/api/Dockerfile` itself): unlike the multi-replica-safe Docker
Compose setup (which runs migrations in a separate one-shot `migrate`
service — see Stage 21 in `docs/architecture.md`), Render's free/starter web
services are single-instance, so the multi-replica migration race that
change was built to prevent doesn't apply here. For this deployment only,
override the start command to:

```
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Health check path**: `/health` — already the cheapest possible endpoint
(one `SELECT 1`-equivalent DB ping, no LLM/embedding/retrieval call — see
`app/api/routes/health.py`), safe to use both for Render's own health check
and for whatever external keep-alive pinger you point at this service. This
avoidance of Render's free-tier cold-start sleep is a deployment
convenience, not a reliability guarantee — nothing in this app depends on
the service never having cold-started.

**Environment variables**:

| Variable | Value |
|---|---|
| `DATABASE_URL` | The Neon connection string from Step 1, converted as described there |
| `SESSION_SECRET` | A real random value, ≥32 chars — e.g. `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `ENVIRONMENT` | `production` |
| `DEMO_MODE` | `true` |
| `STORAGE_BACKEND` | `s3` |
| `S3_BUCKET_NAME` | the R2 bucket name from Step 2 |
| `S3_ENDPOINT_URL` | the R2 endpoint from Step 2 |
| `S3_REGION` | `auto` (R2's convention; any non-empty value is accepted by boto3 here) |
| `AWS_ACCESS_KEY_ID` | the R2 token's access key |
| `AWS_SECRET_ACCESS_KEY` | the R2 token's secret key |
| `LLM_PROVIDER` | `groq` |
| `GROQ_API_KEY` | the key from Step 3 |

Everything else (rate limits, body-size limits, PDF resource ceilings) keeps
its documented default — see `.env.example` for the full list if you want to
tune any of them.

Deploy, then watch the build logs. Once it's live, `curl
https://<your-service>.onrender.com/health` should return
`{"status":"ok","environment":"production","database":"ok"}` — if
`database` is `"unreachable"`, revisit the `DATABASE_URL` SSL note in Step 1
before anything else.

## Step 5 — Render: the web (frontend) service

Create a second Render **Web Service**, same repo, Docker runtime, Dockerfile
path `apps/web/Dockerfile`.

**Build arguments** (Render's dashboard has a Docker Build Args section for
Docker-based services): all three below must be set as **build args**, not
just runtime env vars — `apps/web/next.config.ts` bakes its `rewrites()`
destination and `headers()` CSP/HSTS logic in at build time, and
`NEXT_PUBLIC_DEMO_MODE` is inlined into the client bundle the same way — a
documented gotcha this project has hit before (Stage 7, Stage 20 — see
`docs/architecture.md`).

| Build arg | Value |
|---|---|
| `API_ORIGIN` | the API service's Render URL from Step 4, e.g. `https://enterprise-agent-api.onrender.com` |
| `ENVIRONMENT` | `production` |
| `NEXT_PUBLIC_DEMO_MODE` | `true` |

Set the same three as **runtime** environment variables too (belt-and-braces;
some of Next.js's own server-side code reads `process.env` at request time,
not just at build time). `NEXT_PUBLIC_DEMO_MODE` only controls the frontend's
banner/login-page text — it's the API service's own `DEMO_MODE` (Step 4)
that actually disables registration and rate-limits extraction/triage, so
don't set one without the other.

## Step 6 — Run migrations once, then seed the demo data

Both steps run from Render's **Shell** tab on the API service (or
`render ssh` via Render's CLI), once, after the first successful deploy:

```bash
cd /app  # or wherever the Dockerfile's WORKDIR puts the app — check the build logs
alembic upgrade head   # only needed if the start-command override in Step 4 hasn't run yet
python3 scripts/seed_demo_data.py
```

The seed script is idempotent (see its docstring) — safe to re-run; it does
nothing if the demo account already exists. It prints the demo login
(`demo@example.com` / the password in `scripts/seed_demo_data.py`) when it's
done — those are intentionally public, not secrets.

This step genuinely calls Groq (real LLM cost, real tokens) and R2 (real
storage) — expect it to take under a minute for three small synthetic PDFs.

## Step 7 — Keep-alive

You mentioned already having a working keep-alive approach from another
Render project — point it at this deployment's `/health` on whatever
cadence you're already using. Nothing here needs a specific cadence: the
endpoint is a single cheap DB ping either way. Two things worth confirming
once, though, since they're specific to this app:

- `/health` never touches the LLM gateway, embeddings, or retrieval — a ping
  storm here costs nothing beyond one Postgres round trip per ping.
- Treat cold-start avoidance as convenience, not a guarantee — a genuinely
  cold Render free instance can still take some seconds to respond to the
  very first real request after a period with no traffic, keep-alive or not.

## Step 8 — Verification checklist

Before sharing the link:

- [ ] `GET /health` on the API service returns `database: "ok"`.
- [ ] The web service's landing page loads, shows the platform-overview
      section, and its login form is reachable.
- [ ] The demo banner appears at the top of every page (confirms
      `NEXT_PUBLIC_DEMO_MODE=true` actually took at build time).
- [ ] Logging in as `demo@example.com` (pre-filled on the login form) works
      and shows the seeded submission.
- [ ] The submission's three documents (application, financial summary, loss
      history) are viewable/downloadable via "Open PDF".
- [ ] Search returns results against the seeded documents.
- [ ] Extraction shows 4 of 5 fields with a "View evidence" link that
      displays the actual cited source page text (broker is expected to be
      absent — see docs/architecture.md's "Public demo deployment" entry).
- [ ] Triage shows a recommendation, the low-severity missing-broker flag,
      and the approval control (only for an admin — the seeded demo account
      is one).
- [ ] Re-running extraction/triage from the UI works once, and returns 429
      (with a clear message, not a raw error) once
      `DEMO_LLM_RATE_LIMIT_PER_IP_MAX_ATTEMPTS` is exceeded from the same IP.
- [ ] The registration page shows the "disabled" notice instead of a form,
      and `POST /auth/register` itself returns 403 (registration is really
      disabled server-side, not just hidden in the UI).
- [ ] A fresh browser/incognito session cannot see any data belonging to a
      different, real organisation — there shouldn't be one on this
      deployment at all, but confirm the demo org is the only one present:
      ```sql
      SELECT id, name FROM organisations;
      ```
      from Neon's SQL editor.

## What this deliberately does not cover

Per the project's own Stage 20/21 deferrals (see `docs/architecture.md`):
this is still a single-instance deployment (Render's free/starter tier),
with no distributed rate limiting or shared circuit-breaker state, and no
S3 bucket lifecycle policy beyond what you set manually in the R2 dashboard.

**One specific, real implication worth understanding before you rely on
it**: Render terminates TLS in front of every service and proxies to it,
same as any PaaS — so `request.client.host`, as the app sees it, is
Render's edge, not necessarily the original visitor's IP (this app
deliberately never trusts `X-Forwarded-For`, see `app/api/routes/auth.py`'s
comment on why — there was no reverse proxy in this project's topology when
that decision was made, and verifying Render's exact forwarding behavior
— does it replace the header or append to a client-supplied one, is it a
single hop — needs a real deployed instance to check, not a guess written
here). The practical consequence if every visitor really does appear as
the same IP: the demo's per-IP LLM rate limit collapses into one *shared*
quota across all visitors for that window, rather than one quota each.
That's still a real, working ceiling — total LLM-invoking calls across
every visitor stays bounded, so cost control holds — it's just fairness
between visitors that degrades (one active visitor can use up the shared
window and get everyone else a 429 until it resets). For a low-traffic
portfolio demo this is an acceptable tradeoff, not a security hole; verify
it empirically once deployed (two different real devices hitting extract/
triage around the same time) before deciding whether it's worth a
properly-verified trusted-proxy fix.
