// Whether this build is the public demo deployment. Baked in at build
// time (see Dockerfile's ARG/ENV for NEXT_PUBLIC_DEMO_MODE) because
// next.config.ts's rewrites()/headers() have already established that
// Next.js resolves this kind of config once, at build time, not per
// request — this is a client-visible flag, not a security boundary: the
// backend's own Settings.demo_mode (app/core/config.py) independently
// enforces registration-disabled and rate limiting regardless of what
// this constant says. This only controls whether the frontend *explains*
// that mode to a visitor.
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

// Intentionally public — see apps/api/scripts/seed_demo_data.py's
// docstring. Not a secret, so safe to bake into a public bundle.
export const DEMO_ACCOUNT_EMAIL = "demo@example.com";
export const DEMO_ACCOUNT_PASSWORD = "underwriting-demo-2026";
