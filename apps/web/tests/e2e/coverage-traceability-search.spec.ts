import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * Coverage + Traceability + Search e2e (10-06 Task 3, DASH-04/05/06) — MOCKED API, no backend, no
 * keys. Every /api/* call is route-intercepted: /api/auth/me (role), GET /api/coverage/flows +
 * /api/coverage (the two metrics), GET /api/traceability (chain / honest gaps / no-chain), GET
 * /api/search (populated / no-results / unavailable-503). All states are mockable.
 *
 * Asserts: the coverage panel renders the lifecycle %+definition+per-flow table + the SEPARATE
 * ground-truth card; graph-down + empty states. The traceability viewer renders the chain for a
 * picked artifact with honest gaps, plus the resting + no-chain states. The search UI renders typed
 * highlighted hits, no-results, and the honest "search unavailable" 503 distinct from no-results.
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

async function stubMe(page: Page, role: string) {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill(fulfillJson({ id: 1, email: "user@example.test", role })),
  );
}

// --- payloads ---------------------------------------------------------------------------------

const COVERAGE_FLOWS = {
  definition:
    "Covered = a discovered flow with at least one approved scenario AND at least one passing execution. Coverage = covered flows ÷ total discovered flows.",
  measured_against:
    "Coverage is measured against the flows discovered in the latest exploration.",
  total_discovered: 4,
  covered: 2,
  coverage_percent: 50.0,
  covered_flow_ids: ["flow-0", "flow-1"],
  flows: [
    { flow_id: "flow-0", has_approved: true, has_passing: true, covered: true },
    { flow_id: "flow-2", has_approved: true, has_passing: false, covered: false },
  ],
};

const GROUND_TRUTH = {
  screens_total: 10,
  screens_covered: 7,
  flows_total: 4,
  flows_covered: 3,
  coverage_percent: 70.0,
  measured: true,
};

const CHAIN = {
  entry: { type: "flow", id: "flow-0" },
  flow: {
    flow_id: "flow-0",
    name: "Login flow",
    category: "auth",
    risk_tier: "high",
    step_count: 4,
  },
  flow_note: null,
  scenarios: [
    {
      id: 12,
      flow_id: "flow-0",
      run_id: "run-abc",
      feature_name: "Login",
      status: "approved",
    },
  ],
  scripts: [{ run_id: "run-abc", path: "workspaces/run-abc/test_login.py", derived: true }],
  executions: [
    {
      run_id: "run-abc",
      flow_id: "flow-0",
      verdict: "passed",
      attempts: 1,
      duration_ms: 1200,
      tier: "smoke",
      status: "passed",
    },
  ],
  artifacts: [],
  // No defect linked -> the honest "No defect linked." gap.
  defects: [],
};

const EMPTY_CHAIN = {
  entry: { type: "flow", id: "nope" },
  flow: null,
  flow_note: null,
  scenarios: [],
  scripts: [],
  executions: [],
  artifacts: [],
  defects: [],
};

const SEARCH_RESULTS = {
  query: "login",
  count: 2,
  hits: [
    {
      index: "executions",
      id: "run-abc",
      score: 1.2,
      source: { run_id: "run-abc", title: "Login smoke run" },
      highlight: { title: ["<em>Login</em> smoke run"] },
    },
    {
      index: "failures",
      id: "7",
      score: 0.9,
      source: { run_id: "run-abc", defect_id: 7, message: "login assertion failed" },
      highlight: { message: ["<em>login</em> assertion failed"] },
    },
  ],
};

// --- coverage (DASH-04) -----------------------------------------------------------------------

test("coverage: lifecycle %+definition+per-flow table + the SEPARATE ground-truth card", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "admin");
  await page.route("**/api/coverage/flows", (route) =>
    route.fulfill(fulfillJson(COVERAGE_FLOWS)),
  );
  await page.route("**/api/coverage", (route) =>
    route.fulfill(fulfillJson(GROUND_TRUTH)),
  );

  await page.goto("/coverage");

  // Lifecycle coverage: the % meter + the honest definition + the per-flow table.
  await expect(page.getByLabel("Coverage: 50%")).toBeVisible();
  await expect(
    page.getByText("Coverage = covered flows ÷ total discovered flows.", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "flow-0" })).toHaveAttribute(
    "href",
    "/graph/flows/flow-0",
  );
  // flow-2 is not covered -> the muted "Not covered" word (never color alone).
  await expect(page.getByLabel("Not covered").first()).toBeVisible();

  // The SEPARATE ground-truth card with its OWN definition (never merged — Pitfall 5 / T-10-31).
  const gt = page.getByTestId("ground-truth-card");
  await expect(gt).toBeVisible();
  // The card heading (first match — "Exploration completeness" also appears in the meter label +
  // the definition sentence; the card is its own SEPARATE metric, never merged with lifecycle).
  await expect(gt.getByText("Exploration completeness").first()).toBeVisible();
  await expect(gt.getByLabel("Exploration completeness: 70%")).toBeVisible();
  await expect(gt.getByText("7 of 10 screens")).toBeVisible();
});

test("coverage: graph-down (503) renders the honest unavailable state + Retry", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "admin");
  await page.route("**/api/coverage/flows", (route) =>
    route.fulfill(fulfillError(503, "graph unavailable")),
  );

  await page.goto("/coverage");
  await expect(page.getByText("Graph unavailable")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  // Never a fabricated percentage.
  await expect(page.getByLabel("Coverage: 50%")).toHaveCount(0);
});

test("coverage: empty (no discovered flows) -> honest empty + Go to targets", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "admin");
  await page.route("**/api/coverage/flows", (route) =>
    route.fulfill(
      fulfillJson({
        ...COVERAGE_FLOWS,
        total_discovered: 0,
        covered: 0,
        coverage_percent: 0.0,
        covered_flow_ids: [],
        flows: [],
      }),
    ),
  );

  await page.goto("/coverage");
  await expect(page.getByText("No discovered flows yet")).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to targets" })).toBeVisible();
});

// --- traceability (DASH-05) -------------------------------------------------------------------

test("traceability: resting before a lookup -> the honest caption", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "admin");

  await page.goto("/traceability");
  await expect(page.getByTestId("trace-resting")).toBeVisible();
});

test("traceability: a picked flow renders the chain with an honest 'No defect linked.' gap", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "admin");
  await page.route("**/api/traceability**", (route) =>
    route.fulfill(fulfillJson(CHAIN)),
  );

  await page.goto("/traceability?type=flow&id=flow-0");

  // The ordered chain: present nodes drill to the detail pages.
  await expect(page.getByRole("link", { name: "flow-0" })).toHaveAttribute(
    "href",
    "/graph/flows/flow-0",
  );
  await expect(page.getByRole("link", { name: "12" })).toHaveAttribute(
    "href",
    "/scenarios/12",
  );
  await expect(page.getByRole("link", { name: "run-abc" })).toHaveAttribute(
    "href",
    "/executions/run-abc",
  );
  // The honest gap: no defect linked (a passing flow with no defect) — never a fabricated node.
  const defectGap = page.getByTestId("chain-gap").filter({ hasText: "No defect linked." });
  await expect(defectGap).toBeVisible();
});

test("traceability: an unknown id -> the honest 'No chain found' state (not a 404)", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "admin");
  await page.route("**/api/traceability**", (route) =>
    route.fulfill(fulfillJson(EMPTY_CHAIN)),
  );

  await page.goto("/traceability?type=flow&id=nope");
  await expect(page.getByTestId("trace-no-chain")).toBeVisible();
});

// --- search (DASH-06) -------------------------------------------------------------------------

test("search: populated -> typed badges + the server highlight rendered as safe emphasis", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "admin");
  await page.route("**/api/search**", (route) =>
    route.fulfill(fulfillJson(SEARCH_RESULTS)),
  );

  await page.goto("/search?q=login");

  await expect(page.getByText('2 results for "login"')).toBeVisible();
  // The typed badges (word + hue, never color alone).
  await expect(page.getByLabel("Type: Execution")).toBeVisible();
  await expect(page.getByLabel("Type: Failure")).toBeVisible();
  // The server highlight fragment rendered as emphasized text (the matched term is an <em>).
  await expect(page.getByText("smoke run", { exact: false }).first()).toBeVisible();
  // A drill-in link to the source detail page.
  await expect(page.getByRole("link", { name: "Open" }).first()).toBeVisible();
});

test("search: no-results echoes the query (never a fabricated hit)", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "admin");
  await page.route("**/api/search**", (route) =>
    route.fulfill(fulfillJson({ query: "zzz", count: 0, hits: [] })),
  );

  await page.goto("/search?q=zzz");
  await expect(page.getByTestId("search-no-results")).toBeVisible();
  await expect(page.getByText('Nothing matched "zzz".', { exact: false })).toBeVisible();
});

test("search: ES-down (503) -> the honest 'search unavailable', NOT an empty list", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, "admin");
  await page.route("**/api/search**", (route) =>
    route.fulfill(fulfillError(503, "search unavailable")),
  );

  await page.goto("/search?q=login");
  await expect(page.getByTestId("search-unavailable")).toBeVisible();
  await expect(page.getByText("Search is unavailable")).toBeVisible();
  // Distinct from no-results — the no-results block never renders.
  await expect(page.getByTestId("search-no-results")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});
