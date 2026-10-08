import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { OUTBOX_FILE, WORLD_FILE } from "./paths";

/**
 * Browser end-to-end tests for the pilot flows (spec M4, AC2/AC4/AC6/AC9/AC11).
 *
 * Runs its own API (8362) and production web build (3362) against a throwaway
 * `dl360_e2e` database and Redis db 1, so it never touches `pnpm dev` data or ports.
 * The API's start command first rebuilds that database (apps/api/tests/e2e_world.py),
 * so the world always exists before any test runs.
 *
 *   pnpm e2e            # from the repo root; needs Docker Postgres + Redis running
 */
const ROOT = path.resolve(import.meta.dirname, "..");
const API_PORT = 8362;
const WEB_PORT = 3362;
const PROXY_KEY = "e2e-proxy-key";

const apiEnv = {
  DL360_ENV: "local",
  DL360_DATABASE_URL: "postgresql+asyncpg://dl360_app:dl360_app@localhost:5436/dl360_e2e",
  DL360_MIGRATION_DATABASE_URL: "postgresql+asyncpg://dl360:dl360@localhost:5436/dl360_e2e",
  DL360_REDIS_URL: "redis://localhost:6380/1",
  DL360_PROXY_KEY: PROXY_KEY,
  DL360_BASE_DOMAIN: "digitallearning360.localhost",
  DL360_DEFAULT_SCHOOL_SLUG: "",
  DL360_EMAIL_OUTBOX_FILE: OUTBOX_FILE,
  DL360_PAYSTACK_SECRET_KEY: "", // online payment off: parents pay by transfer in these tests
};

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1, // the flows share one school and run in file order
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: `http://e2e.digitallearning360.localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `uv run python -m tests.e2e_world "${WORLD_FILE}" && uv run uvicorn app.main:app --port ${API_PORT}`,
      cwd: path.join(ROOT, "apps/api"),
      url: `http://127.0.0.1:${API_PORT}/healthz`,
      env: apiEnv,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `pnpm --filter web build && pnpm --filter web exec next start -p ${WEB_PORT}`,
      cwd: ROOT,
      url: `http://127.0.0.1:${WEB_PORT}`,
      env: { DL360_API_INTERNAL_URL: `http://127.0.0.1:${API_PORT}`, DL360_PROXY_KEY: PROXY_KEY },
      reuseExistingServer: false,
      timeout: 300_000,
    },
  ],
});
