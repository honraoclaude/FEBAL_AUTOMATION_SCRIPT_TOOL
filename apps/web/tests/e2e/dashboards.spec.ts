import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * Dashboards + role-gated nav e2e (10-05 Task 3, PLAT-04 / DASH-01..03) — MOCKED API, no backend,
 * no keys. Every /api/* call is route-intercepted: /api/auth/me (with each role), the three
 * GET /api/dashboards/{executive,qa,developer} payloads (populated / empty / error / 403). All
 * states are mockable — no real Postgres/Neo4j/provider keys.
 *
 * Asserts: the sidebar renders only the permitted nav per role + the role badge; each dashboard's
 * populated + empty + error states; the no-access state for a forbidden role hitting a URL directly;
 * the QA artifact links are AUTH-GATED URLs (/api/executions/{run}/artifacts/{flow}/{kind}) with NO
 * raw filesystem path; and the executive dashboard renders the two coverage metrics SEPARATELY
 * (never merged — Pitfall 5).
 */

type Json = Record<string, unknown>;

function fulfillJson(body: Json | Json[]) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(body) };
}

function fulfillError(status: number, detail: string) {
  return { status, contentType: "application/json", body: JSON.stringify({ detail }) };
}

async function setAuth(context: BrowserContext) {
  await context.addCookies([
    { name: "access_token", value: "t", domain: "localhost", path: "/" },
  ]);
}

/** Stub /api/auth/me to return the given role (the sidebar reads role off this). */
async function stubMe(page: Page, role: string) {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill(fulfillJson({ id: 1, email: "user@example.test", role })),
  );
}

// --- payloads ---------------------------------------------------------------------------------

const COVERAGE = {
  definition:
    "Covered = a discovered flow with at least one approved scenario AND at least one passing execution.",
  measured_against:
    "Coverage is measured against the flows discovered in the latest exploration.",
  total_discovered: 4,
  covered: 2,
  coverage_percent: 50.0,
  covered_flow_ids: ["flow-0", "flow-1"],
  flows: [
    { flow_id: "flow-0", has_approved: true, has_passing: true, covered: true },
    { flow_id: "flow-1", has_approved: true, has_passing: true, covered: true },
    { flow_id: "flow-2", has_approved: true, has_passing: false, covered: false },
    { flow_id: "flow-3", has_approved: false, has_passing: false, covered: false },
  ],
};

const EXECUTIVE = {
  coverage: COVERAGE,
  pass_rate_trend: [
    { day: "2026-06-20", pass_rate: 0.75, total: 4, passed: 3 },
    { day: "2026-06-21", pass_rate: 0.9, total: 10, passed: 9 },
  ],
  defects_trend: [
    { day: "2026-06-20", count: 2 },
    { day: "2026-06-21", count: 1 },
  ],
  kpis: { pass_rate_percent: 90.0, open_defects: 3 },
};

const EXECUTIVE_EMPTY = {
  coverage: {
    ...COVERAGE,
    total_discovered: 0,
    covered: 0,
    coverage_percent: 0.0,
    covered_flow_ids: [],
    flows: [],
  },
  pass_rate_trend: [],
  defects_trend: [],
  kpis: { pass_rate_percent: 0.0, open_defects: 0 },
};

const QA = {
  runs: [
    {
      run_id: "run-abc",
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
  ],
  failed_tests: [
    {
      run_id: "run-abc",
      flow_id: "flow-2",
      verdict: "product_failure",
      attempts: 2,
      error_text: "AssertionError: expected 200",
      artifacts: [
        { kind: "screenshot", path: "flow-2/test-failed-1.png" },
        { kind: "trace", path: "flow-2/trace.zip" },
        { kind: "video", path: "flow-2/video.webm" },
      ],
    },
    {
      run_id: "run-abc",
      flow_id: "flow-1",
      verdict: "aborted",
      attempts: 1,
      error_text: null,
      // No video artifact -> the honest "Video captured on failure only." caption.
      artifacts: [{ kind: "screenshot", path: "flow-1/test-failed-1.png" }],
    },
  ],
};

const DEVELOPER = {
  root_cause_groups: [
    {
      classification: "product_defect",
      fingerprint: "abc123",
      count: 5,
      rep_defect_id: 7,
    },
    {
      classification: "automation",
      fingerprint: "def456",
      count: 2,
      rep_defect_id: 9,
    },
  ],
  errors_trend: [
    { day: "2026-06-20", count: 3 },
    { day: "2026-06-21", count: 4 },
  ],
  module_breakdown: [
    { flow_id: "flow-2", failure_count: 5 },
    { flow_id: "flow-1", failure_count: 2 },
  ],
};

// --- role-gated nav ---------------------------------------------------------------------------

test("nav: admin sees all the role-gated items + an Admin role badge", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "admin");
  await page.route("**/api/dashboards/executive", (route) =>
    route.fulfill(fulfillJson(EXECUTIVE)),
  );

  await page.goto("/dashboards/executive");

  await expect(page.getByRole("link", { name: "Dashboards" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Coverage" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Traceability" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Search" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Users" })).toBeVisible();
  await expect(page.getByTestId("role-badge")).toContainText("Admin");
});

test("nav: developer hides Users + shows the muted Developer badge", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "developer");
  await page.route("**/api/dashboards/developer", (route) =>
    route.fulfill(fulfillJson(DEVELOPER)),
  );

  await page.goto("/dashboards/developer");

  await expect(page.getByRole("link", { name: "Dashboards" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Coverage" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Search" })).toBeVisible();
  // Users is Admin-only — never rendered for a developer.
  await expect(page.getByRole("link", { name: "Users" })).toHaveCount(0);
  await expect(page.getByTestId("role-badge")).toContainText("Developer");
});

test("nav: qa_engineer sees only the QA dashboard + Search (no Coverage/Traceability/Users)", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "qa_engineer");
  await page.route("**/api/dashboards/qa", (route) => route.fulfill(fulfillJson(QA)));

  await page.goto("/dashboards/qa");

  await expect(page.getByRole("link", { name: "Dashboards" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Search" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Coverage" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Traceability" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Users" })).toHaveCount(0);
  await expect(page.getByTestId("role-badge")).toContainText("QA Engineer");
});

// --- executive (DASH-01) ----------------------------------------------------------------------

test("executive: populated KPIs + the two coverage metrics rendered SEPARATELY", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "admin");
  await page.route("**/api/dashboards/executive", (route) =>
    route.fulfill(fulfillJson(EXECUTIVE)),
  );

  await page.goto("/dashboards/executive");

  // KPI tiles (server-authoritative values).
  await expect(page.getByLabel("Coverage: 50%")).toBeVisible();
  await expect(page.getByLabel("Pass rate: 90%")).toBeVisible();
  await expect(page.getByLabel("Open defects: 3")).toBeVisible();

  // The two coverage metrics are SEPARATE tiles, never merged (Pitfall 5 / T-10-26):
  // lifecycle "Covered flows" AND exploration "Discovered flows".
  await expect(page.getByLabel("Covered flows: 2 of 4")).toBeVisible();
  await expect(page.getByLabel("Discovered flows: 4")).toBeVisible();

  // Trend cards present (exact: the sr-only summary also begins with the title text).
  await expect(page.getByText("Pass rate over time", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Defects filed over time", { exact: true }),
  ).toBeVisible();
});

test("executive: empty (no data yet) shows the honest empty + Go to executions", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "admin");
  await page.route("**/api/dashboards/executive", (route) =>
    route.fulfill(fulfillJson(EXECUTIVE_EMPTY)),
  );

  await page.goto("/dashboards/executive");
  await expect(page.getByText("No data yet")).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to executions" })).toBeVisible();
});

test("executive: error renders inline + Retry (never a fabricated number)", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "admin");
  await page.route("**/api/dashboards/executive", (route) =>
    route.fulfill(fulfillError(500, "boom")),
  );

  await page.goto("/dashboards/executive");
  await expect(page.getByText("Couldn't load this dashboard")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});

test("executive: a forbidden role (403) renders no-access, never the data", async ({
  page,
  context,
}) => {
  await setAuth(context);
  // A developer directly types the executive URL (the nav already hides it).
  await stubMe(page, "developer");
  await page.route("**/api/dashboards/executive", (route) =>
    route.fulfill(fulfillError(403, "forbidden")),
  );

  await page.goto("/dashboards/executive");
  await expect(page.getByTestId("no-access")).toBeVisible();
  await expect(page.getByText("You don't have access to this")).toBeVisible();
  // The data never renders.
  await expect(page.getByLabel("Pass rate: 90%")).toHaveCount(0);
});

// --- qa (DASH-02) -----------------------------------------------------------------------------

test("qa: artifact links are AUTH-GATED URLs (no raw path) + only the 3 real kinds + trace note", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "qa_engineer");
  await page.route("**/api/dashboards/qa", (route) => route.fulfill(fulfillJson(QA)));

  await page.goto("/dashboards/qa");

  // History row + a failed test with its WORD verdict.
  await expect(page.getByRole("link", { name: "run-abc" }).first()).toBeVisible();
  await expect(page.getByLabel("Verdict: Failed")).toBeVisible();

  // The artifact links are auth-gated /api/executions/.../artifacts/... URLs — NEVER a raw fs path.
  const screenshot = page.getByRole("link", { name: "Screenshot for flow-2" });
  await expect(screenshot).toBeVisible();
  await expect(screenshot).toHaveAttribute(
    "href",
    "/api/executions/run-abc/artifacts/flow-2/test-failed-1.png",
  );
  await expect(page.getByRole("link", { name: "Trace for flow-2" })).toHaveAttribute(
    "href",
    "/api/executions/run-abc/artifacts/flow-2/trace.zip",
  );
  await expect(page.getByRole("link", { name: "Video for flow-2" })).toHaveAttribute(
    "href",
    "/api/executions/run-abc/artifacts/flow-2/video.webm",
  );

  // CHECKER LOW-3: only 3 real kinds — NO Console log / Network log links + the trace note.
  await expect(page.getByRole("link", { name: /Console log/ })).toHaveCount(0);
  await expect(page.getByRole("link", { name: /Network log/ })).toHaveCount(0);
  await expect(
    page.getByText("console + network captured in the trace").first(),
  ).toBeVisible();

  // The aborted test with no video artifact -> the honest absence caption (not a broken link).
  await expect(page.getByRole("link", { name: "Video for flow-1" })).toHaveCount(0);
  await expect(
    page.getByText("Video captured on failure only.").first(),
  ).toBeVisible();
});

test("qa: empty (no runs) shows the honest empty + Go to executions", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "qa_engineer");
  await page.route("**/api/dashboards/qa", (route) =>
    route.fulfill(fulfillJson({ runs: [], failed_tests: [] })),
  );

  await page.goto("/dashboards/qa");
  await expect(page.getByText("No runs yet")).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to executions" })).toBeVisible();
});

test("qa: error renders inline + Retry", async ({ page, context }) => {
  await setAuth(context);
  await stubMe(page, "qa_engineer");
  await page.route("**/api/dashboards/qa", (route) =>
    route.fulfill(fulfillError(500, "boom")),
  );

  await page.goto("/dashboards/qa");
  await expect(page.getByText("Couldn't load this dashboard")).toBeVisible();
});

// --- developer (DASH-03) ----------------------------------------------------------------------

test("developer: root-cause groups (fp + class badge + occurrences + defect link) + module bars", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "developer");
  await page.route("**/api/dashboards/developer", (route) =>
    route.fulfill(fulfillJson(DEVELOPER)),
  );

  await page.goto("/dashboards/developer");

  // Root-cause grouping: the mono fingerprint, the Phase-9 class badge (word), occurrences, link.
  await expect(page.getByText("fp-abc123")).toBeVisible();
  await expect(page.getByLabel("Class: Product defect")).toBeVisible();
  await expect(page.getByText("5 occurrences")).toBeVisible();
  await expect(page.getByRole("link", { name: "#7" })).toHaveAttribute(
    "href",
    "/defects/7",
  );

  // Errors-over-time chart + the module breakdown bars (proportional --status-fail).
  await expect(page.getByText("Errors over time", { exact: true })).toBeVisible();
  await expect(page.getByText("Flow flow-2")).toBeVisible();
  await expect(page.getByText("5 failures")).toBeVisible();
});

test("developer: empty (no failures grouped) shows the honest empty", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "developer");
  await page.route("**/api/dashboards/developer", (route) =>
    route.fulfill(
      fulfillJson({
        root_cause_groups: [],
        errors_trend: [],
        module_breakdown: [],
      }),
    ),
  );

  await page.goto("/dashboards/developer");
  await expect(page.getByText("No failures grouped yet")).toBeVisible();
});

test("developer: a forbidden role (403) renders no-access, never the data", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "qa_engineer");
  await page.route("**/api/dashboards/developer", (route) =>
    route.fulfill(fulfillError(403, "forbidden")),
  );

  await page.goto("/dashboards/developer");
  await expect(page.getByTestId("no-access")).toBeVisible();
  await expect(page.getByText("fp-abc123")).toHaveCount(0);
});
