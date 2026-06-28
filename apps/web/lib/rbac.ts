/**
 * Frontend role -> permitted-nav map (PLAT-04 UX mirror of the API rbac.py matrix).
 *
 * This is the UX-ONLY mirror of `apps/api/app/services/rbac.py` (ROLE_PERMISSIONS + the
 * endpoint->role matrix). It decides which NAV items + dashboards a role may SEE — it is NEVER the
 * security boundary. Every gated route ALSO hits a `require_role`-gated API; a directly-typed
 * forbidden URL returns 403 and the page renders the no-access state, never the data
 * (10-UI-SPEC "Cross-cutting: the role mirror is UX, never the boundary").
 *
 * The hrefs below MUST stay in lock-step with the API capability map:
 *   - Admin       = ALL nav
 *   - QA Lead     = all dashboards + coverage + traceability + search
 *   - QA Engineer = the QA dashboard + search
 *   - Developer   = the Developer dashboard + coverage + traceability + search
 *   - Users (/admin/users) = Admin only
 *
 * The EXISTING pre-Phase-10 items (Targets, Explorations, Knowledge graph, Scenarios, Executions,
 * Defects) keep their existing always-visible gating — only the APPENDED Phase-10 items are filtered
 * by this map. An href absent from a role's set is hidden for that role.
 */

/** The Phase-10 appended nav hrefs this map gates (the pre-existing items are not listed here). */
export const NAV_HREFS = {
  dashboardExecutive: "/dashboards/executive",
  dashboardQa: "/dashboards/qa",
  dashboardDeveloper: "/dashboards/developer",
  coverage: "/coverage",
  traceability: "/traceability",
  search: "/search",
  users: "/admin/users",
} as const;

/**
 * The static role -> permitted Phase-10 nav hrefs (the UX mirror of ROLE_PERMISSIONS). An unknown
 * role gets the empty set (deny-by-default), matching the backend `can()` helper.
 */
export const ROLE_NAV: Record<string, ReadonlySet<string>> = {
  admin: new Set<string>([
    NAV_HREFS.dashboardExecutive,
    NAV_HREFS.dashboardQa,
    NAV_HREFS.dashboardDeveloper,
    NAV_HREFS.coverage,
    NAV_HREFS.traceability,
    NAV_HREFS.search,
    NAV_HREFS.users,
  ]),
  qa_lead: new Set<string>([
    NAV_HREFS.dashboardExecutive,
    NAV_HREFS.dashboardQa,
    NAV_HREFS.dashboardDeveloper,
    NAV_HREFS.coverage,
    NAV_HREFS.traceability,
    NAV_HREFS.search,
  ]),
  qa_engineer: new Set<string>([NAV_HREFS.dashboardQa, NAV_HREFS.search]),
  developer: new Set<string>([
    NAV_HREFS.dashboardDeveloper,
    NAV_HREFS.coverage,
    NAV_HREFS.traceability,
    NAV_HREFS.search,
  ]),
};

/**
 * True iff `role` may SEE the nav item / dashboard at `href` (deny-by-default for an unknown role).
 * The one helper the sidebar AND each dashboard page's no-access mirror reason from — one source of
 * truth for "may this role open this view." NEVER the security boundary (the API 403 is).
 */
export function canSee(role: string | undefined, href: string): boolean {
  if (!role) return false;
  return ROLE_NAV[role]?.has(href) ?? false;
}
