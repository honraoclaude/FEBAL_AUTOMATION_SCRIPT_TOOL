import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright e2e config (plan 04-04 Task 3) — first e2e harness for apps/web.
 *
 * The Live Exploration View e2e (tests/e2e/explore-live.spec.ts) is fully SELF-CONTAINED: it
 * route-intercepts every /api/* call (auth/me, executions, and the SSE events stream) so it
 * needs NO running backend and NO provider keys — it asserts the page renders the UI-SPEC
 * states from a SCRIPTED SSE frame sequence. The web dev server is started by the runner.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  reporter: "list",
  timeout: 30_000,
  use: {
    baseURL: "http://localhost:3100",
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    // A dedicated port (3100) so the e2e never collides with a dev server on 3000. The page
    // is rendered with all backend calls mocked, so no API_URL/backend is required.
    command: "npm run dev -- --port 3100",
    url: "http://localhost:3100/login",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
