---
phase: 07-execution-engine-workers
plan: 02
subsystem: api
tags: [execution-engine, tier-selection, risk-ranking, pytest-bdd-markers, codegen, exec-01, d-01, d-02, d-03b, keyless]

# Dependency graph
requires:
  - phase: 07-execution-engine-workers
    plan: 01
    provides: "exec_service producer (create_test_run/enqueue_jobs) + TestRun/TestResult ORM models (test_runs/test_results) the tier selector + failure-history ranking build on"
  - phase: 06-bdd-playwright-generation
    provides: "codegen/project.py _render_checked_py gate + conftest.py.j2 template (the marker-registration home)"
  - phase: 05-knowledge-graph
    provides: "kg/flows.build_flows (per-flow graph risk_score records) + kg/reader.flows_source + routers/scenarios._flow_risk_index (the wait_for + honest-empty shape copied verbatim)"
provides:
  - "exec_service.TIER_SELECTOR map + resolve_tier (tag→-m, full/risk-based→[], unknown→ValueError/422; T-07-05)"
  - "exec_service.RiskRankWeights frozen dataclass ([ASSUMED] risk_weight=0.6/failure_weight=0.4/top_n=10)"
  - "exec_service.failure_rate (product_failure/total over last K test_runs from test_results; cold-start→0.0)"
  - "exec_service._load_flow_risk (build_flows RECORD LIST under asyncio.wait_for(_RISK_TIMEOUT_S=3.0), honest-empty on graph-down)"
  - "exec_service.rank_risk_flows (combined = risk_weight*risk_score + failure_weight*failure_rate*100, top-N; D-03b sequencing documented)"
  - "generated-project tier markers (conftest.py.j2 pytest_configure registers smoke/sanity/regression) so -m <tag> selects"
affects: [07-03, 07-04, 07-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tier resolution = constant selector tokens (TIER_SELECTOR) behind an allow-list (TIER_SELECTOR keys + risk-based); the raw client tier string is NEVER echoed into argv (T-07-05), unknown → ValueError → 422"
    - "Risk-based ranking RANKS build_flows' per-flow records (each already carrying the real graph risk_score) — never a direct risk_score() call; grep \"risk_score(\" exec_service.py finds nothing"
    - "Bounded graph read = the routers/scenarios._flow_risk_index shape copied verbatim: asyncio.wait_for(_RISK_TIMEOUT_S=3.0) on BOTH flows_source and build_flows inside ONE try/except returning honest-empty (no hang on graph down/slow/not-discovered)"
    - "D-03b sequencing: risk-based resolves while neo4j is UP and BEFORE the run phase (materialize the spec list), then the run phase proceeds with neo4j off (3GB WSL budget)"
    - "Frozen-weight tuning surface (RiskRankWeights) mirrors kg/risk.RiskWeights — [ASSUMED] starting points, low blast radius"
    - "Generated-project marker registration lives in conftest.py.j2 pytest_configure (rendered valid Python through _render_checked_py, no new template file) so -m smoke selects with no PytestUnknownMarkWarning (RESEARCH Pitfall 3)"

key-files:
  created:
    - apps/api/tests/unit/test_exec_tiers.py
    - apps/api/tests/unit/test_risk_ranking.py
    - apps/api/tests/functional/test_codegen_markers.py
  modified:
    - apps/api/app/services/exec_service.py
    - apps/api/app/templates/conftest.py.j2

key-decisions:
  - "Tier-marker registration HOME = conftest.py.j2 pytest_configure (the plan's first option), NOT a rendered pytest.ini/pyproject entry — keeps the registration in the existing rendered file (no new template), mirrors the api's own [tool.pytest.ini_options] markers block, and rides the _render_checked_py ast-parse gate"
  - "resolve_tier returns a COPY (list(...)) of the constant selector, never the shared mutable list — a caller mutating the argv can't poison TIER_SELECTOR for the next run (the test asserts `selector is not TIER_SELECTOR['smoke']`)"
  - "_load_flow_risk returns the build_flows RECORD LIST (not the dict index routers/scenarios._flow_risk_index returns) because the ranking needs the full per-record risk_score; the wait_for + honest-empty shape is otherwise byte-for-byte the same seam"
  - "failure_rate sources the last K DISTINCT test_runs by created_at recency (RESEARCH failure-history SQL: product_failure count / total per flow); empty history → 0.0 for all flows (graceful cold-start, pure structural-risk order)"
  - "spec_path per ranked flow = features/<flow_id>.feature (the codegen feature-naming convention) — a stable run-relative reference the run phase materializes; the unit test only asserts it is present + truthy (the codegen graph wiring is owned by Plan 06's generate_project)"
  - "The two unit test files were reused VERBATIM from the interrupted prior run (read + judged sound + aligned with the plan's behavior block) — committed as the RED gate before any production code"

patterns-established:
  - "Selector resolution + dynamic risk ranking live in exec_service (the api producer), NOT the worker plane — exec_service imports kg.flows/kg.reader, which is fine: the SC3 NO-LLM gate scans only the worker package + worker_main, and exec_service never resolves risk during the run phase (D-03b)"
  - "Keyless, graph-free proof of tier mechanics: the selector map + the ranking math are pure (monkeypatch _load_flow_risk + failure_rate, no graph/db); the marker functional test renders the conftest + runs a real `pytest -m smoke --collect-only` subprocess against a planted feature pair"

requirements-completed: [EXEC-01]

metrics:
  duration: ~45m
  tasks-completed: 2
  files-created: 3
  files-modified: 2
  completed-date: 2026-06-21
---

# Phase 7 Plan 02: Tier Selection + Risk-Based Ranking Summary

Made suites runnable BY TIER: the tag tiers (smoke/sanity/regression) resolve to a constant pytest-bdd `-m <tag>` selector behind a tampering-proof allow-list (full/risk-based → no filter, unknown → ValueError → 422), and the risk-based tier is computed dynamically by RANKING the graph's mined flows (each already carrying its real graph `risk_score` off `build_flows`) plus recent failure history, frozen-weighted and top-N capped, read through the exact `asyncio.wait_for` + honest-empty seam copied from `routers/scenarios._flow_risk_index` so it never hangs on a down/cold graph. The generated Playwright project now registers the tier markers in its conftest so `-m smoke` actually selects (not 0-collected / no warning). All proven keyless and graph-free.

## What Was Built

**Task 1 — Tier selectors + risk ranking over build_flows output (`123335f` test RED, `b79215a` feat GREEN):** Extended `app/services/exec_service.py` with `TIER_SELECTOR` (smoke/sanity/regression → `["-m","<tag>"]`; full → `[]`) and `resolve_tier` validating against the `TIER_SELECTOR` keys + `risk-based` allow-list (unknown → `ValueError` the router maps to 422; T-07-05) and returning a fresh copy of the constant tokens. Added the frozen `RiskRankWeights` dataclass (`[ASSUMED]` 0.6/0.4/top_n=10, mirroring `kg/risk.RiskWeights`), `failure_rate` (product_failure count / total over the last K distinct `test_runs` from `test_results`; empty history → 0.0 for all), `_load_flow_risk` (the `build_flows` RECORD LIST under `asyncio.wait_for(_RISK_TIMEOUT_S=3.0)` on BOTH `flows_source` and `build_flows`, honest-empty `[]` on graph down/slow/not-discovered — copied verbatim from `_flow_risk_index`), and `rank_risk_flows` (`combined = risk_weight*record["risk_score"] + failure_weight*failure_rate*100`, sorted desc, top-N). The docstring documents the D-03b sequencing (resolve while neo4j is UP, BEFORE the run phase; materialize the spec list; then run with neo4j off).

**Task 2 — Register tier markers in the generated project (`5e45485` feat):** Added `pytest_configure(config)` to `app/templates/conftest.py.j2` calling `config.addinivalue_line("markers", ...)` for smoke/sanity/regression — the marker home chosen so no new template file is needed and the registration rides the existing `_render_checked_py` ast-parse gate (the rendered conftest stays valid Python). The functional test renders the conftest through the real codegen gate (asserting all three markers declared) and runs a real `pytest -m smoke --collect-only` subprocess against a planted @smoke + untagged feature pair, asserting exactly the tagged scenario collects (untagged deselected) with no `PytestUnknownMarkWarning`.

## Verification Evidence

- `uv run pytest tests/unit/test_exec_tiers.py tests/unit/test_risk_ranking.py -q` → **17 passed in 4.82s** (selector map, allow-list 422 path, weighted-sum order, TOP_N truncation, cold-start pure-risk order, neo4j-down empty ranking, frozen-weights immutability).
- `uv run pytest tests/functional/test_codegen_markers.py -m functional -q` → **2 passed in 5.52s**; the `--collect-only` subprocess reports `1/2 tests collected (1 deselected)` with no `PytestUnknownMarkWarning`.
- Acceptance greps: `grep "build_flows\|wait_for" exec_service.py` shows the bounded read goes through `build_flows` under `asyncio.wait_for`; `grep "risk_score(" exec_service.py` finds **NO** direct call (exit 1 — the score is read off each record).
- `uv run pytest tests/unit/test_no_llm_in_worker.py -q` → **1 passed** (exec_service's new kg.flows/kg.reader imports do not trip the SC3 worker-plane gate — exec_service is the api producer, not the worker).
- Codegen render unchanged: `tests/functional/test_codegen.py -m "functional and not graph"` → **1 passed** (`_render_checked_py` still ast-parses the extended conftest).
- Full deterministic suite `pytest -m "not live_llm and not graph and not e2e and not functional"` → **237 passed, 115 deselected in 19.83s** — no regressions.
- `ruff check` clean on `exec_service.py` and `test_codegen_markers.py`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Functional collect-only assertion matched the wrong node-id form**
- **Found during:** Task 2 (first functional run)
- **Issue:** The test asserted the human scenario title ("A smoke scenario") appears in `pytest --collect-only -q` output; pytest-bdd names the collected node after the function (`test_a_smoke_scenario`), so the literal-title assertion failed even though selection worked correctly (`1/2 tests collected (1 deselected)`, no warning).
- **Fix:** Asserted the actual pytest-bdd node names (`test_a_smoke_scenario` present, `test_an_untagged_scenario` absent) plus the `1 deselected` line — the mechanism was already correct; only the assertion was wrong.
- **Files modified:** `apps/api/tests/functional/test_codegen_markers.py`
- **Commit:** `5e45485`

### Interpretation note (not a deviation)

The plan offered TWO marker-registration homes (conftest `pytest_configure` OR a rendered pytest.ini/pyproject markers entry). Chose conftest `pytest_configure` (the plan's first option) — it keeps the registration in the existing rendered file (no new template), mirrors the api's own marker block, and rides the `_render_checked_py` ast-parse gate. Per the plan's "Do NOT add a new template file if conftest can hold it."

## Authentication Gates

None — both tasks are proven keyless and graph-free (the selector map + ranking math are pure with monkeypatched seams; the marker test runs a `--collect-only` subprocess on planted features, no provider keys, no neo4j, no broker).

## Known Stubs

None that block EXEC-01. The ranked entries' `spec_path` (`features/<flow_id>.feature`) is the codegen feature-naming convention; the actual graph-driven feature materialization is owned by Plan 06's `generate_project` and the run-phase wiring (Plan 03+). The unit test asserts the field is present + truthy (the contract this plan owns); it is not a silent placeholder.

## Self-Check: PASSED

- Created files verified present: tests/unit/test_exec_tiers.py, tests/unit/test_risk_ranking.py, tests/functional/test_codegen_markers.py — all on disk.
- Modified files verified: app/services/exec_service.py (TIER_SELECTOR + rank_risk_flows), app/templates/conftest.py.j2 (pytest_configure) — present.
- Commits verified in git log: 123335f (test RED), b79215a (feat GREEN Task 1), 5e45485 (feat Task 2) — all present.
