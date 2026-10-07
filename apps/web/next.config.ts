import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Schools are served at {slug}.digitallearning360.localhost in development.
  allowedDevOrigins: ["digitallearning360.localhost", "*.digitallearning360.localhost"],
  // Off on purpose: every page is per-school and per-user, so prerendered shells would
  // add Suspense plumbing for little gain. Revisit for the public school websites.
  cacheComponents: false,
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
