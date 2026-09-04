# Retrieval benchmark

Measures Recall@5 and MRR (Mean Reciprocal Rank) for the three retrieval
strategies — vector-only, lexical-only, and hybrid — against a small,
hand-labeled fixture set (`retrieval/dataset.py`), plus a sensitivity
sweep of hybrid's Reciprocal Rank Fusion constant `k`.

This is what Stage 10's hybrid retrieval decision (`docs/architecture.md`)
was missing at the time: a way to check "does hybrid actually beat either
signal alone" with numbers instead of a couple of manually-picked example
queries.

## Why this isn't inside `apps/api`

Per the repository layout decision in `docs/architecture.md`, a
top-level package only gets created once something outside `apps/api`
needs to import its code. This benchmark is exactly that case — it
imports `apps/api`'s retrieval code directly (the same
`RetrievalService`/`DocumentChunkRepository` that runs in production, not
a reimplementation) rather than living as a shared extracted package,
since there's still only one real runtime consumer (the API itself); the
benchmark just borrows its code via `sys.path`, run in `apps/api`'s own
virtualenv.

## Running it

Needs a reachable Postgres (same as running the backend or its test
suite) and the real embedding model (no fakes — the point is measuring
actual retrieval quality). Seeds its fixture data inside one transaction
that's rolled back at the end, so a run never leaves data behind in
whatever database `DATABASE_URL` points at.

```bash
source apps/api/.venv/bin/activate
DATABASE_URL=postgresql+asyncpg://enterprise_agent:<password>@localhost:5432/enterprise_agent \
  SESSION_SECRET=any-value-unused-by-this-script \
  python3 -m benchmarks.retrieval.run
```

## Interpreting the RRF k sweep

The sweep is informational, not a tuning recommendation to act on
blindly — twelve hand-written queries is nowhere near enough to safely
retune a production constant against. It exists so a future, larger
labeled set can be dropped into `dataset.py` and immediately produce a
real basis for changing `RetrievalService`'s `_RRF_K`, rather than that
decision being made on vibes either way.
