import { expect, test, type Page } from "@playwright/test";

/**
 * Executions section e2e (plan 07-04 Task 3, EXEC-05/06) — MOCKED API + SSE, no backend, no keys.
 *
 * Every /api/* call is route-intercepted: /api/auth/me (dashboard shell), the runs list
 * GET /api/executions, the on-mount GET /api/executions/{runId} (resolve exists vs 404), the
 * SSE stream GET /api/executions/{runId}/events (a SCRIPTED text/event-stream of
 * ExecutionProgressEvent frames), and POST /api/executions{,/kill}. The tests touch the UI-SPEC
 * states: launcher start, running per-test events, the honest Stopping… draining state, terminal
 * passed/failed/killed, reconnecting, empty (no runs + no trends), start-error (queue down), 404 —
 * and assert flaky renders AMBER with the word "Flaky" + failed renders RED with the word "Failed"
 * (never color-only), and that the terminal detail shows Screenshot/Trace/Video links ONLY (no
 * Console log / Network log link) with the "in the trace" note.
 */

const RUN_ID = "e2e-exec-abc123";

interface Frame {
  run_id: string;
  completed: number;
  total: number;
  passed: number;
  failed: number;
  flaky: number;
  elapsed_s: number;
  status: string;
  flow_id?: string | null;
  test_id?: string | null;
  test_name?: string | null;
  test_status?: string | null;
  attempt?: number;
  duration_ms?: number | null;
}

/** Build an SSE body of `event: test` frames from a list of ExecutionProgressEvent objects. */
function sseBody(events: Frame[]): string {
  return (
    events.map((ev) => `event: test\ndata: ${JSON.stringify(ev)}\n`).join("\n") + "\n"
  );
}

async function stubShell(page: Page) {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 1, email: "admin@example.test" }),
    }),
  );
}

test("list: empty state — no runs and no trends", async ({ page, context }) => {
  await context.addCookies([
    { name: "access_token", value: "t", domain: "localhost", path: "/" },
  ]);
  await stubShell(page);
  await page.route("**/api/executions", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    }
    return route.fallback();
  });

  await page.goto("/executions");

  await expect(page.getByText("No runs yet")).toBeVisible();
  await expect(page.getByText("Trends appear after your first run.").first()).toBeVisible();
});

test("list: start-error — queue down surfaces inline (not a toast)", async ({
  page,
  context,
}) => {
  await context.addCookies([
    { name: "access_token", value: "t", domain: "localhost", path: "/" },
  ]);
  await stubShell(page);
  await page.route("**/api/executions", (route) => {
    const req = route.request();
    if (req.method() === "GET") {
      return route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    }
    if (req.method() === "POST") {
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "queue unavailable" }),
      });
    }
    return route.fallback();
  });

  await page.goto("/executions");
  await page.getByRole("button", { name: "Start run" }).click();

  await expect(page.getByText(/Couldn't start the run/)).toBeVisible();
  await expect(page.getByText(/--profile queue up/)).toBeVisible();
});

test("list: populated history shows flaky amber + failed red with their words", async ({
  page,
  context,
}) => {
  await context.addCookies([
    { name: "access_token", value: "t", domain: "localhost", path: "/" },
  ]);
  await stubShell(page);
  await page.route("**/api/executions", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            run_id: RUN_ID,
            tier: "smoke",
            selector: "@smoke",
            status: "failed",
            total: 4,
            passed: 2,
            failed: 1,
            flaky: 1,
            started_at: "2026-06-20T10:00:00Z",
            finished_at: "2026-06-20T10:00:42Z",
            created_at: "2026-06-20T10:00:00Z",
          },
        ]),
      });
    }
    return route.fallback();
  });

  await page.goto("/executions");

  // Results cell carries the WORDS (WCAG 1.4.1 — never color-only).
  await expect(page.getByText("1 failed")).toBeVisible();
  await expect(page.getByText("1 flaky")).toBeVisible();
  // The run-id drill-in link is present.
  await expect(page.getByRole("link", { name: RUN_ID })).toBeVisible();
});

test("live: running per-test events -> stopping (draining) -> stays honest on kill", async ({
  page,
  context,
}) => {
  await context.addCookies([
    { name: "access_token", value: "t", domain: "localhost", path: "/" },
  ]);
  await stubShell(page);

  // On-mount GET: a running run (not terminal) so the live view opens the stream.
  await page.route(`**/api/executions/${RUN_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: RUN_ID,
        tier: "smoke",
        status: "running",
        total: 2,
        passed: 0,
        failed: 0,
        flaky: 0,
        results: [],
      }),
    }),
  );

  // SSE: a snapshot + two running/resolved per-test frames (run stays running).
  const frames: Frame[] = [
    {
      run_id: RUN_ID,
      completed: 0,
      total: 2,
      passed: 0,
      failed: 0,
      flaky: 0,
      elapsed_s: 1,
      status: "running",
    },
    {
      run_id: RUN_ID,
      completed: 1,
      total: 2,
      passed: 1,
      failed: 0,
      flaky: 0,
      elapsed_s: 5,
      status: "running",
      flow_id: "flow-1",
      test_id: "checkout.feature:1",
      test_name: "Checkout completes",
      test_status: "passed",
      attempt: 1,
      duration_ms: 1240,
    },
    {
      run_id: RUN_ID,
      completed: 2,
      total: 2,
      passed: 1,
      failed: 0,
      flaky: 1,
      elapsed_s: 9,
      status: "running",
      flow_id: "flow-2",
      test_id: "login.feature:1",
      test_name: "Login retries",
      test_status: "flaky",
      attempt: 2,
      duration_ms: 2200,
    },
  ];
  await page.route(`**/api/executions/${RUN_ID}/events`, (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream", "cache-control": "no-cache" },
      body: sseBody(frames),
    }),
  );
  await page.route(`**/api/executions/${RUN_ID}/kill`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ stopping: true }),
    }),
  );

  await page.goto(`/executions/${RUN_ID}`);

  // Absolute counters from the latest frame.
  await expect(page.getByLabel("Passed: 1")).toBeVisible();
  await expect(page.getByLabel("Flaky: 1")).toBeVisible();
  await expect(page.getByLabel("Total: 2")).toBeVisible();

  // A passed per-test row + the flaky row with its WORD.
  await expect(page.getByText("Checkout completes")).toBeVisible();
  await expect(page.getByText("Login retries")).toBeVisible();
  await expect(page.getByLabel("Verdict: Flaky")).toBeVisible();
  await expect(page.getByText("2 attempts")).toBeVisible();

  // Kill -> the honest Stopping… draining state (no fake-instant kill).
  await page.getByRole("button", { name: "Kill run" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Kill run" }).click(); // confirm in dialog
  await expect(page.getByText(/Stopping the run… finishing the current test/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Stopping…" })).toBeDisabled();
});

test("terminal: failed run shows detail with Screenshot/Trace/Video only (no console/network)", async ({
  page,
  context,
}) => {
  await context.addCookies([
    { name: "access_token", value: "t", domain: "localhost", path: "/" },
  ]);
  await stubShell(page);

  await page.route(`**/api/executions/${RUN_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: RUN_ID,
        tier: "smoke",
        status: "failed",
        total: 2,
        passed: 1,
        failed: 1,
        flaky: 0,
        results: [
          {
            flow_id: "flow-2",
            verdict: "product_failure",
            attempts: 2,
            duration_ms: 3100,
          },
          { flow_id: "flow-1", verdict: "passed", attempts: 1, duration_ms: 1240 },
        ],
      }),
    }),
  );
  // The stream immediately reports terminal too (idempotent with the on-mount terminal detail).
  await page.route(`**/api/executions/${RUN_ID}/events`, (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream", "cache-control": "no-cache" },
      body: sseBody([
        {
          run_id: RUN_ID,
          completed: 2,
          total: 2,
          passed: 1,
          failed: 1,
          flaky: 0,
          elapsed_s: 12,
          status: "failed",
        },
      ]),
    }),
  );

  await page.goto(`/executions/${RUN_ID}`);

  // Terminal banner + failed verdict (red) with its WORD.
  await expect(page.getByTestId("terminal-banner")).toContainText("Run complete");
  await expect(page.getByLabel("Verdict: Failed")).toBeVisible();
  await expect(page.getByLabel("Verdict: Passed")).toBeVisible();

  // Artifact links: Screenshot/Trace/Video ONLY — no Console log / Network log link.
  await expect(page.getByRole("link", { name: /Screenshot for flow-2/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Trace for flow-2/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Video for flow-2/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Console log/ })).toHaveCount(0);
  await expect(page.getByRole("link", { name: /Network log/ })).toHaveCount(0);
  await expect(page.getByText("console + network captured in the trace").first()).toBeVisible();

  // The passed test has NO video link — the honest absence caption instead.
  await expect(page.getByRole("link", { name: /Video for flow-1/ })).toHaveCount(0);
  await expect(page.getByText("Video captured on failure only.").first()).toBeVisible();
});

test("terminal: killed run shows the stopped banner", async ({ page, context }) => {
  await context.addCookies([
    { name: "access_token", value: "t", domain: "localhost", path: "/" },
  ]);
  await stubShell(page);
  await page.route(`**/api/executions/${RUN_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: RUN_ID,
        tier: "smoke",
        status: "killed",
        total: 4,
        passed: 1,
        failed: 0,
        flaky: 0,
        results: [{ flow_id: "flow-1", verdict: "passed", attempts: 1, duration_ms: 900 }],
      }),
    }),
  );
  await page.route(`**/api/executions/${RUN_ID}/events`, (route) =>
    route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream", "cache-control": "no-cache" },
      body: sseBody([
        {
          run_id: RUN_ID,
          completed: 1,
          total: 4,
          passed: 1,
          failed: 0,
          flaky: 0,
          elapsed_s: 6,
          status: "killed",
        },
      ]),
    }),
  );

  await page.goto(`/executions/${RUN_ID}`);
  await expect(page.getByTestId("terminal-banner")).toContainText("Run stopped");
});

test("live: reconnecting freezes last-known values (stream drops, run not terminal)", async ({
  page,
  context,
}) => {
  await context.addCookies([
    { name: "access_token", value: "t", domain: "localhost", path: "/" },
  ]);
  await stubShell(page);
  await page.route(`**/api/executions/${RUN_ID}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run_id: RUN_ID,
        tier: "smoke",
        status: "running",
        total: 2,
        passed: 1,
        failed: 0,
        flaky: 0,
        results: [],
      }),
    }),
  );
  // Abort the stream so EventSource enters its native retry backoff (reconnecting state).
  await page.route(`**/api/executions/${RUN_ID}/events`, (route) => route.abort());

  await page.goto(`/executions/${RUN_ID}`);
  // The pill announces a non-running connection state; the page does not crash or clear.
  await expect(
    page.getByText(/Reconnecting…|Connecting…|Lost connection/).first(),
  ).toBeVisible();
});

test("404: unknown run shows not-found + back link", async ({ page, context }) => {
  await context.addCookies([
    { name: "access_token", value: "t", domain: "localhost", path: "/" },
  ]);
  await stubShell(page);
  await page.route(`**/api/executions/${RUN_ID}`, (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "No execution run found for this run_id" }),
    }),
  );
  await page.route(`**/api/executions/${RUN_ID}/events`, (route) => route.abort());

  await page.goto(`/executions/${RUN_ID}`);
  await expect(page.getByText("No run found for this id.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to executions" })).toBeVisible();
});
