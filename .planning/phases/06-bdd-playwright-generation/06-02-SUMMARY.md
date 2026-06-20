---
phase: 06-bdd-playwright-generation
plan: 02
subsystem: api+web
tags: [scenarios, review-queue, no-vacuous-gate, auth-gated-router, nextjs, zod, playwright-e2e, rbac]

# Dependency graph
requires:
  - phase: 06-bdd-playwright-generation
    provides: "scenario_service (get/list/set_status/update_gherkin/list_approved), gates (validate_gherkin + resolve_then_refs/assert_non_vacuous), generation.generate_scenarios, Scenario model + then_refs sidecar (06-01)"
  - phase: 05-knowledge-graph-flow-learning
    provides: "kg/reader.flows_source + kg/flows.build_flows (source-flow risk), kg/writer (graph-test seeding)"
  - phase: 01-foundation-dev-environment
    provides: "locked design system (shadcn vendored, --status-* tokens, app-sidebar NAV_ITEMS, api client wrapper + sonner), Playwright e2e harness"
provides:
  - "Auth-gated review router (GET list/get, POST edit/approve/reject) re-running BOTH gates on edit AND approve (D-02/D-04); 422 + no-save on failure; only-approved-feed-codegen via list_approved (D-01)"
  - "Honest server-authoritative per-Then results (ThenRefResult resolved/kg_ref/reason) — never fabricated green (D-03); graph-unreachable degrades fast to all-unresolved"
  - "POST /generate-scenarios entrypoint (feeds the review queue) + GenerateScenariosRequest/GenerateScriptsRequest request schemas"
  - "Review-queue UI: list (status+risk+filter) + detail/review (styled-native Gherkin editor, honest gate indicators, edit→re-validate→approve flow) built exactly to 06-UI-SPEC; one 'Scenarios' sidebar item"
affects: [06-03-codegen, 06-04-stability-seeded-bug]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Best-effort UI enrichment guarded by asyncio.wait_for: source-flow risk + per-Then resolution never block/hang a mutation when the graph profile is down (honest None risk / honest all-unresolved)"
    - "Raw then_refs sidecar exposed on ScenarioDetail so the edit-save forwards the row's OWN structured refs unchanged — the no-vacuous gate re-validates them server-side (D-02)"
    - "React 'adjust state during render' (no effect) to reset the editor from server-saved text — avoids the set-state-in-effect cascade lint"

key-files:
  created:
    - apps/api/app/schemas/scenario.py
    - apps/api/app/routers/scenarios.py
    - apps/api/tests/functional/test_scenarios_router.py
    - apps/web/lib/api/scenarios.ts
    - apps/web/app/(dashboard)/scenarios/page.tsx
    - apps/web/app/(dashboard)/scenarios/[id]/page.tsx
    - apps/web/components/scenarios/gate-indicators.tsx
    - apps/web/components/scenarios/gherkin-editor.tsx
    - apps/web/components/scenarios/status-badge.tsx
    - apps/web/components/scenarios/scenario-states.tsx
    - apps/web/tests/e2e/scenarios.spec.ts
  modified:
    - apps/api/app/routers/generate.py
    - apps/api/app/main.py
    - apps/web/components/app-sidebar.tsx

key-decisions:
  - "Risk lookup + per-Then resolution are best-effort and asyncio.wait_for-bounded (3s) so reject/edit/list never hang on a down Bolt; a graph-unreachable per-Then is reported NOT resolved (honest, never fabricated green) rather than erroring the whole response"
  - "ScenarioDetail exposes the raw then_refs (not just resolved then_results) so the edit-save forwards the row's own structured refs unchanged for server-side re-validation (D-02); editing the structured refs themselves is out of scope this slice (reviewer edits Gherkin text)"
  - "The Gherkin editor is a token-styled NATIVE <textarea> reusing input.tsx classes — zero shadcn add (the textarea block is deliberately not vendored); zero new frontend dependency"
  - "Scenario-specific inline error copy (ScenarioErrorState) instead of reusing the graph error state's graph-worded copy (06-UI-SPEC fidelity)"

patterns-established:
  - "Functional router tests seed/read-back over a short-lived host SQLAlchemy engine (host DSN) and clean up per-test — mirrors test_kg_endpoints' host-driver seed/read-back"
  - "Non-graph router lifecycle coverage = paths that resolve BEFORE any neo4j read (lint-422, 404, reject); resolvable/vacuous/approve are graph-marked (Manual-Only, like 06-01)"

requirements-completed: [GEN-02]

# Metrics
duration: ~55min
completed: 2026-06-20
---

# Phase 6 Plan 02: Scenario Review Queue Summary

**The auth-gated approve/edit review queue (GEN-02): a router that re-runs BOTH quality gates on edit-save AND approve (422 + no-save on failure, D-02/D-04), exposes honest server-authoritative per-Then no-vacuous results (never fabricated green, D-03), feeds codegen approved-only (D-01), plus the review-queue UI built exactly to 06-UI-SPEC with a styled-native Gherkin editor — zero new shadcn, zero new deps.**

## Performance
- **Duration:** ~55 min
- **Completed:** 2026-06-20
- **Tasks:** 2
- **Files modified:** 14 (11 created, 3 modified)

## Accomplishments
- **Auth-gated review router** (`routers/scenarios.py`): `GET /api/scenarios?status=` (default drafts; `all` lists every row; each row carries its source-flow risk, honest None unscored), `GET /api/scenarios/{id}` (one scenario + per-Then results), `POST .../edit` (re-run BOTH gates → 422 + no-save on failure, else update_gherkin edited/draft), `POST .../approve` (re-run BOTH gates → approved only on pass, else 422), `POST .../reject` (rejected). Router-level `Depends(get_current_user)` — every endpoint 401 unauth (T-06-07).
- **Honest gate display (D-03):** per-Then `then_results` derived from `resolve_then_refs` — green only when the server confirms resolution; a graph-unreachable Then is honestly reported NOT resolved (reason "knowledge graph unreachable"), never a fabricated green.
- **`POST /generate-scenarios`** added to `generate.py` (feeds the queue; GenerationError→422, _require_run 404); request schemas (GenerateScenariosRequest + the Slice-3 GenerateScriptsRequest) live in `schemas/scenario.py`.
- **Review-queue UI built exactly to 06-UI-SPEC:** list (Scenario drill-in link · Source flow · reused RiskBadge · StatusBadge + "Edited" caption · mono Updated; risk-desc sort; deep-linkable filter segments; loading/two-empty/error states) + detail/review (breadcrumb, title+status, styled-native Gherkin editor, honest GateIndicators, Source-flow section, Approve disabled until gates pass AND no unsaved edit, Reject confirm dialog, inline-422-text-preserved, success-only toasts, query invalidation, no optimistic updates).
- **One sidebar item** ("Scenarios", ListChecks, after "Knowledge graph"); zod-at-boundary client mirroring the Pydantic models.

## Task Commits
1. **Task 1: auth-gated review router + schemas + generate-scenarios** — `0182224` (feat)
2. **Task 2: review-queue UI (list + detail/edit) + zod client + sidebar + e2e** — `c43076b` (feat)

## Files Created/Modified
- `apps/api/app/schemas/scenario.py` — ScenarioSummary/Detail + ThenRefResult + Edit/Generate request models (then_refs exposed on Detail for edit re-validation)
- `apps/api/app/routers/scenarios.py` — the auth-gated review router (gates re-run on edit + approve; honest per-Then; risk + resolution best-effort/timeout-bounded)
- `apps/api/app/routers/generate.py` — added POST /generate-scenarios
- `apps/api/app/main.py` — wired scenarios_router before stubs_router
- `apps/api/tests/functional/test_scenarios_router.py` — 401-unauth (every endpoint) + non-graph reject/malformed-422/404 + graph-marked resolvable lifecycle + list_approved
- `apps/web/lib/api/scenarios.ts` — zod schemas + fetchers
- `apps/web/app/(dashboard)/scenarios/page.tsx` — review-queue list
- `apps/web/app/(dashboard)/scenarios/[id]/page.tsx` — detail/review + edit→re-validate→approve flow
- `apps/web/components/scenarios/{gherkin-editor,gate-indicators,status-badge,scenario-states}.tsx` — compositions over existing tokens/blocks
- `apps/web/components/app-sidebar.tsx` — "Scenarios" nav item
- `apps/web/tests/e2e/scenarios.spec.ts` — mocked-API e2e (8 tests)

## Decisions Made
See key-decisions in frontmatter. Notably: the source-flow risk lookup and the per-Then resolution are best-effort and `asyncio.wait_for`-bounded so a down graph profile never hangs a mutation (the api boots without neo4j), and the raw `then_refs` is exposed on the detail so an edit-save re-validates the row's own structured refs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Risk/resolution lookups hung mutations when the graph profile is down**
- **Found during:** Task 1 (running the non-graph functional lifecycle)
- **Issue:** `reject` (and any handler returning a ScenarioDetail) called `_flow_risk_index` + `_then_results`, both of which open a Bolt read; against a down neo4j the connect blocked until the 30s httpx client timeout fired (ReadTimeout) instead of degrading. A `ServiceUnavailable` from `_then_results` also escaped to the global 503 handler.
- **Fix:** Wrapped both in `asyncio.wait_for(..., 3s)`; on timeout/error the risk index is honestly empty (None risk) and the per-Then results are honestly all-unresolved (reason "knowledge graph unreachable") — never fabricated green, never a hang. Approve still independently re-runs `assert_non_vacuous` (correctly 503s if the graph is needed and down).
- **Files modified:** apps/api/app/routers/scenarios.py
- **Verification:** `pytest tests/functional/test_scenarios_router.py -m "not graph"` → 10 passed (reject no longer times out).
- **Committed in:** 0182224 (Task 1)

**2. [Rule 3 - Blocking] Expose raw then_refs on ScenarioDetail for the edit re-validation**
- **Found during:** Task 2 (wiring the edit-save mutation)
- **Issue:** The detail response carried only resolved `then_results` (no `kind`/`ref`), so the client could not faithfully forward the structured refs on an edit-save; sending text-only markers would always fail the no-vacuous gate (422), breaking the "edit valid Gherkin → 200" flow.
- **Fix:** Added `then_refs: list` to `ScenarioDetail` (Pydantic + zod) and returned `row.then_refs` from the router; the edit-save forwards them unchanged so the gate re-validates the row's own refs (D-02 intent).
- **Files modified:** apps/api/app/schemas/scenario.py, apps/api/app/routers/scenarios.py, apps/web/lib/api/scenarios.ts, apps/web/app/(dashboard)/scenarios/[id]/page.tsx
- **Committed in:** c43076b (Task 2)

**3. [Rule 1 - Bug] Scenario-specific error copy (UI-SPEC fidelity)**
- **Found during:** Task 2 (e2e error-state)
- **Issue:** Reusing the graph `ErrorState` showed graph-worded copy ("Couldn't load the knowledge graph…") on the scenarios surface — not the 06-UI-SPEC error copy.
- **Fix:** Added `ScenarioErrorState` with the spec copy ("Couldn't load scenarios. Try again — … docker compose ps") and a Retry button, used by both the list and detail.
- **Files modified:** apps/web/components/scenarios/scenario-states.tsx (+ page wiring)
- **Committed in:** c43076b (Task 2)

---

**Total deviations:** 3 auto-fixed (2 bug, 1 blocking)
**Impact on plan:** No scope change. The risk/resolution timeout hardens the down-graph path (correctness + honesty), the then_refs exposure is the minimal enabler for the D-02 edit flow, and the error copy is a UI-SPEC fidelity fix.

## Environment Notes (operational, not code)
- The host (3GB WSL cap) OOM'd the api container twice while uvicorn `--reload` re-imported the new router under memory pressure with the web container (1.5g) running. Following the graph_mode pattern, `web` was stopped to free memory so the api could boot, then `web` was restarted after verification. No code impact; an inherent constraint of this dev box.
- The api `app/` is a hot-reload bind mount, so new router files reach the running container, but adding a NEW module imported by `main.py` requires an api restart (uvicorn `--reload` re-imports changed files but a brand-new module wired into the app needs the worker to re-import main).

## Verification Results
- `cd apps/api && uv run pytest tests/functional/test_scenarios_router.py -m "not graph" -q` → **10 passed, 4 deselected**.
- `cd apps/api && uv run pytest tests/unit/test_single_write_path.py -q` → **2 passed** (router adds zero write-Cypher).
- `cd apps/api && uv run pytest -m "not live_llm and not e2e and not graph" -q` → **270 passed, 38 deselected** (no regressions; +10 over 06-01's 260).
- `scenarios_router` present in `/openapi.json` (all 6 scenario paths registered).
- `cd apps/web && npx tsc --noEmit` → clean; `eslint` on touched paths → clean.
- `cd apps/web && npx playwright test tests/e2e/scenarios.spec.ts` → **8 passed** (list/filter/drill-in/edit-422-inline/edit-200-honest/approve/reject-confirm/empty/error).
- `git diff --exit-code apps/web/package.json apps/web/package-lock.json` → clean (zero new frontend deps); no `components/ui/textarea.tsx` created (styled-native textarea).

## Manual-Only (provider keys / graph)
- The graph-marked router lifecycle (resolvable edit-200, vacuous-422, approve, list_approved-against-graph) needs neo4j under graph_mode — authored + green-by-construction, run Manual-Only per project convention (like 06-01's graph tests).
- Live generate→review→approve (the full chain) needs a provider key for `/generate-scenarios` — Manual-Only.

## Next Phase Readiness
- Slice 2 complete: generated drafts can be triaged (list/edit/approve/reject) with both gates re-run server-side; only approved rows feed codegen (`list_approved`).
- Ready for Slice 3 (codegen): the `GenerateScriptsRequest` schema is in place; codegen reads `scenario_service.list_approved(run_id)` and emits the Playwright project from approved-only scenarios (D-01/D-05/D-06).

## Self-Check: PASSED
All 8 spot-checked created files exist on disk; both task commits (0182224, c43076b) are present in git history.

---
*Phase: 06-bdd-playwright-generation*
*Completed: 2026-06-20*
