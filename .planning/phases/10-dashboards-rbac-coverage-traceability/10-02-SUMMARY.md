---
phase: 10-dashboards-rbac-coverage-traceability
plan: 02
subsystem: dashboards
tags: [dashboards, rbac, coverage, fastapi, sqlalchemy, pydantic, aggregation, role-gate]

# Dependency graph
requires:
  - phase: 10-dashboards-rbac-coverage-traceability
    plan: 01
    provides: require_role(*roles) gate, rbac.ROLE_PERMISSIONS + endpoint->role matrix, users.role
  - phase: 07-execution-engine
    provides: exec_history (pass_rate_trend/list_runs), TestRun/TestResult/TestArtifact, /api/coverage (kg)
  - phase: 09-defect-jira
    provides: Classification + Defect (classification/fingerprint/status), the run_id/flow_id link
  - phase: 05-knowledge-graph
    provides: mine_flows_from_neo4j (the discovered-flow set, f"flow-{i}")
provides:
  - coverage_dash.coverage(db, *, driver) — DASH-04 lifecycle coverage (approved AND passing), distinct from kg/coverage.py
  - role-gated GET /api/coverage/flows (admin|qa_lead|developer) with the honest definition in the payload
  - dashboards.{executive,qa,developer}(db) on-read aggregation services (reuse exec_history)
  - role-gated GET /api/dashboards/{executive,qa,developer} per the rbac.py matrix (403 matrix proven)
affects: [10-05-ui-nav, dashboards, coverage, rbac]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DASH-04 lifecycle coverage = discovered ∩ approved-scenario ∩ passing-execution; distinct module from kg/coverage.py (no shared code path)"
    - "per-route require_role(...) (not router-level) when each route has a different permitted-role set"
    - "dashboard aggregation reuses exec_history fns verbatim; pass_rate 0..1 -> 0..100 percent converted once server-side"
    - "module-scoped event loop + engine.dispose() fixture for Postgres-backed unit tests on Windows (asyncpg cross-loop teardown)"

key-files:
  created:
    - apps/api/app/services/coverage_dash.py
    - apps/api/app/schemas/coverage_dash.py
    - apps/api/app/routers/coverage_dash.py
    - apps/api/app/services/dashboards.py
    - apps/api/app/schemas/dashboards.py
    - apps/api/app/routers/dashboards.py
    - apps/api/tests/unit/test_coverage_dash.py
    - apps/api/tests/integration/test_dashboards.py
  modified:
    - apps/api/app/main.py

key-decisions:
  - "DASH-04 is a SEPARATE module from kg/coverage.py — imports nothing from it, ships its own honest definition string (Pitfall 5 / T-10-11)"
  - "verdict 'passed' is the only 'passing'; failed tests = verdict IN (product_failure, aborted) — there is NO 'failed' verdict (CHECKER LOW-1)"
  - "the pass_rate 0..1 -> 0..100 percent conversion lives in dashboards.executive as kpis.pass_rate_percent (CHECKER LOW-2 x100 point), unambiguous for the UI meter"
  - "root-cause groups key on (Defect.classification, Defect.fingerprint) — Classification has no fingerprint column; Defect carries both"
  - "executive coverage passes the graph driver through; graph-down degrades to the main.py 503 handler, never fabricated zeros (T-10-10)"

patterns-established:
  - "per-route require_role(...) for routes with differing role sets on one router"
  - "lifecycle coverage join (mine_flows ∩ approved ∩ passing) as the DASH-04 metric shape"

requirements-completed: [DASH-01, DASH-02, DASH-03, DASH-04]

# Metrics
duration: ~35min
completed: 2026-06-29
---

# Phase 10 Plan 02: Dashboards + Lifecycle Coverage Summary

**Backend read-services + role-gated routers for the three dashboards (Executive/QA/Developer) and the graph-derived DASH-04 lifecycle coverage metric — on-read aggregation over Phase-4..9 data (mirroring exec_history.py), every endpoint gated by the Plan-01 `require_role`, with the honest coverage definition shipped in the payload and the 403 role matrix proven.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-06-29
- **Tasks:** 3 (all TDD: RED → GREEN)
- **Files modified:** 9 (8 created, 1 modified)

## Accomplishments

- **DASH-04 lifecycle coverage** (`coverage_dash.coverage`): mines the current graph, intersects `discovered_ids = {f"flow-{i}"}` with the distinct approved-scenario flow ids AND the distinct passing-execution flow ids; returns `total_discovered / covered / coverage_percent (1dp, 0.0 when total==0) / covered_flow_ids / flows[]` drill-down PLUS the honest `definition` + `measured_against` (flow_id-positional caveat) strings IN the payload. A DISTINCT module from `kg/coverage.py` — imports nothing from it.
- **Role-gated `GET /api/coverage/flows`** (admin, qa_lead, developer) per the rbac.py matrix, registered before `stubs_router`.
- **Dashboard aggregation service** (`dashboards.{executive,qa,developer}`) reusing `exec_history` verbatim:
  - **executive** — coverage (reuse coverage_dash) + pass-rate trend + defects-filed-per-day trend + KPIs (`pass_rate_percent` 0..100, `open_defects` = Defect rows not rejected).
  - **qa** — `list_runs` history + failed tests (verdict IN product_failure | aborted) with RUN-RELATIVE artifact refs (kind + stored path; never an absolute fs path).
  - **developer** — root-cause groupings (Defect by classification + fingerprint, count desc, with a representative defect id) + errors-per-day trend + module failure breakdown (failures per flow_id, desc).
- **Role-gated `GET /api/dashboards/{executive,qa,developer}`** with PER-ROUTE `require_role(...)` (each dashboard has a different permitted-role set) per the rbac.py matrix; the 403 matrix + 401 unauth proven for all four gated endpoints.

## Task Commits

1. **Task 1: coverage_dash service + schema + role-gated router (DASH-04)** — `e6b55a4` (feat)
2. **Task 2: dashboards aggregation service (exec/qa/dev) + schemas** — `ddb086f` (feat)
3. **Task 3: role-gated dashboards router + registration + the 403 matrix** — `44a65a4` (feat)

_TDD tasks combined RED+GREEN into one commit each (the failing test and its implementation shipped together per atomic-task commit)._

## Files Created/Modified

- `apps/api/app/services/coverage_dash.py` — DASH-04 lifecycle coverage join + honest definition; distinct from kg/coverage.py.
- `apps/api/app/schemas/coverage_dash.py` — `CoverageResponse` + `FlowCoverageRow`.
- `apps/api/app/routers/coverage_dash.py` — role-gated `GET /api/coverage/flows`.
- `apps/api/app/services/dashboards.py` — `executive`/`qa`/`developer` on-read aggregations (reuse exec_history).
- `apps/api/app/schemas/dashboards.py` — the three dashboard schemas (reuse `CoverageResponse` + `TestRunResponse`).
- `apps/api/app/routers/dashboards.py` — per-route role-gated `GET /api/dashboards/{executive,qa,developer}`.
- `apps/api/app/main.py` — `coverage_dash_router` + `dashboards_router` included before `stubs_router`.
- `apps/api/tests/unit/test_coverage_dash.py` — 5 tests (the join, failing-only-not-covered, zero-discovered, honest definition, no-shared-code-path).
- `apps/api/tests/integration/test_dashboards.py` — 6 tests (aggregates, empty honest, the 4-endpoint role matrix).

## Decisions Made

- **DASH-04 is a separate metric from kg/coverage.py** (Pitfall 5 / T-10-11): the module imports nothing from `kg/coverage.py`, uses a different result shape (no `screens_total`), and ships its own honest definition. A unit test asserts the no-shared-code-path invariant via `inspect.getsource`.
- **No 'failed' verdict anywhere** (CHECKER LOW-1): the verdict vocabulary is passed | flaky | product_failure | aborted. "Passing" = `verdict == 'passed'`; "failed tests" / "module failures" = `verdict IN (product_failure, aborted)`. Nothing seeds or queries a 'failed' verdict.
- **pass_rate ×100 conversion documented and centralized** (CHECKER LOW-2): `exec_history.pass_rate_trend` returns `pass_rate` as 0..1; the executive KPI converts the latest day's value to `kpis.pass_rate_percent` (0..100) ONCE, server-side, so the displayed % and the UI meter's 0-100 scale agree. The raw 0..1 trend is still returned for the chart.
- **Root-cause groups key on Defect, not Classification**: `Classification` has no `fingerprint` column (it lives on `Defect`). Grouping on `(Defect.classification, Defect.fingerprint)` gives the dedup-keyed root-cause grouping with a representative defect id (`min(Defect.id)`).
- **Per-route require_role** (not router-level): each dashboard has a different permitted-role set (executive admin/qa_lead; qa adds qa_engineer; developer swaps in developer), so the gate is declared per-route via `dependencies=[Depends(require_role(...))]` on each `@router.get`.
- **Graph-down honesty for the executive coverage tile** (T-10-10): the executive route passes the driver through to coverage; a down graph raises `ServiceUnavailable` which the existing `main.py` `_neo4j_unavailable_handler` turns into a clean 503 — never a fabricated zero.

## Deviations from Plan

None - plan executed exactly as written. No Rule 1-4 deviations were required. All interfaces matched the plan's `<interfaces>` block (the exec_history functions, `mine_flows_from_neo4j`, the models, and `require_role`) verbatim.

One implementation detail worth noting (NOT a deviation): the keyless coverage_dash unit tests are Postgres-backed (they seed Scenario/TestResult rows), so they carry the `integration` marker and a module-scoped event-loop + `engine.dispose()` fixture — the same Windows asyncpg cross-loop discipline used by `test_role_assign.py` / `test_defects_router.py`. The graph mine is monkeypatched (keyless), matching the plan's "fixture-testable keyless; the graph-marked variant runs under graph_mode."

## Issues Encountered

- **Full-suite flake (out of scope, pre-existing):** `tests/unit/test_classifier_evidence.py::test_gather_evidence_and_classify_product_failure` failed once in the full deterministic run with the Windows asyncio proactor teardown error (`'NoneType' object has no attribute 'send'`). It **passes cleanly in isolation** (1 passed) — the exact pre-existing Windows event-loop teardown race documented in the 10-01 SUMMARY, in a classifier file untouched by this plan. Logged as out-of-scope per the SCOPE BOUNDARY rule; not fixed. Remaining suite: 440 passed.

## Known Stubs

None — every file is wired to real data/queries. No placeholder values, no TODO/FIXME, no empty data sources. (The frontend pages that render these payloads are Plan 05; this slice is the backend read-surface only, as scoped.)

## Threat Flags

None — the plan's `<threat_model>` (T-10-07..11) is fully covered: every dashboard/coverage endpoint is `require_role`-gated (T-10-07/08, the 403 matrix asserted); QA artifact refs are the RUN-RELATIVE stored path only (T-10-09, asserted not-absolute); the executive coverage tile degrades to the honest 503 when the graph is down (T-10-10); coverage_dash is a distinct module shipping its own definition (T-10-11, no-shared-code-path asserted). No new security surface beyond the register.

## Verification

- Plan test files green: `test_coverage_dash.py` (5) + `test_dashboards.py` (6) → **11 passed**.
- Grep gates: `require_role` in `routers/dashboards.py` non-comment count = **6** (≥3 ✓); `kg.coverage` import in `coverage_dash.py` = **0** ✓; `definition` present in `coverage_dash.py` ✓.
- Full deterministic suite (`not live_llm and not e2e and not graph and not functional and not search`): **440 passed**, 1 out-of-scope pre-existing Windows teardown flake (passes in isolation).

## Next Phase Readiness

- The three dashboard endpoints + the coverage endpoint return the exact aggregate shapes Plan 05's UI renders, all role-gated. Plan 05 builds the zod clients + role-gated pages over these payloads (and builds the auth-gated artifact URL from the run-relative `path` per the Phase-7 contract — never an fs path).
- Plan 03 (traceability) reuses the same exec_history + FK-linked-models join discipline; Plan 04 (search) reuses the graceful-degrade + role-gate patterns established here.

## Self-Check: PASSED

All 8 created files exist on disk; all 3 task commits (`e6b55a4`, `ddb086f`, `44a65a4`) are in the git log.

---
*Phase: 10-dashboards-rbac-coverage-traceability*
*Completed: 2026-06-29*
