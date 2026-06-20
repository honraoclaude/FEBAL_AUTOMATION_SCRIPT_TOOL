import { expect, test } from "@playwright/test";

/**
 * Scenario review-queue e2e (06-02 Task 2, GEN-02 / 06-UI-SPEC) — MOCKED API, no backend, no keys.
 *
 * Every /api/* call is route-intercepted. Covers the UI-SPEC states: the list (status + risk
 * badges + filter), drill-in, the editable Gherkin textarea, a save that re-validates server-side
 * (422 → inline failure, text preserved, Approve disabled; 200 → fresh honest indicators, Approve
 * enabled), approve, reject-with-confirm, and the empty + error states. No backend/keys required.
 */

type Json = Record<string, unknown>;

function fulfillJson(body: Json | Json[]) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(body) };
}

const DRAFTS = [
  {
    id: 1,
    run_id: "run-1",
    flow_id: "flow-0",
    feature_name: "Add to cart",
    status: "draft",
    edited: false,
    stale: false,
    flow_risk_score: 78,
    flow_risk_tier: "high",
    updated_at: "2026-06-20T14:00:00Z",
  },
  {
    id: 2,
    run_id: "run-1",
    flow_id: "flow-1",
    feature_name: "Login",
    status: "draft",
    edited: false,
    stale: false,
    flow_risk_score: 18,
    flow_risk_tier: "low",
    updated_at: "2026-06-20T13:00:00Z",
  },
];

const GHERKIN =
  "Feature: Add to cart\n  Scenario: Add an item\n    Given the inventory page\n    Then the inventory page is shown\n";

const DETAIL_RESOLVED = {
  ...DRAFTS[0],
  gherkin_text: GHERKIN,
  then_refs: [
    { then_text: "the inventory page is shown", kind: "page", ref: { page_fingerprint: "fp-inv" } },
  ],
  then_results: [
    { then_text: "the inventory page is shown", resolved: true, kg_ref: "page: fp-inv", reason: null },
  ],
};

const DETAIL_VACUOUS = {
  ...DRAFTS[0],
  gherkin_text: GHERKIN,
  then_refs: [{ then_text: "a ghost page", kind: "page", ref: { page_fingerprint: "fp-nope" } }],
  then_results: [
    { then_text: "a ghost page", resolved: false, kg_ref: null, reason: "ref not found in graph" },
  ],
};

async function authCookie(context: import("@playwright/test").BrowserContext) {
  await context.addCookies([
    { name: "access_token", value: "e2e-mock-token", domain: "localhost", path: "/" },
  ]);
}

async function mockShell(page: import("@playwright/test").Page) {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill(fulfillJson({ id: 1, email: "admin@example.test" })),
  );
}

test("list renders status + risk badges and the drill-in link", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/scenarios?status=draft", (route) => route.fulfill(fulfillJson(DRAFTS)));

  await page.goto("/scenarios");

  await expect(page.getByRole("heading", { name: "Scenario review" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Add to cart" })).toBeVisible();
  await expect(page.getByText("High", { exact: true })).toBeVisible();
  await expect(page.getByText("78", { exact: true })).toBeVisible();
  await expect(page.getByText("Draft", { exact: true }).first()).toBeVisible();
});

test("filter switches to Approved and deep-links the status param", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/scenarios?status=draft", (route) => route.fulfill(fulfillJson(DRAFTS)));
  await page.route("**/api/scenarios?status=approved", (route) => route.fulfill(fulfillJson([])));

  await page.goto("/scenarios");
  await page.getByRole("button", { name: "Approved" }).click();

  await expect(page).toHaveURL(/status=approved/);
  await expect(page.getByText("No approved scenarios")).toBeVisible();
  await expect(page.getByRole("button", { name: "View drafts" })).toBeVisible();
});

test("list renders the no-scenarios empty state", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/scenarios?status=draft", (route) => route.fulfill(fulfillJson([])));

  await page.goto("/scenarios");

  await expect(page.getByText("No scenarios yet")).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to knowledge graph" })).toBeVisible();
});

test("list renders the inline error + Retry state", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/scenarios?status=draft", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "boom" }) }),
  );

  await page.goto("/scenarios");

  await expect(page.getByText(/Couldn't load scenarios|Couldn't load the knowledge/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});

test("detail drill-in + edit save 422 keeps text inline and Approve disabled", async ({
  page,
  context,
}) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/scenarios?status=draft", (route) => route.fulfill(fulfillJson(DRAFTS)));
  // Start with a vacuous detail so Approve is disabled from the outset.
  await page.route("**/api/scenarios/1", (route) => route.fulfill(fulfillJson(DETAIL_VACUOUS)));
  await page.route("**/api/scenarios/1/edit", (route) =>
    route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({ detail: "no-vacuous gate: Then steps with no graph-backed outcome" }),
    }),
  );

  await page.goto("/scenarios");
  await Promise.all([
    page.waitForURL(/\/scenarios\/1$/),
    page.getByRole("link", { name: "Add to cart" }).click(),
  ]);

  // The editable native textarea is present and holds the Gherkin.
  const editor = page.getByLabel("Gherkin");
  await expect(editor).toBeVisible();
  await editor.fill(GHERKIN + "    Then nothing\n");

  await page.getByRole("button", { name: "Save edits" }).click();

  // 422 → inline failure rendered, text preserved, Approve still disabled.
  await expect(page.getByText("This Gherkin doesn't parse.")).toBeVisible();
  await expect(page.getByText(/no-vacuous gate/)).toBeVisible();
  await expect(editor).toHaveValue(GHERKIN + "    Then nothing\n");
  await expect(page.getByRole("button", { name: "Approve scenario" })).toBeDisabled();
});

test("edit save 200 repaints honest indicators and enables Approve", async ({
  page,
  context,
}) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/scenarios?status=draft", (route) => route.fulfill(fulfillJson(DRAFTS)));

  const EDITED_TEXT = GHERKIN + "# tweak\n";
  // Detail starts vacuous (Approve disabled); after a successful edit it returns resolved AND
  // echoes the edited Gherkin text so the editor un-dirties (mirrors the server persisting it).
  let edited = false;
  await page.route("**/api/scenarios/1", (route) =>
    route.fulfill(
      fulfillJson(
        edited
          ? { ...DETAIL_RESOLVED, edited: true, gherkin_text: EDITED_TEXT }
          : DETAIL_VACUOUS,
      ),
    ),
  );
  await page.route("**/api/scenarios/1/edit", (route) => {
    edited = true;
    return route.fulfill(
      fulfillJson({ ...DETAIL_RESOLVED, edited: true, gherkin_text: EDITED_TEXT }),
    );
  });

  await page.goto("/scenarios/1");

  await expect(page.getByText("Vacuous")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve scenario" })).toBeDisabled();

  const editor = page.getByLabel("Gherkin");
  await editor.fill(EDITED_TEXT);
  await page.getByRole("button", { name: "Save edits" }).click();

  // Fresh honest indicators (Resolved) + Approve enabled.
  await expect(page.getByText("Resolved")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve scenario" })).toBeEnabled();
});

test("approve navigates back to the queue", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/scenarios?status=draft", (route) => route.fulfill(fulfillJson(DRAFTS)));
  await page.route("**/api/scenarios/1", (route) => route.fulfill(fulfillJson(DETAIL_RESOLVED)));
  await page.route("**/api/scenarios/1/approve", (route) =>
    route.fulfill(fulfillJson({ ...DETAIL_RESOLVED, status: "approved" })),
  );

  await page.goto("/scenarios/1");
  await expect(page.getByRole("button", { name: "Approve scenario" })).toBeEnabled();
  await page.getByRole("button", { name: "Approve scenario" }).click();

  await expect(page).toHaveURL(/\/scenarios(\?.*)?$/);
});

test("reject requires confirmation then navigates back", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/scenarios?status=draft", (route) => route.fulfill(fulfillJson(DRAFTS)));
  await page.route("**/api/scenarios/1", (route) => route.fulfill(fulfillJson(DETAIL_RESOLVED)));
  await page.route("**/api/scenarios/1/reject", (route) =>
    route.fulfill(fulfillJson({ ...DETAIL_RESOLVED, status: "rejected" })),
  );

  await page.goto("/scenarios/1");
  await page.getByRole("button", { name: "Reject scenario" }).click();

  // The confirm dialog appears; confirming rejects + navigates back.
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Reject scenario" }).click();

  await expect(page).toHaveURL(/\/scenarios(\?.*)?$/);
});
