type HealthResponse = {
  status: "ok" | "degraded";
  environment: string;
  database: "ok" | "unreachable";
};

async function getHealth(): Promise<HealthResponse | null> {
  const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

  try {
    const response = await fetch(`${apiOrigin}/health`, { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as HealthResponse;
  } catch {
    return null;
  }
}

export default async function HomePage() {
  const health = await getHealth();

  return (
    <main style={{ padding: "2rem", maxWidth: "40rem" }}>
      <h1>Enterprise Agent Platform</h1>
      <p>Stage 1 scaffold — verifying the frontend can reach the API.</p>
      {health ? (
        <dl>
          <dt>API status</dt>
          <dd>{health.status}</dd>
          <dt>Database</dt>
          <dd>{health.database}</dd>
          <dt>Environment</dt>
          <dd>{health.environment}</dd>
        </dl>
      ) : (
        <p role="alert">API unreachable at {process.env.API_ORIGIN ?? "http://localhost:8000"}.</p>
      )}
    </main>
  );
}
