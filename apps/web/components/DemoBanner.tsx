import { DEMO_ACCOUNT_EMAIL, DEMO_ACCOUNT_PASSWORD, DEMO_MODE } from "@/lib/demo";

export function DemoBanner() {
  if (!DEMO_MODE) return null;

  return (
    <div className="demo-banner" role="note">
      <span className="demo-banner-tag">Public demo</span>
      <p>
        This deployment uses <strong>synthetic data only</strong> — no real underwriting
        documents. Registration is disabled; log in with the shared demo account:{" "}
        <code>{DEMO_ACCOUNT_EMAIL}</code> / <code>{DEMO_ACCOUNT_PASSWORD}</code>. AI-generating
        actions (extraction, triage) are rate-limited per visitor to keep this demo free to run.
      </p>
    </div>
  );
}
