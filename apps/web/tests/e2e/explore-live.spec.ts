import { expect, test } from "@playwright/test";

/**
 * Live Exploration View e2e (plan 04-04 Task 3, EXPL-01) — MOCKED SSE, no backend, no keys.
 *
 * Every /api/* call is route-intercepted: /api/auth/me (dashboard layout), the on-mount
 * GET /api/executions/{runId} (so the page resolves "run exists", not 404), and the SSE
 * stream GET /api/explore/{runId}/events which is fulfilled with a SCRIPTED sequence of
 * ExploreProgressEvent frames in text/event-stream format — a running step, a REFUSED step,
 * and a terminal frame. The test asserts the UI-SPEC states render: counters update, a feed
 * row appears, the refused row shows the "Refused" text (meaning in text, not color-only),
 * and the terminal banner renders on the terminal frame.
 */

const RUN_ID = "e2e-run-abc123";

/** Build an SSE body of `event: step` frames from a list of ExploreProgressEvent objects. */
function sseBody(events: Record<string, unknown>[]): string {
  return (
    events
      .map((ev) => `event: step\ndata: ${JSON.stringify(ev)}\n`)
      .join("\n") + "\n"
  );
}

const FRAMES: Record<string, unknown>[] = [
  {
    run_id: RUN_ID,
    step: 1,
    pages_found: 1,
    actions_taken: 1,
    current_url: "https://demo.test/",
    current_title: "Home",
    screenshot_path: "state-1.png",
    feed_line: "step 1: chose [0] Products",
    cost_usd: 0.0012,
    elapsed_s: 3,
    stop_reason: null,
  },
  {
    run_id: RUN_ID,
    step: 2,
    pages_found: 2,
    actions_taken: 2,
    current_url: "https://demo.test/products",
    current_title: "Products",
    // A refused row (risk gate) — the meaning is in the TEXT (word "Refused").
    feed_line: "step 2: Refused [3] Delete account — destructive action blocked",
    screenshot_path: "state-2.png",
    cost_usd: 0.0031,
    elapsed_s: 6,
    stop_reason: null,
  },
  {
    run_id: RUN_ID,
    step: 3,
    pages_found: 3,
    actions_taken: 3,
    current_url: "https://demo.test/cart",
    current_title: "Cart",
    feed_line: "exploration complete",
    screenshot_path: "state-3.png",
    cost_usd: 0.0052,
    elapsed_s: 9,
    // Terminal: saturation -> the green "Complete" state (L-2 mapping).
    stop_reason: "saturation",
  },
];

test("live view renders connecting -> running -> refused -> terminal from a mocked SSE stream", async ({
  page,
  context,
}) => {
  // proxy.ts (Next 16 route protection) does a coarse access_token COOKIE-PRESENCE check and
  // redirects to /login when absent. The value is never verified here (the JWT secret lives in
  // the API tier and every /api call below is mocked), so a placeholder cookie satisfies the gate.
  await context.addCookies([
    {
      name: "access_token",
      value: "e2e-mock-token",
      domain: "localhost",
      path: "/",
    },
  ]);

  // Dashboard layout calls /api/auth/me — stub a logged-in user so the shell renders.
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 1, email: "admin@example.test" }),
    }),
  );

  // On-mount executions probe: 200 so the page does NOT enter the unknown-run/404 state.
  await page.route(`**/api/executions/${RUN_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: RUN_ID,
        kind: "explore",
        status: "running",
        error: null,
      }),
    }),
  );

  // The SSE stream — scripted frames in text/event-stream format.
  await page.route(`**/api/explore/${RUN_ID}/events`, (route) =>
    route.fulfill({
      status: 200,
      headers: {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
      },
      body: sseBody(FRAMES),
    }),
  );

  // Screenshots: serve a tiny transparent PNG so the <img> onLoad cross-fade fires.
  const png = Buffer.from(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489" +
      "0000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082",
    "hex",
  );
  await page.route(`**/api/explore/${RUN_ID}/screenshot/*`, (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: png }),
  );

  await page.goto(`/explore/${RUN_ID}`);

  // Counters update from the latest frame (pages found = 3 after the terminal frame).
  await expect(page.getByLabel("Pages found: 3")).toBeVisible();
  await expect(page.getByLabel("Actions: 3")).toBeVisible();

  // A normal feed row appeared.
  await expect(page.getByText("step 1: chose [0] Products")).toBeVisible();

  // The REFUSED row shows the "Refused" text (meaning carried in text, not color-only).
  await expect(
    page.getByText("Refused [3] Delete account — destructive action blocked"),
  ).toBeVisible();

  // Terminal banner renders on the terminal (saturation -> complete) frame.
  const banner = page.getByTestId("terminal-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Exploration complete");

  // Terminal -> the "Stop exploration" button is gone (running-only control).
  await expect(
    page.getByRole("button", { name: "Stop exploration" }),
  ).toHaveCount(0);
});
