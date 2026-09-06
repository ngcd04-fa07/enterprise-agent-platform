# Evaluation harness

Two evaluators, deliberately different in kind — matching CLAUDE.md's AI
rules: "Prefer deterministic evaluators in the eval platform; LLM-as-judge
only for genuinely semantic dimensions, and only with versioned prompts
and structured output."

## `extraction/` — deterministic

Scores the real `ExtractionService` (Stage 9) against a hand-labeled
dataset via normalized string matching — not an LLM call. "Does the text
say $500,000" is checkable by plain comparison, not a judgment call, so
it gets a deterministic evaluator.

```bash
source apps/api/.venv/bin/activate
DATABASE_URL=... SESSION_SECRET=... python3 -m evals.extraction.run
```

Reports correct/hallucination/missed/wrong-value counts plus precision
and recall.

## `triage_faithfulness/` — LLM-as-judge

The one genuinely semantic dimension in this app's AI surface: does the
triage agent's free-text summary (Stage 12) accurately restate the exact
facts and findings it was given, without inventing anything or
contradicting the given recommendation? That's not answerable by string
matching, so this evaluator uses a second LLM call — the same local model,
via the same `llm_gateway` — with a versioned prompt (`JUDGE_PROMPT_VERSION`
in `judge.py`) and a structured verdict schema (`FaithfulnessVerdict`).
The recommendation itself is never judged here — it's deterministic
(`app/agents/underwriting_rules.py`) and already covered by
`tests/test_underwriting_rules.py`.

```bash
source apps/api/.venv/bin/activate
DATABASE_URL=... SESSION_SECRET=... python3 -m evals.triage_faithfulness.run
```

**A real limitation, not hidden:** the judge is a local model from the
same family as the one it's judging — both the triage synthesis call and
the judge's own call request `TaskComplexity.COMPLEX` (Stage 16's model
routing), so as of Stage 16 both run on the local `qwen2.5:14b` "capable"
tier, not a genuinely independent or larger model. Its reasoning quality
has varied noticeably between runs: the first run against the original
3B model (pre-Stage-16) flagged a real omission in its own `issues`
reasoning while still marking the overall verdict `faithful: true`, and
separately mischaracterized a `low`-severity finding as high-severity; a
second run over the identical scenarios produced fully coherent,
internally-consistent reasoning throughout; the first run after Stage
16's routing change (now on `qwen2.5:14b`) was also fully clean. LLM-as-
judge with a small local model is a real, useful signal for catching
gross failures (invented facts, contradicted recommendations) — it is
not a substitute for reading the `issues` output on any given run, and
its boolean verdict alone shouldn't be trusted as a stable, precise
pass/fail without a human spot-checking the reasoning behind it.

## `smoke_test.py` — CI-safe harness check, not a model-quality measurement

Neither evaluator above runs in CI: both need a real Ollama model, which
CI's runners don't have. `smoke_test.py` instead runs the exact same
seeding/scoring/judging code (`run_extraction_eval`/`run_triage_eval`,
factored out of each `run.py` for this reason) against a deterministic
`FakeLLMGateway` programmed to behave perfectly — so it's cheap, fast, and
runs on every push (see `.github/workflows/ci.yml`). It answers a
different question than the two evaluators above: not "is the model any
good," but "is the harness itself still wired correctly" — dataset
loading, fixture seeding inside a rolled-back transaction, the
merge/scoring/judging logic. A regression here (a renamed field, a broken
merge, a changed call signature) fails CI immediately instead of only
surfacing the next time someone runs the real evaluators by hand.

Since Stage 18, it also drives `record_run.record_with_llm` and
`compare_runs.compare_runs` directly (the same reusable functions the two
CLIs above wrap) with two fake runs — one perfect, one deliberately
regressed on the real `fields_split_across_pages` case's second page —
and asserts the persisted comparison correctly flags a REGRESSED slice.
This keeps the "no real model in CI" constraint intact for the
comparison machinery too, and cleans up its own persisted rows afterward
regardless of outcome (a smoke test's rows aren't real comparison
history worth keeping).

```bash
source apps/api/.venv/bin/activate
DATABASE_URL=... SESSION_SECRET=... python3 -m evals.smoke_test
```

## `comparison.py`, `record_run.py`, `compare_runs.py` — release comparison (Stage 18)

Systematic baseline-vs-candidate comparison on top of the two evaluators
above: did a change (a new model, a new prompt, a routing change) make
things better or worse, in aggregate *and* on every slice? An aggregate
improvement is never allowed to mask a slice-level regression — see
`comparison.py`'s `compare()`, and the worked example in
`test_comparison.py` (an aggregate 89%→92% "improvement" with one slice
regressing 87%→71% is still, correctly, an overall REGRESSED verdict).

**Record a run, then compare two of them:**

```bash
source apps/api/.venv/bin/activate
DATABASE_URL=... SESSION_SECRET=... python3 -m evals.record_run \
    --evaluator extraction --label baseline
DATABASE_URL=... SESSION_SECRET=... python3 -m evals.record_run \
    --evaluator extraction --label candidate
DATABASE_URL=... SESSION_SECRET=... python3 -m evals.compare_runs \
    --evaluator extraction --baseline baseline --candidate candidate
```

`--baseline`/`--candidate` accept either a run id or a label — a label
resolves to its most recent matching run (labels are deliberately not
unique; the same label, e.g. "baseline", is expected to be re-recorded
many times as the evaluated code changes), with a printed note if more
than one run shares it. `compare_runs` exits non-zero on an overall
REGRESSED verdict, so it can gate a release, not just report on one.

**A real, non-fabricated model-version comparison, since this repo
already has two real local models (Stage 16):**

```bash
python3 -m evals.record_run --evaluator extraction --label baseline --model qwen2.5:3b
python3 -m evals.record_run --evaluator extraction --label candidate --model qwen2.5:14b
python3 -m evals.compare_runs --evaluator extraction --baseline baseline --candidate candidate
```

`--model` bypasses Stage 16's `RoutingLLMGateway` entirely and talks to
one named Ollama model directly. Run for real against this project's
4-case extraction dataset: the larger `qwen2.5:14b` model actually scored
*worse* than `qwen2.5:3b` (90%→85% aggregate, 80%→60% on the
`multi_page` slice) — reported here as found, not smoothed over. One
manual run on a tiny dataset isn't a general claim about either model;
it's exactly the kind of result this tooling exists to surface plainly.
**This is a manual/optional demonstration only — CI never runs a real
model.**

**Persistence and semantics, briefly** (see `docs/architecture.md`'s
Stage 18 decision for the full writeup): three tables
(`evaluation_runs`, `evaluation_case_results`, `evaluation_comparisons`),
tenant-unscoped like `ai_call_traces`, for the same reason. Metric
*direction* is explicit, not assumed: `KNOWN_METRIC_DIRECTIONS` in
`comparison.py` lists which metrics are higher-is-better (all of them,
today — `correct`, `faithful`); an unregistered metric is reported
`UNKNOWN_DIRECTION` rather than silently treated as higher-is-better,
since a future metric like latency or error rate is lower-is-better and
guessing wrong would silently invert its regression/improvement calls. A
metric or slice present on only one side of a comparison is reported
`MISSING_IN_BASELINE`/`MISSING_IN_CANDIDATE`, never treated as 0.
Comparing across evaluators (extraction vs. triage) is rejected outright.

## `smoke_test.py` — CI-safe harness check, not a model-quality measurement

Different purpose despite similar shape (a labeled dataset + a runner +
a metric). `benchmarks/retrieval/` (Stage 11) tunes *ranking quality* —
there's no "correct" answer, just better/worse orderings. `evals/`
measures AI-output *correctness/faithfulness* against ground truth or a
faithfulness standard — closer to a regression/compliance check. The
roadmap names them as distinct stages (11 vs. 15) for the same reason.

## Common design notes

All scripts that seed fixtures do so inside one transaction that's always
rolled back — a run never leaves data behind in whatever database
`DATABASE_URL` points at (verified via direct `psql` inspection after a
real run of each). `extraction/run.py` and `triage_faithfulness/run.py`
run against the real Ollama models, no fakes — the point is measuring
real behavior. `smoke_test.py` is the deliberate exception, using a fake
model so it can run without Ollama at all — see above for why that's a
different, complementary kind of check, not a replacement.

`record_run.py` and `compare_runs.py` (Stage 18) are different in kind:
they *persist* real data (an `EvaluationRun` and its case results, a
comparison) rather than rolling it back — that's the whole point, a
durable comparison history. `comparison.py`'s own logic has zero DB
dependency and is tested with plain, fast pytest tests in
`test_comparison.py` — run via `pytest evals/` from the repo root (not
folded into `apps/api`'s own `pytest`, which is scoped to
`apps/api/tests` only, to avoid a reverse-direction import).
