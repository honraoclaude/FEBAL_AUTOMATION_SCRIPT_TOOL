---
phase: 10-dashboards-rbac-coverage-traceability
plan: 06
subsystem: web-coverage-traceability-search-admin
tags: [frontend, nextjs, coverage, traceability, search, rbac, admin, zod, tanstack-query, a11y, e2e]

# Dependency graph
requires:
  - phase: 10-dashboards-rbac-coverage-traceability
    plan: 01
    provides: GET /api/users + POST /api/users/{id}/role (admin-only, self-demote 400); /me returns role
  - phase: 10-dashboards-rbac-coverage-traceability
    plan: 02
    provides: GET /api/coverage/flows (DASH-04 lifecycle coverage + honest definition + per-flow drill-down)
  - phase: 10-dashboards-rbac-coverage-traceability
    plan: 03
    provides: GET /api/traceability (DASH-05 chain shape, honest gaps, graph-down flow=null+note, unknown id->200 empty)
  - phase: 10-dashboards-rbac-coverage-traceability
    plan: 04
    provides: GET /api/search (DASH-06 typed hits + highlight; ES-down -> honest 503, never a fake empty list)
  - phase: 10-dashboards-rbac-coverage-traceability
    plan: 05
    provides: lib/rbac.ts canSee(); the role-gated sidebar nav for these pages; MeterKpiTile; role-badge; dashboard-states (Error/Empty/NoAccess/Skeleton)
  - phase: 05-knowledge-graph
    provides: GET /api/coverage (Phase-5 ground-truth — screens_covered/total + measured flag), shown SEPARATELY
provides:
  - lib/api/coverage.ts — zod clients for /api/coverage/flows (lifecycle) + /api/coverage (ground-truth)
  - lib/api/traceability.ts — zod client + EntryType->query-param map + flowSegments() normalizer
  - lib/api/search.ts — zod client (503 distinct from empty 200) + firstHighlight()/hitTitle() helpers
  - lib/api/users.ts — zod client (getUsers + setRole)
  - components/dashboards/chain-view.tsx — the ordered <ol> chain renderer with honest "No {segment} linked." gaps
  - components/dashboards/search-results.tsx — typed result cards + SAFE-parsed server highlight (no HTML injection)
  - the four pages: /coverage (DASH-04), /traceability (DASH-05), /search (DASH-06), /admin/users (PLAT-04)
affects: [dashboards, rbac, coverage, traceability, search, web]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "two coverage metrics kept SEPARATE on /coverage: lifecycle (Flow coverage) card + Exploration completeness card, each its own definition (Pitfall 5 / T-10-31)"
    - "the chain rendered as a semantic <ol> (a11y order); a missing segment is a muted dashed 'No {segment} linked.' node, never a fabricated node or dead link"
    - "URL (?type=&id= / ?q=&index=) is the SINGLE source of truth for the submitted query — no setState-in-effect (the react-hooks/set-state-in-effect lint rule); the form state is only the typing buffer"
    - "ES highlight rendered SAFELY by parsing on the literal <em>…</em> the server emits into text + <em> spans — never dangerouslySetInnerHTML (T-10-29 XSS)"
    - "503 surfaced distinctly from an empty-results 200 (ApiError.status) so search/coverage render the honest unavailable state, never 'no results' / a fabricated zero"
    - "admin role change: useMutation + ['users']+['auth','me'] invalidation, NO optimistic update — the badge repaints from the server response; success-only sonner toast; inline change-failed error keeps the OLD badge"
    - "self-demote guard is a UI MIRROR: the self-row control is disabled (myId from /me); the server 400 is the real boundary (T-10-28)"
    - "tables on the vendored shadcn `table` block (NOT @tanstack/react-table)"

key-files:
  created:
    - apps/web/lib/api/coverage.ts
    - apps/web/lib/api/traceability.ts
    - apps/web/lib/api/search.ts
    - apps/web/lib/api/users.ts
    - apps/web/components/dashboards/chain-view.tsx
    - apps/web/components/dashboards/search-results.tsx
    - apps/web/app/(dashboard)/coverage/page.tsx
    - apps/web/app/(dashboard)/traceability/page.tsx
    - apps/web/app/(dashboard)/search/page.tsx
    - apps/web/app/(dashboard)/admin/users/page.tsx
    - apps/web/tests/e2e/coverage-traceability-search.spec.ts
    - apps/web/tests/e2e/admin-users.spec.ts
  modified: []

key-decisions:
  - "The Phase-5 ground-truth coverage shape is screens_total/screens_covered/flows_total/flows_covered/coverage_percent/measured (read off routers/kg.py, NOT a discovered/total pair) — the schema mirrors the real backend; measured=false renders the honest 'Not yet measured' state, never a fabricated 0%"
  - "The traceability picker label 'Execution' maps to the EntryType 'run' -> the run_id query param (the UI label differs from the API param name by design)"
  - "An unknown traceability id is the 'no chain found' state computed client-side (no flow AND every relational segment empty) — the backend returns 200 with an honest empty chain, never a 404"
  - "Search 503 vs empty-200: the page branches on ApiError.status === 503 for the honest 'search unavailable' state, DISTINCT from a count:0/hits:[] 'No results' state (T-10-30)"
  - "URL-as-source-of-truth for the submitted query (no useEffect sync) — this also satisfies the react-hooks/set-state-in-effect lint rule the first traceability draft tripped"

patterns-established:
  - "ChainView — the ordered honest-gap chain renderer (reusable for any artifact-lineage view)"
  - "HighlightedFragment — the safe server-highlight parser (text + <em> spans, no HTML injection)"

requirements-completed: [PLAT-04, DASH-04, DASH-05, DASH-06]

# Metrics
duration: ~30min
completed: 2026-06-29
---

# Phase 10 Plan 06: Coverage + Traceability + Search + Admin UI Summary

**The final Phase-10 UI slice — the coverage panel (DASH-04: lifecycle %+honest definition+per-flow drill-down with the Phase-5 ground-truth shown as a SEPARATE card), the traceability viewer (DASH-05: a deep-linkable ?type=&id= picker feeding an ordered flow↔scenario↔script↔execution↔defect chain with honest "No {segment} linked." gaps), the search UI (DASH-06: typed highlighted hits with the ES highlight rendered as SAFE emphasis + an honest "search unavailable" 503 distinct from no-results), and the admin role-assignment screen (PLAT-04: list+assign with the self-demote guard, a confirm dialog, no optimistic update, and a success-only toast) — built EXACTLY to the approved 10-UI-SPEC over the Plan-01..04 endpoints, with ZERO new frontend dependencies and a 17-test mocked-API e2e green.**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-06-29
- **Tasks:** 3 (auto)
- **Files modified:** 12 (12 created, 0 modified)

## Accomplishments

- **Coverage panel** (DASH-04, `/coverage`): the lifecycle "Flow coverage" card — the `MeterKpiTile` % + the honest `definition` DISPLAYED inline (D-02) + the covered/total mono counts + the per-flow drill-down table (Flow · Approved scenario · Passing execution · Covered — a green check / muted dash per condition + the resolved "Covered"/"Not covered" word, flow name → `/graph/flows/{id}`) + the `measured_against` flow_id honesty caption; the SEPARATE "Exploration completeness" ground-truth card with its OWN definition (never merged — Pitfall 5 / T-10-31), reading the real Phase-5 `screens_covered/screens_total/measured` shape and rendering the honest "Not yet measured" state when `measured:false`. States: loading / empty (→ targets) / populated / graph-down (honest 503) / error.
- **Traceability viewer** (DASH-05, `/traceability`): the entry picker (a Flow · Scenario · Execution · Defect segment + a mono id input + "Show chain", deep-linkable `?type=&id=`) feeding `chain-view.tsx` — the ordered `<ol>` Flow → Scenario → Script → Execution → Defect, each present node a tile with its Label + mono id + an accent drill-in link; a missing segment a muted dashed "No {segment} linked." node (honest gap, never a fabricated node/dead link); fan-out sets rendered; a graph-down flow degrades to the honest `flow_note`. States: resting / loading / no-chain-for-id (the client-computed empty chain, the backend 200) / populated / no-access / error.
- **Search UI** (DASH-06, `/search`): a labeled `<input type="search">` + an accent "Search" (Enter submits), deep-linkable `?q=`, an index segment (All · Executions · Failures · Logs); the results region (`role="region"`) with the `role="status" aria-live` count; `search-results.tsx` typed result cards (Execution/Failure/Log badge — word + icon + hue) with the ES `highlight` fragment rendered as SAFE emphasized text (parsed on the literal `<em>` the server emits — never `dangerouslySetInnerHTML`, T-10-29) + a drill-in link where resolvable. States: resting / loading / no-results (echoed query) / populated / **search-unavailable (the honest 503, DISTINCT from no-results)** / error.
- **Admin users screen** (PLAT-04, `/admin/users`): the users `table` (Email · Role · control) — mono email + `role-badge` + a `dropdown-menu` to change the role; the current admin's own row DISABLED with "You can't change your own role." (the self-demote guard mirror, `myId` from `/me`); the role-change flow (dropdown → the confirm `dialog` "Change {email}'s role?" with the target-is-Admin note → `useMutation` POST with `["users"]`+`["auth","me"]` invalidation, NO optimistic update → the badge REPAINTS from the server response + a success-only sonner toast; on failure the inline error + the OLD badge). States: loading / only-the-admin / populated / changing ("Changing…") / change-failed / non-admin-403 → no-access (T-10-27).
- **Mocked-API e2e** (17 tests): `coverage-traceability-search.spec.ts` (13 — coverage populated/graph-down/empty + the two-metric separation; traceability resting/chain-with-honest-gap/no-chain; search populated/no-results/unavailable-503) + `admin-users.spec.ts` (4 — list + self-row guard; role change → confirm → toast → badge repaint; change-failed inline + OLD badge; non-admin → no-access).

## Task Commits

1. **Task 1: coverage panel (DASH-04) + traceability viewer (DASH-05)** — `1b3a7a3` (feat)
2. **Task 2: search UI (DASH-06) with the honest graceful-degrade** — `c07ae5d` (feat)
3. **Task 3: admin users screen (PLAT-04) + the four-surface mocked e2e** — `20ccb5e` (feat)

## Files Created

- `apps/web/lib/api/coverage.ts` — zod clients for the two coverage metrics (lifecycle + ground-truth).
- `apps/web/lib/api/traceability.ts` — zod client + `EntryType`→query-param map + `flowSegments()`.
- `apps/web/lib/api/search.ts` — zod client (503 distinct) + `firstHighlight()`/`hitTitle()`.
- `apps/web/lib/api/users.ts` — zod client (`getUsers` + `setRole`).
- `apps/web/components/dashboards/chain-view.tsx` — the ordered `<ol>` chain + honest gaps.
- `apps/web/components/dashboards/search-results.tsx` — typed result cards + safe-parsed highlight.
- `apps/web/app/(dashboard)/coverage/page.tsx` — DASH-04 coverage panel.
- `apps/web/app/(dashboard)/traceability/page.tsx` — DASH-05 traceability viewer.
- `apps/web/app/(dashboard)/search/page.tsx` — DASH-06 search UI.
- `apps/web/app/(dashboard)/admin/users/page.tsx` — PLAT-04 admin role-assignment screen.
- `apps/web/tests/e2e/coverage-traceability-search.spec.ts` — 13 mocked-API e2e tests.
- `apps/web/tests/e2e/admin-users.spec.ts` — 4 mocked-API e2e tests.

## Decisions Made

- **Ground-truth coverage shape read off the real backend** (not the plan's loosely-described "discovered/total"): `routers/kg.py` returns `screens_total/screens_covered/flows_total/flows_covered/coverage_percent/measured`. The schema mirrors that; `measured:false` renders the honest "Not yet measured" state, never a fabricated 0%-as-measured.
- **URL-as-source-of-truth for the submitted query** (traceability + search): the `?type=&id=` / `?q=&index=` params drive the query directly; the form state is only the typing buffer seeded from the URL. This avoids a `useEffect` URL-sync — which also satisfies the `react-hooks/set-state-in-effect` lint rule the first traceability draft tripped (see Deviations).
- **The "Execution" picker label maps to the `run` EntryType → the `run_id` query param** — the UI label and the API param name intentionally differ.
- **Unknown traceability id is the client-computed "no chain found" state** (no flow AND every relational segment empty) — the backend returns an honest 200 empty chain (Plan 03 decision), never a 404; the viewer renders the gap message.
- **Search 503 vs empty-200 are distinct branches**: the page checks `ApiError.status === 503` for the honest "search unavailable" state, separate from a `count:0` "No results" state (T-10-30) — never an empty list pretending zero hits.
- **The ES highlight is parsed, not injected**: `HighlightedFragment` splits on the literal `<em>…</em>` the server highlighter emits and renders only those runs as `<em>`, every other run as React-escaped text — no `dangerouslySetInnerHTML`, so a crafted source value can never execute (T-10-29).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] traceability page tripped the react-hooks/set-state-in-effect lint rule**
- **Found during:** Task 1 (running the per-task eslint on the paren paths).
- **Issue:** the first draft synced the `?type=&id=` deep-link into the submitted-entry state via a `useEffect` calling `setFormType/setFormId/setEntry` — eslint's `react-hooks/set-state-in-effect` flags this as a cascading-render anti-pattern (error, not warning).
- **Fix:** removed the effect — the URL params are now read directly as the SINGLE source of truth for the submitted entry (`entry` is derived from `searchParams` each render); the form state is only the not-yet-submitted typing buffer, seeded once from the URL. Applied the same URL-as-source pattern to the search page.
- **Files modified:** `apps/web/app/(dashboard)/traceability/page.tsx` (fixed before the Task 1 commit).
- **Commit:** `1b3a7a3` (folded into the Task 1 commit).

**2. [Rule 1 - Bug] two e2e strict-mode violations on ambiguous text matches**
- **Found during:** Task 3 (running the per-task `npx playwright test`).
- **Issue:** (a) `getByTestId("ground-truth-card").getByText("Exploration completeness")` matched 3 elements (the card heading, the `MeterKpiTile` label, and the definition sentence all contain the phrase) — a strict-mode violation. (b) `getByText("admin@example.test")` matched 2 elements (the sidebar footer `/me` email AND the table row) — a strict-mode violation. Both are test-assertion bugs, not page bugs.
- **Fix:** (a) scoped to the card heading via `.first()` + asserted the meter's `aria-label` ("Exploration completeness: 70%"); (b) scoped the email assertions to `getByRole("table")`.
- **Files modified:** `apps/web/tests/e2e/coverage-traceability-search.spec.ts`, `apps/web/tests/e2e/admin-users.spec.ts` (fixed before the Task 3 commit).
- **Commit:** `20ccb5e` (folded into the Task 3 commit).

No Rule 2/3/4 deviations were required. The plan's `<interfaces>` (the Plan-01..04 payloads, `require_role`/`/me` role, the `MeterKpiTile`/`role-badge`/`dashboard-states`/vendored `table`/`dialog`/`dropdown-menu`/`sonner` precedents) matched the codebase verbatim, except the ground-truth coverage shape which was read off the real `routers/kg.py` (documented above, not a deviation — the plan referenced "the existing GET /api/coverage" generically).

## Issues Encountered

None beyond the two test-assertion bugs above (fixed before their task commits). No first-compile parallel flake recurred on the final full runs (both specs ran 13/13 + 4/4 green deterministically).

## Known Stubs

None — every page is wired to the real Plan-01..04 + Phase-5 endpoints through the zod clients. No placeholder values, no TODO/FIXME, no empty data sources. The nav items for these four pages were shipped in Plan 05; this plan owns the PAGES, completing them.

## Threat Flags

None — the plan's `<threat_model>` (T-10-27..31) is fully covered:
- **T-10-27 (EoP — admin screen reachable by a non-admin):** the API gates `/api/users`; the nav hides Users (Plan 05); a direct URL → 403 → the `<NoAccess>` state, never the data (e2e-asserted).
- **T-10-28 (EoP — self-demote/lockout via the UI):** the self-row control is disabled with the guard caption; the server 400 is the real boundary (e2e-asserted on the disabled self-row).
- **T-10-29 (XSS — rendering the ES highlight):** `HighlightedFragment` parses the literal `<em>` server fragment into text + `<em>` spans (React-escaped) — no `dangerouslySetInnerHTML` anywhere.
- **T-10-30 (Info disclosure — fabricated chain/hit/coverage):** every node/hit/metric renders strictly from the server payload; a missing chain segment is an honest gap; ES-down is an honest 503; coverage `measured:false` is the honest unmeasured state (e2e-asserted).
- **T-10-31 (Info disclosure — conflating the two coverage metrics):** separate cards each with its own definition (e2e-asserted on the SEPARATE ground-truth card).

No new security surface beyond the register.

## Verification

- `cd apps/web && npx tsc --noEmit` — clean.
- `npx eslint "app/(dashboard)/coverage" "app/(dashboard)/traceability" "app/(dashboard)/search" "app/(dashboard)/admin" lib/api/{coverage,traceability,search,users}.ts components/dashboards/{chain-view,search-results}.tsx tests/e2e/{coverage-traceability-search,admin-users}.spec.ts` — clean (paren paths quoted).
- `npx playwright test tests/e2e/coverage-traceability-search.spec.ts tests/e2e/admin-users.spec.ts` — **13 + 4 = 17 passed**.
- `git diff --quiet apps/web/package.json` AND `package-lock.json` — CLEAN (ZERO new frontend deps).
- Grep gate: `react-table` in `app/(dashboard)/coverage` + `app/(dashboard)/admin` → NONE (tables on the vendored shadcn `table`); the role mutation invalidates `["users"]` + `["auth","me"]` with no optimistic update (asserted in the code + the badge-repaint e2e).

## Next Phase Readiness

- Phase 10 is COMPLETE: all six DASH surfaces + the PLAT-04 admin half ship to the approved 10-UI-SPEC over the Plan-01..04 endpoints, role-gated, honest, and a11y-clean. The remaining Phase-10 verification (any live ES/graph round-trips) is the search/graph-profile Manual-Only work already documented in 10-04.
- `ChainView` (the honest-gap lineage renderer) and `HighlightedFragment` (the safe server-highlight parser) are reusable for any future artifact-lineage / search-emphasis surface.

## Self-Check: PASSED

All 12 created files exist on disk; all 3 task commits (`1b3a7a3`, `c07ae5d`, `20ccb5e`) are in the git log.

---
*Phase: 10-dashboards-rbac-coverage-traceability*
*Completed: 2026-06-29*
