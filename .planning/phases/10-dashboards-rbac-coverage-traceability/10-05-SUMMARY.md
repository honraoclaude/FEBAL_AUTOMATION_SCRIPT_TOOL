---
phase: 10-dashboards-rbac-coverage-traceability
plan: 05
subsystem: web-dashboards
tags: [frontend, nextjs, rbac, dashboards, recharts, zod, tanstack-query, role-gate, a11y, e2e]

# Dependency graph
requires:
  - phase: 10-dashboards-rbac-coverage-traceability
    plan: 01
    provides: /me returns role; the rbac.py role->permission matrix mirrored client-side
  - phase: 10-dashboards-rbac-coverage-traceability
    plan: 02
    provides: GET /api/dashboards/{executive,qa,developer} payloads (coverage, trends, KPIs, failed tests + run-relative artifact refs, root-cause + module breakdown)
  - phase: 07-execution-engine
    provides: artifactUrl/artifactBasename (the auth-gated run-relative artifact-URL builder), the vendored shadcn `table` + recharts Card pattern, verdict-badge
  - phase: 09-defect-jira
    provides: ClassBadge (the Phase-9 defect-class word+icon mapping reused on the Developer dashboard)
provides:
  - lib/rbac.ts — the static ROLE_NAV map + canSee(role, href) (the UX mirror of the API matrix)
  - components/dashboards/role-badge.tsx — the role badge (word + icon + --status-* hue, never color alone)
  - role-filtered sidebar nav (Dashboards/Coverage/Traceability/Search/Users appended after Defects, off /me)
  - lib/api/dashboards.ts — zod clients for the three dashboard endpoints
  - components/dashboards/{kpi-tile,dashboard-charts,dashboard-states}.tsx — the shared KPI meter / trend charts / honest-state blocks
  - the three role-scoped dashboard pages (executive/qa/developer) to the 10-UI-SPEC
affects: [10-06-coverage-traceability-search-ui, dashboards, rbac, web]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "client role mirror: lib/rbac.ts ROLE_NAV + canSee() mirrors the API rbac.py matrix; the appended nav items render off /me, the pre-existing items keep their always-visible gating"
    - "no-access as defense-in-depth: a page maps an ApiError 403 to <NoAccess>, never the data (the API require_role is the boundary)"
    - "KPI meter = styled-native role=progressbar over --status-* tokens (gap=muted remainder vs failure=red remainder), band from the SERVER percent — not a Recharts gauge, not a client cutoff"
    - "dashboard trend cards reuse the Phase-7 recharts Card pattern (h-64 ResponsiveContainer, mono axis numerals, isAnimationActive=false, role=img + sr-only summary) with ZERO new dep"
    - "tables on the vendored shadcn `table` block (NOT @tanstack/react-table, which is not installed)"

key-files:
  created:
    - apps/web/lib/rbac.ts
    - apps/web/components/dashboards/role-badge.tsx
    - apps/web/lib/api/dashboards.ts
    - apps/web/components/dashboards/kpi-tile.tsx
    - apps/web/components/dashboards/dashboard-charts.tsx
    - apps/web/components/dashboards/dashboard-states.tsx
    - apps/web/app/(dashboard)/dashboards/executive/page.tsx
    - apps/web/app/(dashboard)/dashboards/qa/page.tsx
    - apps/web/app/(dashboard)/dashboards/developer/page.tsx
    - apps/web/tests/e2e/dashboards.spec.ts
  modified:
    - apps/web/components/app-sidebar.tsx

key-decisions:
  - "ROLE_NAV mirrors the API matrix EXACTLY (Admin=all; QA Lead=all dashboards+coverage+traceability+search; QA Engineer=QA+search; Developer=Developer+coverage+traceability+search; Users=admin-only); an unknown role => empty set (deny-by-default, matching the backend can())"
  - "the flat-list nav contract is preserved: the single 'Dashboards' item resolves to the highest-privilege dashboard the role may open (Executive > QA > Developer); a role with no dashboard hides the item"
  - "while /me is pending (role undefined) canSee() returns false for every gated href, so NO gated nav renders yet (the 10-UI-SPEC pending-state rule)"
  - "the two coverage metrics are SEPARATE executive tiles (Covered flows + Discovered flows), each with its own definition caption — never merged (Pitfall 5 / T-10-26)"
  - "QA artifact links are auth-gated /api/executions/{run}/artifacts/{flow}/{kind} URLs built via the Phase-7 artifactUrl from the run-relative basename — NEVER the payload's raw stored path (T-10-24)"
  - "CHECKER LOW-3: render ONLY the 3 real TestArtifact kinds (screenshot|trace|video) + the honest 'console + network captured in the trace' note; absent video => 'Video captured on failure only.' (NOT 5 link slots)"

patterns-established:
  - "lib/rbac.ts canSee() — the one client source of truth the sidebar AND each page's no-access mirror reason from"
  - "MeterKpiTile — the accessible server-driven KPI meter (the Phase-10 coverage/pass-rate precedent)"

requirements-completed: [PLAT-04, DASH-01, DASH-02, DASH-03]

# Metrics
duration: ~13min
completed: 2026-06-29
---

# Phase 10 Plan 05: Role-Gated Nav + the Three Dashboards UI Summary

**The frontend half of PLAT-04 (role-filtered sidebar nav + the no-access boundary mirror, read off the `/me` role through `lib/rbac.ts`) plus the three role-scoped dashboards (Executive/QA/Developer) built to the approved 10-UI-SPEC over the Plan-02 payloads — every value server-authoritative, the two coverage metrics kept separate, QA artifact links auth-gated, with ZERO new frontend dependencies and a 13-test mocked-API e2e green.**

## Performance

- **Duration:** ~13 min
- **Completed:** 2026-06-29
- **Tasks:** 3 (auto)
- **Files modified:** 11 (10 created, 1 modified)

## Accomplishments

- **Role-gated sidebar nav (PLAT-04 UX mirror):** `lib/rbac.ts` ships the static `ROLE_NAV` map + `canSee(role, href)` mirroring the API `rbac.py` matrix exactly. `app-sidebar.tsx` extends `Me` with `role`, APPENDS the Phase-10 items (Dashboards/Coverage/Traceability/Search/Users) after "Defects", filters them off `/me`, and renders the role badge in the footer. The single "Dashboards" item resolves to the highest-privilege dashboard the role may open; a pending `/me` renders no gated nav yet.
- **Role badge** (`role-badge.tsx`): the four roles as WORD + lucide icon + `--status-*` hue (Admin red ShieldCheck / QA Lead green ClipboardCheck / QA Engineer amber FlaskConical / Developer muted Code2) — never color alone (WCAG 1.4.1).
- **Dashboards zod client** (`lib/api/dashboards.ts`): zod-at-the-boundary schemas + fetchers for the three endpoints (1:1 with the Plan-02 Pydantic shapes); `asArtifactKind` narrows a payload kind to the 3 real `TestArtifact` kinds.
- **Shared components:** `kpi-tile.tsx` (`KpiTile` + `MeterKpiTile` — the accessible `role="progressbar"` meter with server-driven bands: gap=muted remainder vs failure=red remainder); `dashboard-charts.tsx` (`PassRateTrendCard` + `CountTrendCard` reusing the Phase-7 recharts Card pattern, no new dep); `dashboard-states.tsx` (the honest error/empty/no-access/skeleton blocks).
- **Executive dashboard** (DASH-01): the KPI strip (Coverage meter + honest definition, Pass-rate meter, Open defects) + the two coverage metrics as SEPARATE tiles (Covered flows + Discovered flows, each its own definition) + the Pass-rate / Defects-filed trend cards; graph-down (503), error, empty, and no-access (403) states.
- **QA dashboard** (DASH-02): the execution-history table (vendored `table`, row → `/executions/{run_id}`, word+dot status) + the failed-tests panel (verdict + attempts chip + View run) + the Screenshots & videos auth-gated links (3 real kinds + the trace note; absent video → honest caption).
- **Developer dashboard** (DASH-03): root-cause groupings (mono `fp-{hash}` + the reused Phase-9 `ClassBadge` + occurrences + a representative `/defects/{id}` link) + the Errors-over-time chart + the module breakdown (proportional `--status-fail` bars).
- **Mocked-API e2e** (`dashboards.spec.ts`): 13 tests mocking `/api/auth/me` (each role) + the three dashboard payloads — asserting the role-gated nav per role, each dashboard's populated/empty/error states, the no-access state for a forbidden role hitting a URL directly, the auth-gated artifact hrefs (no raw paths), and the two-coverage-metric separation.

## Task Commits

1. **Task 1: role-filtered sidebar nav + role badge + lib/rbac.ts map** — `d066625` (feat)
2. **Task 2: dashboards api client (zod) + KPI tile + trend charts** — `97e2a6c` (feat)
3. **Task 3: the three dashboard pages + mocked-API e2e** — `3be8c0c` (feat)

## Files Created/Modified

- `apps/web/lib/rbac.ts` — `ROLE_NAV` map + `canSee()` (the UX mirror of the API matrix).
- `apps/web/components/dashboards/role-badge.tsx` — the role badge (word+icon+hue).
- `apps/web/components/app-sidebar.tsx` — `Me.role`; the appended role-filtered nav; the footer role badge.
- `apps/web/lib/api/dashboards.ts` — the three zod clients + `asArtifactKind`.
- `apps/web/components/dashboards/kpi-tile.tsx` — `KpiTile` + `MeterKpiTile` (accessible server-driven meter).
- `apps/web/components/dashboards/dashboard-charts.tsx` — `PassRateTrendCard` + `CountTrendCard` (recharts reuse).
- `apps/web/components/dashboards/dashboard-states.tsx` — error/empty/no-access/skeleton blocks.
- `apps/web/app/(dashboard)/dashboards/{executive,qa,developer}/page.tsx` — the three dashboards.
- `apps/web/tests/e2e/dashboards.spec.ts` — 13 mocked-API e2e tests.

## Decisions Made

- **The client role mirror is UX-only, never the boundary** (T-10-23): `canSee()` hides nav and a page maps an `ApiError` 403 to `<NoAccess>` (the data never renders), but the API `require_role` is the real gate. The e2e proves a developer who types the executive URL gets the no-access state, not the data.
- **Two coverage metrics kept separate** (Pitfall 5 / T-10-26): the executive dashboard renders "Covered flows" (lifecycle) and "Discovered flows" (exploration completeness) as distinct tiles, each with its own definition caption — asserted in the e2e.
- **Auth-gated artifact links via the Phase-7 builder** (T-10-24): the QA links use `artifactUrl(run, flow, kind)` from the run-relative basename; the payload's raw stored `path` is never rendered as an href. The e2e asserts the exact `/api/executions/.../artifacts/...` URLs.
- **Only the 3 real artifact kinds** (CHECKER LOW-3): the QA artifact panel renders screenshot/trace/video + the "console + network captured in the trace" note — no console_log/network_log link slots.
- **Chart-title `getByText` needs `{ exact: true }`:** each trend card's sr-only accessible summary begins with the title text, so an inexact `getByText(title)` is a strict-mode violation. Fixed in the spec (see Deviations).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] e2e strict-mode violation on chart titles**
- **Found during:** Task 3 (running the per-task `npx playwright test` verify).
- **Issue:** `page.getByText("Defects filed over time")` / `"Errors over time"` matched BOTH the card title `<p>` AND the chart's visually-hidden accessible summary `<span class="sr-only">` (which intentionally begins with the title text per the WCAG chart-summary rule), causing a Playwright strict-mode violation. This was a bug in the new test assertions, not in the page.
- **Fix:** Added `{ exact: true }` to the three chart-title `getByText` assertions in `dashboards.spec.ts`.
- **Files modified:** `apps/web/tests/e2e/dashboards.spec.ts`.
- **Commit:** `3be8c0c` (folded into the Task 3 commit, fixed before the task was committed).

No Rule 2/3/4 deviations were required. The plan's `<interfaces>` (the Plan-02 payloads, `require_role`/`/me` role, `artifactUrl`/`artifactBasename`, the recharts/table/verdict-badge precedents, the Phase-9 `ClassBadge`) all matched the codebase verbatim.

## Issues Encountered

- **Parallel compile-timing flake (resolved):** on the FIRST full-suite run, three nav/executive tests reported transient failures alongside the two genuine chart-title bugs. All passed in isolation; `next dev` compiles a route on its first request, so under `fullyParallel` load a cold-route first hit could exceed the 5s assertion timeout. Once the two genuine title bugs were fixed (so those tests no longer slowed the parallel pool with trace capture), the full suite ran **13 passed** deterministically. No source change was needed; the flake was first-compile latency, not a code defect.

## Known Stubs

None — every page is wired to the real Plan-02 endpoints through the zod client. No placeholder values, no TODO/FIXME, no empty data sources. The Coverage/Traceability/Search/Users PAGES those nav items point at are Plan 06 (this plan owns only the NAV for them, as scoped by the plan's `<interfaces>`); the nav items are intentional and documented, not stubs.

## Threat Flags

None — the plan's `<threat_model>` (T-10-23..26) is fully covered: the nav gating is UX-only with the API 403 as the boundary and a `<NoAccess>` mirror (T-10-23, e2e-asserted); artifact links are auth-gated URLs from run-relative basenames, never an fs path (T-10-24, e2e-asserted on the exact hrefs); every KPI/chart/row renders strictly from the server payload with skeletons on load — never a fabricated number (T-10-25); the two coverage numbers are separate tiles (T-10-26, e2e-asserted). No new security surface beyond the register.

## Verification

- `npx tsc --noEmit` — clean.
- `npx eslint "app/(dashboard)/dashboards" components/dashboards lib/rbac.ts lib/api/dashboards.ts components/app-sidebar.tsx tests/e2e/dashboards.spec.ts` — clean.
- `npx playwright test tests/e2e/dashboards.spec.ts` — **13 passed**.
- `git diff --quiet apps/web/package.json` (and `package-lock.json`) — CLEAN (ZERO new frontend deps; recharts already present).
- Grep gate: `rg "react-table" app/(dashboard)/dashboards components/dashboards lib/api/dashboards.ts` → NONE (tables on the vendored shadcn `table`).

## Next Phase Readiness

- The role-gated nav already renders the Coverage/Traceability/Search/Users items off `/me`; Plan 06 builds those PAGES (`/coverage`, `/traceability`, `/search`, `/admin/users`) over the Plan-03/04 endpoints, reusing `lib/rbac.ts` `canSee()` for the no-access mirror and the shared `dashboard-states.tsx` blocks.
- The `MeterKpiTile`, the recharts trend cards, and the artifact-link contract are reusable for the coverage panel + any future metric surface.

## Self-Check: PASSED

All 10 created files exist on disk; the modified `app-sidebar.tsx` is committed; all 3 task commits (`d066625`, `97e2a6c`, `3be8c0c`) are in the git log.

---
*Phase: 10-dashboards-rbac-coverage-traceability*
*Completed: 2026-06-29*
