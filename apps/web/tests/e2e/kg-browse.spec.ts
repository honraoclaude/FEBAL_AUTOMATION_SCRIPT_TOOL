import { expect, test } from "@playwright/test";

/**
 * Knowledge-graph browse e2e (05-03 Task 2, KG-02 / D-05) — MOCKED API, no backend, no keys.
 *
 * Every /api/* call is route-intercepted: /api/auth/me (dashboard shell), /api/coverage,
 * /api/pages, /api/flows, /api/elements, /api/graph. The test asserts the UI-SPEC states:
 * the Pages/Flows(risk badge)/Element-repository tables render, the coverage stat shows the
 * mocked % AND the "Not yet measured" honest state, a drill-in link navigates, and the
 * empty + error states render. No backend or provider key is required.
 */

type Json = Record<string, unknown>;

function fulfillJson(body: Json) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  };
}

const COVERAGE_MEASURED = {
  screens_total: 7,
  screens_covered: 6,
  flows_total: 2,
  flows_covered: 2,
  coverage_percent: 85.7,
  measured: true,
};

const COVERAGE_UNMEASURED = {
  screens_total: 0,
  screens_covered: 0,
  flows_total: 0,
  flows_covered: 0,
  coverage_percent: 0.0,
  measured: false,
};

const PAGES = {
  pages: [
    {
      fingerprint: "fp-login-abcdef12",
      url: "http://saucedemo:80/",
      title: "Login",
      first_seen: "2026-06-19T10:00:00Z",
      last_verified: "2026-06-19T10:00:00Z",
      element_count: 3,
    },
    {
      fingerprint: "fp-inventory-deadbeef",
      url: "http://saucedemo:80/inventory.html",
      title: "Inventory",
      first_seen: "2026-06-19T10:01:00Z",
      last_verified: "2026-06-19T10:01:00Z",
      element_count: 12,
    },
  ],
};

const FLOWS = {
  flows: [
    {
      flow_id: "flow-0",
      name: "Checkout",
      category: "Checkout",
      risk_score: 78,
      risk_tier: "high",
      step_count: 5,
      bounded: false,
      signals: { has_destructive: false, state_change_edges: 3, path_length: 5 },
    },
    {
      flow_id: "flow-1",
      name: "Login",
      category: "Authentication",
      risk_score: 18,
      risk_tier: "low",
      step_count: 2,
      bounded: false,
      signals: { has_destructive: false, state_change_edges: 0, path_length: 2 },
    },
  ],
};

const ELEMENTS = {
  elements: [
    {
      key: "fp-inventory-deadbeef#button:Add to cart",
      role: "button",
      label: "Add to cart",
      page_fingerprint: "fp-inventory-deadbeef",
      page_url: "http://saucedemo:80/inventory.html",
      locator_chain: [
        { strategy: "data-testid", value: "add-to-cart", name: null },
        { strategy: "role", value: "button", name: "Add to cart" },
      ],
      locator_history: [
        {
          step: 1,
          chain: [{ strategy: "data-testid", value: "add-to-cart", name: null }],
        },
      ],
      first_seen: "2026-06-19T10:01:00Z",
      last_verified: "2026-06-19T10:01:00Z",
    },
  ],
};

const GRAPH = { counts: { Page: 2, Element: 15 }, discovered: true };

async function authCookie(context: import("@playwright/test").BrowserContext) {
  await context.addCookies([
    { name: "access_token", value: "e2e-mock-token", domain: "localhost", path: "/" },
  ]);
}

async function mockShell(page: import("@playwright/test").Page) {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill(
      fulfillJson({ id: 1, email: "admin@example.test" }),
    ),
  );
}

test("Pages view renders the coverage stat + pages table and drills in", async ({
  page,
  context,
}) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/coverage", (route) => route.fulfill(fulfillJson(COVERAGE_MEASURED)));
  await page.route("**/api/pages", (route) => route.fulfill(fulfillJson(PAGES)));
  await page.route("**/api/pages/**", (route) =>
    route.fulfill(
      fulfillJson({
        ...PAGES.pages[1],
        elements: [
          { key: "fp-inventory-deadbeef#button:Add to cart", role: "button", label: "Add to cart" },
        ],
        forms: [],
        navigates_to: [],
      }),
    ),
  );

  await page.goto("/graph");

  // Coverage stat shows the mocked %.
  await expect(page.getByText("85.7%")).toBeVisible();
  // Pages table rows render.
  await expect(page.getByRole("link", { name: "Inventory" })).toBeVisible();
  await expect(page.getByRole("link", { name: "12 elements" })).toBeVisible();

  // Drill-in: clicking the page title navigates to page detail.
  await Promise.all([
    page.waitForURL(/\/graph\/pages\//),
    page.getByRole("link", { name: "Inventory" }).click(),
  ]);
  await expect(page.getByRole("heading", { name: "Elements" })).toBeVisible();
});

test("Pages view renders 'Not yet measured' coverage when measured=false", async ({
  page,
  context,
}) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/coverage", (route) =>
    route.fulfill(fulfillJson(COVERAGE_UNMEASURED)),
  );
  await page.route("**/api/pages", (route) => route.fulfill(fulfillJson(PAGES)));

  await page.goto("/graph");

  await expect(page.getByText("Not yet measured")).toBeVisible();
});

test("Pages view renders the no-graph empty state", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/coverage", (route) =>
    route.fulfill(fulfillJson(COVERAGE_UNMEASURED)),
  );
  await page.route("**/api/pages", (route) => route.fulfill(fulfillJson({ pages: [] })));

  await page.goto("/graph");

  await expect(page.getByText("No knowledge graph yet")).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to targets" })).toBeVisible();
});

test("Pages view renders the inline error + Retry state", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/coverage", (route) =>
    route.fulfill(fulfillJson(COVERAGE_UNMEASURED)),
  );
  await page.route("**/api/pages", (route) =>
    route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "boom" }) }),
  );

  await page.goto("/graph");

  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});

test("Flows view renders the risk badge with score + tier word", async ({ page, context }) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/flows", (route) => route.fulfill(fulfillJson(FLOWS)));
  await page.route("**/api/graph", (route) => route.fulfill(fulfillJson(GRAPH)));

  await page.goto("/graph/flows");

  // Risk badge: the tier WORD + the mono score are both present (never color alone).
  await expect(page.getByRole("link", { name: "Checkout" })).toBeVisible();
  await expect(page.getByText("High", { exact: true })).toBeVisible();
  await expect(page.getByText("78", { exact: true })).toBeVisible();
  await expect(page.getByText("Low", { exact: true })).toBeVisible();
});

test("Element repository view renders the locator and host page", async ({
  page,
  context,
}) => {
  await authCookie(context);
  await mockShell(page);
  await page.route("**/api/elements", (route) => route.fulfill(fulfillJson(ELEMENTS)));
  await page.route("**/api/graph", (route) => route.fulfill(fulfillJson(GRAPH)));

  await page.goto("/graph/elements");

  await expect(page.getByRole("link", { name: "Add to cart" })).toBeVisible();
  await expect(page.getByText("data-testid=add-to-cart")).toBeVisible();
});
