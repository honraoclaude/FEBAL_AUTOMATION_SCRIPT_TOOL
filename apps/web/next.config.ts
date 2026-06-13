import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // All browser API traffic goes through this rewrite so FastAPI is
  // same-origin: cookies are first-party (SameSite=Lax just works) and CORS
  // never exists (RESEARCH Pattern 4 / threat T-01-15).
  //
  // API_URL is the D-09 mode switch for the web tier:
  //   - compose:     API_URL=http://api:8000 (container-internal)
  //   - hybrid host: defaults to http://localhost:8001 — the API's HOST-facing
  //     port is 8001 (host 8000 is held by an unrelated project; plan 01-02
  //     decision). Container-internal port stays 8000.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_URL ?? "http://localhost:8001"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
