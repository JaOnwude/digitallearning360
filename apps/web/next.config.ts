import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Schools are served at {slug}.digitallearning360.localhost in development.
  allowedDevOrigins: ["digitallearning360.localhost", "*.digitallearning360.localhost"],
  // Off on purpose: every page is per-school and per-user, so prerendered shells would
  // add Suspense plumbing for little gain. Revisit for the public school websites.
  cacheComponents: false,
  poweredByHeader: false,
  // Security baseline (spec). The CSP itself is per-request (nonce) in src/proxy.ts.
  async headers() {
    const always = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(self)" },
    ];
    const deployed = process.env.NODE_ENV === "production" && process.env.VERCEL === "1";
    if (deployed) {
      always.push({ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" });
    }
    return [{ source: "/:path*", headers: always }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
