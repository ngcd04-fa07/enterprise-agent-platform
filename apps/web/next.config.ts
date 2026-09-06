import type { NextConfig } from "next";

// Browser requests hit the frontend origin at /api/* and get proxied here,
// keeping frontend + API same-origin from the browser's point of view so
// the session cookie (see docs/architecture.md, auth decision) is always
// first-party. Server Components call the API origin directly instead.
const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

// Stage 20: this is the component that actually serves HTML to a
// browser (see app/main.py's SecurityHeadersMiddleware docstring for why
// the API side only carries the two headers that make sense for a JSON
// service, not these) — CSP/frame-ancestors belong here.
//
// 'unsafe-inline' on script-src/style-src is a deliberate, stated
// relaxation, not an oversight: Next.js's production output includes
// inline bootstrap/hydration scripts and (via styled-jsx or any inline
// style prop) inline styles that a strict nonce-only policy would need
// per-request nonce plumbing to keep working — real engineering effort
// this stage doesn't take on speculatively. frame-ancestors 'none' (this
// app should never be embedded in a frame) is enforced with no such
// relaxation needed, and is the highest-value single protection here
// (equivalent to X-Frame-Options: DENY, which is also set for older
// browsers that don't understand frame-ancestors).
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

// HSTS only when this is genuinely running behind HTTPS/production TLS —
// emitting it under plain HTTP (this project's actual current
// deployment, ENVIRONMENT=development in docker-compose.yml) would make
// a browser refuse plain HTTP to this host afterward: a real local-dev
// trap, not a hardening win. Mirrors the API's own Secure-cookie/HSTS
// gating (see app/api/routes/auth.py, app/security/headers.py) so both
// halves of the stack agree on the same single source of truth.
const isProductionDeployment = process.env.ENVIRONMENT !== "development";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin}/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: CSP },
          ...(isProductionDeployment
            ? [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }]
            : []),
        ],
      },
    ];
  },
};

export default nextConfig;
