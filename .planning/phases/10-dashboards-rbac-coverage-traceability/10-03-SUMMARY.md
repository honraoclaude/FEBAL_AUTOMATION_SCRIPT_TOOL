---
phase: 10-dashboards-rbac-coverage-traceability
plan: 03
subsystem: traceability
tags: [traceability, cross-store-join, fastapi, sqlalchemy, pydantic, role-gate, single-write-path]

# Dependency graph
requires:
  - phase: 10-dashboards-rbac-coverage-traceability
    plan: 01
    provides: require_role(*roles) gate, rbac.ROLE_PERMISSIONS + endpoint->role matrix
  - phase: 10-dashboards-rbac-coverage-traceability
    plan: 02
    provides: the exec_history-style read-service + role-matrix test discipline reused here
  - phase: 09-defect-jira
    provides: Classification + Defect (run_id/flow_id + jira_key — the JIRA-04 chain link)
  - phase: 07-execution-engine
    provides: TestRun/TestResult/TestArtifact (run_id/flow_id lifecycle rows)
  - phase: 05-knowledge-graph
    provides: mine_flows_from_neo4j (the discovered-flow set, READ-only) + core.workspaces.run_dir
provides:
  - traceability.chain(db, *, flow_id/run_id/scenario_id/defect_id, driver) — DASH-05 read-time cross-store join from any one entry artifact id
  - role-gated GET /api/traceability (admin|qa_lead|developer) returning the lifecycle chain
  - TraceabilityResponse schema (nullable flow + flow_note + honest-gap segment lists)
affects: [10-05-ui-nav, traceability-viewer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "read-time cross-store join (Neo4j flows + Postgres lifecycle) keyed by ANY entry artifact id; mirrors exec_history.get_run_status resolve-key→assemble-rows shape"
    - "single-write-path discipline enforced by a source-gate test (inspect.getsource + write-Cypher regex over code lines only, skipping prose)"
    - "honest gaps — every missing chain segment is an explicit empty list / null, never a fabricated node"
    - "graph-down degrades the flow segment to null + a note inside the service so a down graph never 500s the chain"
    - "convention-derived script path from run_id via core.workspaces.run_dir (A4 — NOT a stored column), marked derived=True"
    - "exactly-one-entry-id rule enforced in the router (422 for zero or multiple); unknown id → 200 honest empty (not 404)"

key-files:
  created:
    - apps/api/app/services/traceability.py
    - apps/api/app/schemas/traceability.py
    - apps/api/app/routers/traceability.py
    - apps/api/tests/integration/test_traceability.py
  modified:
    - apps/api/app/main.py

key-decisions:
  - "chain(db, *, flow_id/run_id/scenario_id/defect_id, driver) resolves run_id+flow_id from whichever single entry was given, then assembles flow/scenarios/scripts/executions/artifacts/defects on those keys"
  - "the service adds ZERO Neo4j writes — a no-write-Cypher source-gate test (MERGE|CREATE |SET x=|DELETE) keeps the single-write-path grep gate green over the file"
  - "the script segment is convention-derived from the Scenario row's run_id via run_dir (A4 CONFIRMED — not a stored column), each entry marked derived=True"
  - "the flow segment is best-effort READ-only — a graph-down (any exception from mine_flows_from_neo4j) degrades to flow=null + flow_note, never raising (T-10-16); the relational chain still assembles"
  - "the router enforces EXACTLY one entry id (422 for zero or multiple — it never silently picks); an unknown id returns an honest empty chain at 200, NOT a 404"
  - "the router exposes only the static GET '' with query params — no typed /{id} converter exists, so the static-before-typed ordering caveat is moot here"

patterns-established:
  - "read-time cross-store traceability join keyed by any artifact id"
  - "source-gate test asserting a service holds no write-Cypher (single-write-path enforcement)"

requirements-completed: [DASH-05]

# Metrics
duration: ~7min
completed: 2026-06-29
---

# Phase 10 Plan 03: Traceability Cross-Store Join Summary

**The read-time DASH-05 traceability engine — `traceability.chain` assembles the full flow ↔ scenario ↔ script ↔ execution ↔ defect lifecycle chain from ANY single entry artifact id (flow_id / scenario_id / run_id / defect_id) by joining the Neo4j discovered-flow set (READ-only, via `mine_flows_from_neo4j`) with the Phase-9 FK-linked Postgres lifecycle tables on run_id + flow_id — exposed through a role-gated `GET /api/traceability` that requires exactly one entry id, renders missing segments as honest empty/null gaps, derives the script path from run_id by convention (A4), degrades gracefully when the graph is down, and adds ZERO graph writes (the single-write-path discipline holds, guarded by a source-gate test).**

## Performance

- **Duration:** ~7 min
- **Completed:** 2026-06-29
- **Tasks:** 2 (both TDD: RED → GREEN combined per atomic-task commit)
- **Files modified:** 5 (4 created, 1 modified)

## Accomplishments

- **`traceability.chain(db, *, flow_id=None, run_id=None, scenario_id=None, defect_id=None, driver=None) -> dict`** — the read-time cross-store join:
  - **Resolves the keys from any entry id:** scenario_id → Scenario row → its run_id+flow_id; defect_id → Defect row → run_id+flow_id; run_id → the distinct flow_ids on that run's TestResults; flow_id → used directly.
  - **Flow segment** (best-effort, READ-only): the mined flow record (name/category/risk_tier/step_count) for the entry flow_id via `mine_flows_from_neo4j`; a graph-down (any exception) degrades to `flow=null` + `flow_note`, never raising.
  - **Scenarios** by flow_id (+ run_id when pinned), **scripts** convention-derived from each scenario's run_id via `run_dir` (`derived=True`), **executions** = TestResult joined to its parent TestRun (tier/status) by run_id+flow_id, **artifacts** = TestArtifact (RUN-RELATIVE path), **defects** = Defect by run_id+flow_id incl. the `jira_key` JIRA-04 link.
  - **Honest gaps:** every missing segment is an EXPLICIT empty list / null; an unknown id echoes the entry with every segment empty (the "no chain found" state).
  - **Zero graph writes** — all SQLAlchemy 2.0 select/scalars; the only graph touch is the READ-only mine.
- **`TraceabilityResponse` schema** — nullable `flow` (single record or list) + `flow_note` + the six segment lists, each item carrying its own id + drill keys.
- **Role-gated `GET /api/traceability`** (admin, qa_lead, developer per the rbac.py matrix), requiring EXACTLY one entry id (422 for zero or multiple), returning the chain for each entry, and an honest empty chain (200) for an unknown id. Registered before `stubs_router`.

## Task Commits

1. **Task 1: cross-store chain assembly keyed by any artifact id (DASH-05)** — `4a6f41b` (feat)
2. **Task 2: role-gated router + schema + registration** — `f6360ee` (feat)

_TDD tasks combined RED+GREEN into one commit each (the failing test and its implementation shipped together per the atomic-task / 10-02 precedent)._

## Files Created/Modified

- `apps/api/app/services/traceability.py` — the `chain` cross-store join + `_resolve_keys` / `_flow_segment` / `_entry` helpers; READ-only, honest gaps, graph-down degrade.
- `apps/api/app/schemas/traceability.py` — `TraceabilityResponse` + the per-segment BaseModels (EntryRef/FlowSegment/ScenarioSegment/ScriptSegment/ExecutionSegment/ArtifactSegment/DefectSegment).
- `apps/api/app/routers/traceability.py` — role-gated `GET /api/traceability` with the exactly-one-entry-id 422 rule + the driver pass-through.
- `apps/api/app/main.py` — `traceability_router` imported + included before `stubs_router`.
- `apps/api/tests/integration/test_traceability.py` — 6 tests: chain-from-each-entry-id (incl. honest-gap + no-match), graph-down-degrades-honestly, the no-write-Cypher source gate, the role matrix, exactly-one-entry-id (422), and chain-for-each-entry over the router (incl. unknown-id honest-empty 200).

## Decisions Made

- **Key resolution from any entry id is one small select each** (the exec_history `get_run_status` "resolve a key → assemble related rows" shape): scenario/defect entries pin the run_id; a flow_id entry does not pin a run, so the chain spans every run carrying that flow_id; a run_id entry resolves its TestResult flow_ids.
- **Script path is convention-derived, not stored (A4 CONFIRMED):** derived from each scenario's run_id via `core.workspaces.run_dir`, one per distinct run_id, each marked `derived=True`. No new column, no migration.
- **Zero graph writes, guarded by a source-gate test:** `test_no_write_cypher_in_traceability` scans `inspect.getsource(traceability)` for the write-Cypher keywords (`MERGE` / `CREATE ` / `SET x=` / `DELETE`) over CODE lines only (skipping comments + docstring prose so the module may name the forbidden keywords). The single-write-path grep gate stays green.
- **Graph-down degrades inside the service** (T-10-16): `_flow_segment` catches any exception from the mine and returns `([], note)`; the router can therefore pass the lazy driver through unconditionally — a down graph never 500s the chain and the relational segments still assemble.
- **Exactly-one-entry-id is a router rule** (not silently picked): `len(provided) != 1 → HTTPException(422)`. An unknown id is NOT an error — the service returns an honest empty chain the router returns at 200 (the viewer renders the gap; a 404 would be dishonest about a valid-but-unmatched id).
- **No typed `/{id}` converter** on this router (only the static `GET ""` with query params), so the static-before-typed ordering caveat from `defects.py` does not apply here — noted explicitly in the router docstring.

## Deviations from Plan

None — plan executed exactly as written. No Rule 1-4 deviations were required. All interfaces matched the plan's `<interfaces>` block (`mine_flows_from_neo4j`, `run_dir`, the run_id+flow_id-keyed models, `require_role`) verbatim.

Two non-deviation implementation notes: (1) the `flow` field is typed `FlowSegment | list[FlowSegment] | None` so a single-flow entry renders one record while a multi-flow run entry can carry the set — both honest, never fabricated. (2) The tests carry the `integration` marker with the module-scoped event-loop + `engine.dispose()` fixture (the Windows asyncpg cross-loop discipline from 10-01/10-02), since they seed real Postgres rows; the graph mine is monkeypatched (keyless), matching "fixture-testable keyless; the graph-marked variant runs under graph_mode."

## Issues Encountered

None. The full deterministic suite ran clean (447 passed) — the pre-existing Windows proactor-teardown flake noted in 10-02 did not recur this run.

## Known Stubs

None — every segment is wired to real queries/data. No placeholder values, no TODO/FIXME, no empty data sources. (The traceability viewer page that renders this payload is Plan 05; this slice is the backend read-surface only, as scoped.)

## Threat Flags

None — the plan's `<threat_model>` (T-10-12..16) is fully covered, no new surface introduced:

- **T-10-12 (EoP):** `GET /api/traceability` is router-level `require_role("admin","qa_lead","developer")`-gated; the 403 matrix + 401 unauth asserted.
- **T-10-13 (Tampering / single-write-path):** the service joins on READ only — the no-write-Cypher source-gate test keeps the grep gate green.
- **T-10-14 (Tampering / injection):** entry ids are SQLAlchemy-parameterized query VALUES (`.where(... == id)` / `.in_(...)`), never string-built; the graph touch is the parameterized read-only mine.
- **T-10-15 (Info Disclosure / fabricated link):** missing segments render as honest empty/null gaps; only server-confirmed rows appear (asserted via the honest-gap + no-match tests).
- **T-10-16 (DoS / graph-down):** the flow segment degrades to null + a note; the relational chain still assembles (asserted via `test_graph_down_degrades_honestly`).

## Verification

- Plan test file green: `test_traceability.py` → **6 passed** (chain-from-each-entry + graph-down + no-write-gate + role-matrix + exactly-one-id-422 + chain-for-each-entry-router).
- Grep gates: code-only write-Cypher in `services/traceability.py` = **0** (only the docstring prose names the keywords) ✓; `require_role` non-comment count in `routers/traceability.py` = **3** (≥1 ✓).
- Full deterministic suite (`not live_llm and not e2e and not graph and not functional and not search`): **447 passed**, 0 regressions (was 440 in 10-02; +the 6 new traceability tests, with the others unchanged).

## Next Phase Readiness

- `GET /api/traceability` returns the exact chain shape Plan 05's viewer renders, role-gated, with honest gaps. Plan 05 builds the zod client + the role-gated traceability page over this payload (the `?type=&id=` deep-link picker maps directly to the four entry query params; artifact URLs build from the run-relative `path` per the Phase-7 contract).
- The single-write-path discipline is now guarded by a source-gate test pattern that Plan 04 (search) can reuse for its own no-write assertions.

## Self-Check: PASSED

All 4 created files exist on disk; `main.py` modified; both task commits (`4a6f41b`, `f6360ee`) are in the git log.

---
*Phase: 10-dashboards-rbac-coverage-traceability*
*Completed: 2026-06-29*
