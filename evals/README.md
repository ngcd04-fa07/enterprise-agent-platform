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

**A real limitation, not hidden:** the judge is the same 3B local model
being judged, and its reasoning quality varies noticeably run to run, not
just case to case. One real run flagged a real omission in its own
`issues` reasoning while still marking the overall verdict
`faithful: true`, and separately mischaracterized a `low`-severity
finding as high-severity. A second run over the identical scenarios
produced fully coherent, internally-consistent reasoning throughout, with
no such errors. LLM-as-judge with a small local model is a real, useful
signal for catching gross failures (invented facts, contradicted
recommendations) — it is not a substitute for reading the `issues`
output on any given run, and its boolean verdict alone shouldn't be
trusted as a stable, precise pass/fail without a human spot-checking the
reasoning behind it.

## Why `evals/` and not `benchmarks/`

Different purpose despite similar shape (a labeled dataset + a runner +
a metric). `benchmarks/retrieval/` (Stage 11) tunes *ranking quality* —
there's no "correct" answer, just better/worse orderings. `evals/`
measures AI-output *correctness/faithfulness* against ground truth or a
faithfulness standard — closer to a regression/compliance check. The
roadmap names them as distinct stages (11 vs. 15) for the same reason.

## Common design notes

Both evaluators seed their fixtures inside one transaction that's always
rolled back — a run never leaves data behind in whatever database
`DATABASE_URL` points at (verified via direct `psql` inspection after a
real run of each). Both run against the real Ollama model, no fakes —
the point is measuring real behavior.
