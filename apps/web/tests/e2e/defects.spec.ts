import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * Defects review-queue e2e (09-05 Task 3, JIRA-02 / 09-UI-SPEC) — MOCKED API, no backend, no keys.
 *
 * Every /api/* call is route-intercepted: /api/auth/me (the dashboard shell), the queue
 * GET /api/defects?status=&class=, the calibration GET /api/defects/calibration, the detail
 * GET /api/defects/{id}, and the apply/reject POSTs. No real Jira, no provider keys — all states
 * mockable. The tests cover the UI-SPEC states for the list (populated/empty/filter/error), the
 * calibration panel (not-measured / gates-not-met / gates-met), and the detail (draft-configured
 * apply→applied-with-key, draft-not-configured disabled→inline caption, applying-pending,
 * apply-failed-stays-draft, update-on-duplicate label+toast, reject-confirm→rejected, 404) — and
 * assert NO fabricated state crosses the boundary (a Jira key / "Applied" appears only when the
 * mock reports it).
 */

type Json = Record<string, unknown>;

function fulfillJson(body: Json | Json[]) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(body) };
}

function fulfillError(status: number, detail: string) {
  return { status, contentType: "application/json", body: JSON.stringify({ detail }) };
}

const QUEUE = [
  {
    id: 1,
    run_id: "run-1",
    flow_id: "flow-0",
    classification: "product_defect",
    confidence: 88,
    fingerprint: "fp-abc123",
    jira_key: null,
    status: "draft",
    created_at: "2026-06-20T13:00:00Z",
    updated_at: "2026-06-20T14:00:00Z",
  },
  {
    id: 2,
    run_id: "run-1",
    flow_id: "flow-1",
    classification: "automation",
    confidence: 42,
    fingerprint: "fp-def456",
    jira_key: null,
    status: "draft",
    created_at: "2026-06-20T12:00:00Z",
    updated_at: "2026-06-20T12:30:00Z",
  },
];

const NOT_MEASURED = {
  classification_accuracy: null,
  draft_precision: null,
  confidence_threshold: 75,
  autonomous_enabled: false,
};

const GATES_NOT_MET = {
  classification_accuracy: 80,
  draft_precision: 88,
  confidence_threshold: 75,
  autonomous_enabled: false,
};

const GATES_MET = {
  classification_accuracy: 92,
  draft_precision: 95,
  confidence_threshold: 75,
  autonomous_enabled: true,
};

const DETAIL_DRAFT = {
  ...QUEUE[0],
  proposed_issue: {
    summary: "Checkout total is wrong",
    description: "The cart total does not include tax.",
    enriched: false,
    steps: ["Add an item", "Open the cart"],
    expected: "The flow to succeed.",
    actual: "AssertionError: expected $10 got $8",
    severity: "Major",
    priority: "High",
  },
  evidence: {
    error_type: "AssertionError",
    dom_diff: "- $8\n+ $10",
    healing_history: "No healing attempted for this run.",
    infra_health: "up",
    artifacts: [{ kind: "trace", path: "flow-0/test/trace.zip" }],
  },
  attachments: [{ kind: "trace", path: "flow-0/test/trace.zip" }],
  confidence_threshold: 75,
  last_action: null,
};

async function authCookie(context: BrowserContext) {
  await context.addCookies([
    { name: "access_token", value: "e2e-mock-token", domain: "localhost", path: "/" },
  ]);
}

async function mockShell(page: Page) {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill(fulfillJson({ id: 1, email: "admin@example.test" })),
  );
}

// --- List + calibration --------------------------------------------------------------------

test("list renders the queue with class badge, confidence meter, status, and source refs", async ({
  page,
  context,
}) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/defects/calibration", (route) =>
    route.fulfill(fulfillJson(GATES_NOT_MET)),
  );
  await page.route("**/api/defects?status=draft*", (route) => route.fulfill(fulfillJson(QUEUE)));

  await page.goto("/defects");

  await expect(page.getByRole("heading", { name: "Defects" })).toBeVisible();
  await expect(page.getByRole("link", { name: "flow-0 failed" })).toBeVisible();
  // Target the class BADGES (the filter segments duplicate the class words) via their aria-label.
  await expect(page.getByLabel("Class: Product defect")).toBeVisible();
  await expect(page.getByLabel("Class: Automation")).toBeVisible();
  // The confidence numeral renders strictly from the server.
  await expect(page.getByText("88", { exact: true })).toBeVisible();
  // The source refs (test↔flow↔execution).
  await expect(page.getByText("run run-1 · flow-0")).toBeVisible();
});

test("calibration panel renders the not-measured honest state", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/defects/calibration", (route) =>
    route.fulfill(fulfillJson(NOT_MEASURED)),
  );
  await page.route("**/api/defects?status=draft*", (route) => route.fulfill(fulfillJson(QUEUE)));

  await page.goto("/defects");

  await expect(page.getByText("Calibration")).toBeVisible();
  await expect(page.getByText(/Not measured yet\. Run the accuracy harness/)).toBeVisible();
  // No fabricated percentage — the not-measured tiles read "—".
  await expect(page.getByText("Classification accuracy", { exact: true })).toBeVisible();
});

test("calibration panel shows Met when gates are met and the flag is On", async ({
  page,
  context,
}) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/defects/calibration", (route) => route.fulfill(fulfillJson(GATES_MET)));
  await page.route("**/api/defects?status=draft*", (route) => route.fulfill(fulfillJson(QUEUE)));

  await page.goto("/defects");

  await expect(page.getByText("92%")).toBeVisible();
  await expect(page.getByText("Met").first()).toBeVisible();
  await expect(page.getByText("On", { exact: true })).toBeVisible();
});

test("calibration panel shows Not met yet when a gate is below target", async ({
  page,
  context,
}) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/defects/calibration", (route) =>
    route.fulfill(fulfillJson(GATES_NOT_MET)),
  );
  await page.route("**/api/defects?status=draft*", (route) => route.fulfill(fulfillJson(QUEUE)));

  await page.goto("/defects");

  await expect(page.getByText("Not met yet").first()).toBeVisible();
  await expect(page.getByText("Off", { exact: true })).toBeVisible();
});

test("class filter deep-links the class param", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/defects/calibration", (route) =>
    route.fulfill(fulfillJson(GATES_NOT_MET)),
  );
  // The general draft route is registered FIRST; the specific class route is registered LAST so
  // Playwright (reverse registration order) matches the class-filtered request to the empty result.
  await page.route("**/api/defects?status=draft*", (route) => route.fulfill(fulfillJson(QUEUE)));
  await page.route("**/api/defects?status=draft&class=infrastructure", (route) =>
    route.fulfill(fulfillJson([])),
  );

  await page.goto("/defects");
  await page.getByRole("button", { name: "Infrastructure" }).click();

  await expect(page).toHaveURL(/class=infrastructure/);
  await expect(page.getByText("No matching defects")).toBeVisible();
  await expect(page.getByRole("button", { name: "View drafts" })).toBeVisible();
});

test("list renders the no-defects empty state", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/defects/calibration", (route) =>
    route.fulfill(fulfillJson(NOT_MEASURED)),
  );
  await page.route("**/api/defects?status=draft*", (route) => route.fulfill(fulfillJson([])));

  await page.goto("/defects");

  await expect(page.getByText("No defects yet")).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to executions" })).toBeVisible();
});

test("list renders the inline error + Retry state", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/defects/calibration", (route) =>
    route.fulfill(fulfillJson(NOT_MEASURED)),
  );
  await page.route("**/api/defects?status=draft*", (route) =>
    route.fulfill(fulfillError(500, "boom")),
  );

  await page.goto("/defects");

  await expect(page.getByText(/Couldn't load defects/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});

// --- Detail --------------------------------------------------------------------------------

test("detail renders the proposed issue, evidence, fingerprint, and the trace attachment link", async ({
  page,
  context,
}) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/defects/1", (route) => route.fulfill(fulfillJson(DETAIL_DRAFT)));

  await page.goto("/defects/1");

  await expect(page.getByRole("heading", { name: "Checkout total is wrong" })).toBeVisible();
  await expect(page.getByText("Proposed Jira issue")).toBeVisible();
  await expect(page.getByText("AssertionError: expected $10 got $8")).toBeVisible();
  // The honest no-LLM caption (enriched=false).
  await expect(page.getByText(/Description written without an LLM/)).toBeVisible();
  await expect(page.getByText("Fingerprint fp-abc123")).toBeVisible();
  // The auth-gated artifact link is built from the run-relative basename — NEVER a raw path.
  const trace = page.getByRole("link", { name: "Trace for defect 1" });
  await expect(trace).toHaveAttribute(
    "href",
    "/api/executions/run-1/artifacts/flow-0/test/trace.zip",
  );
  // An absent kind shows the honest caption, not a broken link.
  await expect(page.getByText("Video captured on failure only.")).toBeVisible();
});

test("apply on a configured draft flips to Applied with the real server key", async ({
  page,
  context,
}) => {
  await authCookie(context);
  await mockShell(page);
  let applied = false;
  await page.route("**/api/defects/1", (route) =>
    route.fulfill(
      fulfillJson(
        applied
          ? { ...DETAIL_DRAFT, status: "applied", jira_key: "PROJ-123", last_action: "create" }
          : DETAIL_DRAFT,
      ),
    ),
  );
  await page.route("**/api/defects/1/apply", (route) => {
    applied = true;
    return route.fulfill(
      fulfillJson({ ...DETAIL_DRAFT, status: "applied", jira_key: "PROJ-123", last_action: "create" }),
    );
  });

  await page.goto("/defects/1");
  await expect(page.getByRole("button", { name: "Apply — create Jira issue" })).toBeEnabled();
  await page.getByRole("button", { name: "Apply — create Jira issue" }).click();

  // The status flips only on the real server response; the real key shows.
  await expect(page.getByText("Issue filed — PROJ-123")).toBeVisible();
  await expect(page.getByText("Filed to")).toBeVisible();
  await expect(page.getByText("PROJ-123").first()).toBeVisible();
});

test("update-on-duplicate reads 'Apply — update {key}' and toasts 'Issue updated'", async ({
  page,
  context,
}) => {
  await authCookie(context);
  await mockShell(page);
  // A draft that already carries a Jira key → Apply reads "update {key}".
  const dupDraft = { ...DETAIL_DRAFT, jira_key: "PROJ-9" };
  await page.route("**/api/defects/1", (route) => route.fulfill(fulfillJson(dupDraft)));
  await page.route("**/api/defects/1/apply", (route) =>
    route.fulfill(
      fulfillJson({ ...dupDraft, status: "applied", jira_key: "PROJ-9", last_action: "update" }),
    ),
  );

  await page.goto("/defects/1");
  await expect(page.getByRole("button", { name: "Apply — update PROJ-9" })).toBeVisible();
  await page.getByRole("button", { name: "Apply — update PROJ-9" }).click();

  await expect(page.getByText("Issue updated — PROJ-9")).toBeVisible();
});

test("apply when Jira is not configured renders the inline caption and stays a draft", async ({
  page,
  context,
}) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/defects/1", (route) => route.fulfill(fulfillJson(DETAIL_DRAFT)));
  await page.route("**/api/defects/1/apply", (route) =>
    route.fulfill(fulfillError(400, "Jira is not configured")),
  );

  await page.goto("/defects/1");
  await page.getByRole("button", { name: "Apply — create Jira issue" }).click();

  await expect(page.getByText(/Jira isn't configured/)).toBeVisible();
  // Still a draft — no fabricated "Applied".
  await expect(page.getByText("Status: Applied")).toHaveCount(0);
});

test("apply failure renders the inline error + Retry and stays a draft", async ({
  page,
  context,
}) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/defects/1", (route) => route.fulfill(fulfillJson(DETAIL_DRAFT)));
  await page.route("**/api/defects/1/apply", (route) =>
    route.fulfill(fulfillError(502, "Jira unreachable")),
  );

  await page.goto("/defects/1");
  await page.getByRole("button", { name: "Apply — create Jira issue" }).click();

  await expect(page.getByText(/Couldn't file the issue to Jira/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(page.getByText("Status: Applied")).toHaveCount(0);
});

test("reject requires confirmation then marks the defect rejected", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  let rejected = false;
  await page.route("**/api/defects/1", (route) =>
    route.fulfill(fulfillJson(rejected ? { ...DETAIL_DRAFT, status: "rejected" } : DETAIL_DRAFT)),
  );
  await page.route("**/api/defects/1/reject", (route) => {
    rejected = true;
    return route.fulfill(fulfillJson({ ...DETAIL_DRAFT, status: "rejected" }));
  });

  await page.goto("/defects/1");
  await page.getByRole("button", { name: "Reject defect" }).click();

  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Reject defect" }).click();

  await expect(page.getByText("Defect rejected")).toBeVisible();
  await expect(page.getByText("Rejected — not filed to Jira.")).toBeVisible();
});

test("unknown defect renders the 404 message + back link", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/defects/999", (route) =>
    route.fulfill(fulfillError(404, "No defect found for this id")),
  );

  await page.goto("/defects/999");

  await expect(page.getByText("No defect found for this id.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to defects" })).toBeVisible();
});
