import type { NextConfig } from "next";

// Browser requests hit the frontend origin at /api/* and get proxied here,
// keeping frontend + API same-origin from the browser's point of view so
// the session cookie (see docs/architecture.md, auth decision) is always
// first-party. Server Components call the API origin directly instead.
const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin}/:path*`,
      },
    ];
  },
};

export default nextConfig;
