import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Schools are served at {slug}.digitallearning360.localhost in development.
  allowedDevOrigins: ["digitallearning360.localhost", "*.digitallearning360.localhost"],
  cacheComponents: true,
  partialPrefetching: true,
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
