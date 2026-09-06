import { DEMO_EVAL_COMPARISON, DEMO_TRACE_ROWS } from "@/lib/demoTraceData";

// Static, read-only — real numbers from one actual recorded run (see
// lib/demoTraceData.ts for exactly which run and why this isn't a live
// query). Not connected to whatever submission the visitor is looking
// at: this app has no per-submission trace/eval viewer (see
// docs/architecture.md's "Public demo deployment" entry for why), so
// this is presented plainly as a real example, not implied to be live.
export function TraceEvalShowcase() {
  const totalLatencyMs = DEMO_TRACE_ROWS.reduce((sum, row) => sum + row.latencyMs, 0);

  return (
    <section className="card">
      <h2>5. Trace &amp; evaluation</h2>
      <p className="muted">
        A real, previously-recorded example — not a live query against this submission. Every AI
        call this platform makes (embedding, generation, retrieval) is traced with latency and
        outcome; this is the exact trace from one real run of the seed script that populated this
        demo.
      </p>

      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Call</th>
              <th>Provider / model</th>
              <th>Route reason</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody>
            {DEMO_TRACE_ROWS.map((row, index) => (
              <tr key={index}>
                <td>
                  {row.callType}
                  <div className="muted">{row.note}</div>
                </td>
                <td>
                  {row.provider} / {row.model}
                </td>
                <td className="muted">{row.routeReason ?? "—"}</td>
                <td>{row.latencyMs.toFixed(1)} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">
        {DEMO_TRACE_ROWS.length} calls traced · {totalLatencyMs.toFixed(0)} ms total. Notice the
        routing split: per-chunk extraction stays on the fast <code>qwen2.5:3b</code> tier;
        reasoning-heavy triage synthesis escalates to the larger <code>qwen2.5:14b</code> tier and
        takes noticeably longer — a real, visible cost/quality tradeoff, not a hidden one.
      </p>

      <h3>Release comparison example</h3>
      <p className="muted">
        A real recorded evaluation-harness comparison: extraction accuracy on{" "}
        {DEMO_EVAL_COMPARISON.baselineLabel} (baseline) vs. {DEMO_EVAL_COMPARISON.candidateLabel}{" "}
        (candidate), same 4-case dataset.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th>Baseline</th>
              <th>Candidate</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {DEMO_EVAL_COMPARISON.rows.map((row) => (
              <tr key={row.metric}>
                <td>{row.metric}</td>
                <td>{row.baseline}</td>
                <td>{row.candidate}</td>
                <td>
                  <span className={`flag-badge flag-${row.verdict.toLowerCase()}`}>
                    {row.verdict}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">
        Overall release verdict:{" "}
        <span className="flag-badge flag-regressed">{DEMO_EVAL_COMPARISON.overallStatus}</span> —
        the larger model scored worse on this dataset in this run. An aggregate number alone would
        have hidden the <code>multi_page</code> slice regressing further than the aggregate did;
        this harness flags a regression the moment any single row shows one, not just the average.
      </p>
    </section>
  );
}
