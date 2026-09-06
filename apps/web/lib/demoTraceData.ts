// Real, previously-generated data — not fabricated, not live-queried.
//
// The trace rows below are the exact `ai_call_traces` produced by one
// real run of `apps/api/scripts/seed_demo_data.py` against real Postgres,
// real fastembed embeddings, and real local Ollama models, captured via
// direct `psql` inspection (not the script's own printed output). The
// eval comparison is the real, already-documented Stage 18 result from
// `evals/README.md` / `docs/architecture.md` (a manual `qwen2.5:3b` vs
// `qwen2.5:14b` extraction comparison on the same 4-case dataset).
//
// This is deliberately NOT a live query against `ai_call_traces` or
// `evaluation_comparisons`: those tables have no organisation_id or
// submission linkage at all (Stage 14's decision — see
// docs/architecture.md's "Public demo deployment" entry) — building a
// live per-submission trace viewer would mean either a real schema
// change to a table whose whole point is not being tenant-scoped, or a
// fragile time-window correlation that could misattribute one
// organisation's calls to another's request. A static snapshot of one
// real run sidesteps that risk entirely while still showing real numbers.

export interface DemoTraceRow {
  callType: string;
  provider: string;
  model: string;
  status: "success" | "failure";
  latencyMs: number;
  routeReason: string | null;
  note: string;
}

export const DEMO_TRACE_ROWS: DemoTraceRow[] = [
  {
    callType: "embed_documents",
    provider: "fastembed",
    model: "BAAI/bge-small-en-v1.5",
    status: "success",
    latencyMs: 62.9,
    routeReason: null,
    note: "application.pdf, 2 chunks",
  },
  {
    callType: "embed_documents",
    provider: "fastembed",
    model: "BAAI/bge-small-en-v1.5",
    status: "success",
    latencyMs: 25.6,
    routeReason: null,
    note: "financial_summary.pdf, 1 chunk",
  },
  {
    callType: "embed_documents",
    provider: "fastembed",
    model: "BAAI/bge-small-en-v1.5",
    status: "success",
    latencyMs: 43.0,
    routeReason: null,
    note: "loss_history.pdf, 1 chunk",
  },
  {
    callType: "llm_generate",
    provider: "ollama",
    model: "qwen2.5:3b",
    status: "success",
    latencyMs: 3969.0,
    routeReason: "complexity_route_fast",
    note: "extraction, chunk 1 of 4",
  },
  {
    callType: "llm_generate",
    provider: "ollama",
    model: "qwen2.5:3b",
    status: "success",
    latencyMs: 846.4,
    routeReason: "complexity_route_fast",
    note: "extraction, chunk 2 of 4",
  },
  {
    callType: "llm_generate",
    provider: "ollama",
    model: "qwen2.5:3b",
    status: "success",
    latencyMs: 1562.4,
    routeReason: "complexity_route_fast",
    note: "extraction, chunk 3 of 4",
  },
  {
    callType: "llm_generate",
    provider: "ollama",
    model: "qwen2.5:3b",
    status: "success",
    latencyMs: 639.3,
    routeReason: "complexity_route_fast",
    note: "extraction, chunk 4 of 4",
  },
  {
    callType: "llm_generate",
    provider: "ollama",
    model: "qwen2.5:14b",
    status: "success",
    latencyMs: 15900.7,
    routeReason: "complexity_route_capable",
    note: "triage narrative synthesis (routine per-chunk extraction stays on the fast tier; reasoning-heavy synthesis escalates to the capable tier — see Stage 16/19 in docs/architecture.md)",
  },
];

export interface DemoEvalComparisonRow {
  metric: string;
  baseline: string;
  candidate: string;
  verdict: "REGRESSED" | "IMPROVED" | "UNCHANGED";
}

// evals/README.md / docs/architecture.md, Stage 18: a real recorded
// comparison of extraction on qwen2.5:3b (baseline) vs. qwen2.5:14b
// (candidate) against the same 4-case hand-labeled dataset.
export const DEMO_EVAL_COMPARISON: {
  baselineLabel: string;
  candidateLabel: string;
  overallStatus: "REGRESSED" | "IMPROVED" | "UNCHANGED";
  rows: DemoEvalComparisonRow[];
} = {
  baselineLabel: "qwen2.5:3b (extraction)",
  candidateLabel: "qwen2.5:14b (extraction)",
  overallStatus: "REGRESSED",
  rows: [
    { metric: "aggregate", baseline: "90%", candidate: "85%", verdict: "REGRESSED" },
    { metric: "multi_page slice", baseline: "80%", candidate: "60%", verdict: "REGRESSED" },
  ],
};
