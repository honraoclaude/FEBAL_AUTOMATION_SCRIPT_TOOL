import { expect, test, type BrowserContext, type Page } from "@playwright/test";

/**
 * Admin Users e2e (10-06 Task 3, PLAT-04) — MOCKED API, no backend, no keys. Intercepts
 * /api/auth/me (admin / non-admin) + GET /api/users + POST /api/users/{id}/role.
 *
 * Asserts: the users list; a role change -> the confirm dialog -> POST -> success toast -> the badge
 * REPAINTS from the server response (no optimistic update); the self-row control DISABLED with the
 * guard caption (T-10-28); a change-failed inline error (the badge stays the OLD role); and a
 * non-admin /me -> the no-access state (T-10-27, the nav already hides Users).
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

async function stubMe(page: Page, id: number, role: string) {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill(fulfillJson({ id, email: "admin@example.test", role })),
  );
}

const USERS = [
  { id: 1, email: "admin@example.test", role: "admin" },
  { id: 2, email: "dev@example.test", role: "developer" },
];

test("admin: lists users + the self-row control is disabled with the guard caption", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, 1, "admin"); // I am user id 1 (the admin@... row).
  await page.route("**/api/users", (route) => route.fulfill(fulfillJson(USERS)));

  await page.goto("/admin/users");

  // Scope to the table — admin@example.test also appears in the sidebar footer (/me email).
  const table = page.getByRole("table");
  await expect(table.getByText("admin@example.test")).toBeVisible();
  await expect(table.getByText("dev@example.test")).toBeVisible();
  // The admin's own row shows the self-demote guard caption + no change control.
  await expect(page.getByTestId("self-row-guard")).toBeVisible();
  // The other user's row has a change control.
  await expect(
    page.getByRole("button", { name: "Change role for dev@example.test" }),
  ).toBeVisible();
});

test("admin: role change -> confirm dialog -> POST -> toast -> the badge repaints from the server", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, 1, "admin");

  // GET returns the dev as a developer; after the POST a re-GET returns them as qa_lead so the badge
  // REPAINTS from the server (no optimistic update).
  let changed = false;
  await page.route("**/api/users", (route) =>
    route.fulfill(
      fulfillJson(
        changed
          ? [USERS[0], { id: 2, email: "dev@example.test", role: "qa_lead" }]
          : USERS,
      ),
    ),
  );
  await page.route("**/api/users/2/role", (route) => {
    changed = true;
    route.fulfill(
      fulfillJson({ id: 2, email: "dev@example.test", role: "qa_lead" }),
    );
  });

  await page.goto("/admin/users");

  await page
    .getByRole("button", { name: "Change role for dev@example.test" })
    .click();
  await page.getByRole("menuitem", { name: "QA Lead" }).click();

  // The confirm dialog.
  await expect(page.getByText("Change dev@example.test's role?")).toBeVisible();
  await page.getByRole("button", { name: "Change role" }).click();

  // Success toast + the badge repaints from the server (qa_lead now present).
  await expect(page.getByText(/Role changed — dev@example.test is now QA Lead/)).toBeVisible();
  await expect(page.getByTestId("role-badge").filter({ hasText: "QA Lead" })).toBeVisible();
});

test("admin: a failed role change shows the inline error (the badge stays the OLD role)", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, 1, "admin");
  await page.route("**/api/users", (route) => route.fulfill(fulfillJson(USERS)));
  await page.route("**/api/users/2/role", (route) =>
    route.fulfill(fulfillError(500, "boom")),
  );

  await page.goto("/admin/users");
  await page
    .getByRole("button", { name: "Change role for dev@example.test" })
    .click();
  await page.getByRole("menuitem", { name: "QA Lead" }).click();
  await page.getByRole("button", { name: "Change role" }).click();

  await expect(page.getByTestId("change-failed")).toBeVisible();
  // The badge stays the OLD role (never a fabricated new role) — dev is still a Developer.
  await expect(page.getByTestId("role-badge").filter({ hasText: "Developer" })).toBeVisible();
});

test("admin: a non-admin who reaches the URL gets the no-access state (never the data)", async ({
  page,
  context,
}) => {
  await setAuth(context);
  await stubMe(page, 2, "developer");
  await page.route("**/api/users", (route) =>
    route.fulfill(fulfillError(403, "forbidden")),
  );

  await page.goto("/admin/users");
  await expect(page.getByTestId("no-access")).toBeVisible();
  // The user list never renders.
  await expect(page.getByText("dev@example.test")).toHaveCount(0);
});
