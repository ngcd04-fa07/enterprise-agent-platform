interface OverviewItem {
  title: string;
  description: string;
}

const OVERVIEW_ITEMS: OverviewItem[] = [
  {
    title: "Multi-tenant document intelligence",
    description:
      "Every organisation's submissions, documents, and results are isolated in SQL, not just the UI — cross-tenant access fails even against a correctly-guessed ID.",
  },
  {
    title: "Evidence-grounded extraction",
    description:
      "Structured fields are extracted one document chunk at a time, so every value traces back to the exact page it came from — never asked of the model after the fact.",
  },
  {
    title: "Deterministic triage",
    description:
      "The approve/refer recommendation is always computed by plain-code rules, never by a model. An LLM only narrates decisions that are already made and can't overrule them.",
  },
  {
    title: "Human approval",
    description:
      "A triage recommendation never applies itself — every run requires an explicit, audited human approval before it affects a submission.",
  },
  {
    title: "Model routing",
    description:
      "Routine per-chunk extraction runs on a fast model; reasoning-heavy synthesis escalates to a larger one — a caller-declared complexity hint, not a guess.",
  },
  {
    title: "Tracing & evaluation",
    description:
      "Every model, embedding, and retrieval call is traced with latency and outcome, and a real evaluation harness measures extraction accuracy and flags release regressions.",
  },
];

export function PlatformOverview() {
  return (
    <section className="overview">
      <h2>What this platform demonstrates</h2>
      <div className="overview-grid">
        {OVERVIEW_ITEMS.map((item) => (
          <div key={item.title} className="overview-item">
            <h3>{item.title}</h3>
            <p className="muted">{item.description}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
