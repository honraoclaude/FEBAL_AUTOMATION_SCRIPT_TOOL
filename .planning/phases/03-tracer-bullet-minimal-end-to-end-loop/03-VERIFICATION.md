---
phase: 03-tracer-bullet-minimal-end-to-end-loop
verified: 2026-06-15T03:30:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/4
  gaps_closed:
    - "POST /explore against registered SauceDemo produces real Page/NavigatesTo nodes in Neo4j (SC1)"
  gaps_remaining: []
  regressions: []
gaps: []
deferred: []
human_verification:
  - test: "Full live-LLM end-to-end generation: POST /generate-bdd + /generate-scripts against a real provider, then /execute the generated spec."
    expected: "One valid Gherkin scenario + one ast-parseable runnable Playwright spec are produced by a real LLM call (not the deterministic template/mock path), and the spec executes to a result row."
    why_human: "Requires real Anthropic/OpenAI provider keys and spend; the test (test_generation.py::test_generate_bdd_and_scripts_end_to_end) is marked live_llm+graph and is the documented Manual-Only item. Its skip/absence is EXPECTED and is not a gap. The gateway path itself is verified by deterministic unit tests (gateway-only, validate-before-write, ast.parse-before-write)."
  - test: "Host memory fit under the 3 GB WSL cap while the graph profile is active (web stopped, neo4j up)."
    expected: "postgres + redis + api + neo4j(1g) + saucedemo stays under 3 GB; no OOM-kill of the WSL VM during exploration."
    why_human: "Memory pressure / OOM behavior on the specific Windows 11 + Docker Desktop host is an environmental property not assertable from code. graph_mode up/down ran cleanly (exit 0, neo4j healthy) in this verification, which is consistent with the cap holding."
---

# Phase 3: Tracer Bullet — Minimal End-to-End Loop Verification Report

**Phase Goal:** One thin slice of the entire pipeline runs end-to-end against SauceDemo, proving the loop before any engine is built deep.
**Verified:** 2026-06-15T03:30:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure (commit 19f2439 fixing the SC1 blocker)

## Re-Verification Summary

The prior verification (2026-06-15T01:10:00Z, gaps_found 3/4) found SC1 a 🛑 BLOCKER:
POST /explore reported `passed` but wrote ZERO Page/NavigatesTo nodes to Neo4j —
the write used `session.run()` auto-commit without consuming the result, so the
MERGE never durably committed from the long-lived lifespan driver, and the run
flipped to `passed` regardless, masking the failure.

Commit **19f2439** (`apps/api/app/services/explorer.py` + `apps/api/app/core/neo4j_driver.py`)
addressed three real defects:

1. **Uncommitted write →** `write_page_graph` now uses `session.execute_write(_write)`
   (a MANAGED transaction that commits on success) and `RETURN count(*) AS edges`;
   `run_explore` raises `RuntimeError("explore persisted no NavigatesTo edge to Neo4j")`
   when `edges < 1`, flipping the run to `failed`. A no-op write can no longer report
   `passed`.
2. **Defunct pooled connection →** the lifespan driver pooled to a prior neo4j
   container; graph_mode recreates neo4j under a running api. Added
   `liveness_check_timeout=0` so the driver liveness-checks idle connections and
   re-dials the recreated server.
3. **Stale run_id →** URL-keyed Page nodes are MERGE'd, so `run_id` is now `SET` on
   EVERY run (not just `ON CREATE`); the per-run query now finds the latest run's nodes.

This verifier **independently re-confirmed** the fix against a live graph_mode stack
(web stopped, neo4j healthy, api restarted so uvicorn loaded the fixed code — verified
present inside the running container via `grep execute_write|liveness_check_timeout`).

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria — the contract)

| # | Truth (Success Criterion) | Status | Evidence |
|---|---------------------------|--------|----------|
| 1 | POST /explore produces real Page/NavigatesTo nodes in Neo4j (SC1) | ✓ VERIFIED (was FAILED) | `test_explore.py -m graph` → **2 passed** (the exact test that failed before). Direct Neo4j query after the run: a real edge `(:Page {url:http://saucedemo/inventory.html})-[:NavigatesTo]->(:Page {url:http://saucedemo/inventory-item.html?id=4})` tagged with a CURRENT run_id (`3cd2b1ba…`, not the prior stale `b02a63ce`). Durable commit confirmed (queried from a separate process after the writer exited). Read-back guard verified in code: `edges < 1` → `RuntimeError` → status `failed`. |
| 2 | POST /generate-bdd + /generate-scripts produce one Gherkin scenario + one runnable Playwright spec from the graph (SC2) | ✓ VERIFIED (no regression) | generation.py routes both steps through `llm_gateway.complete()`, validates Gherkin with gherkin-official before write, Jinja2 template owns spec structure + selectors; deterministic unit tests green in graph (5 passed) + default (105 passed) suites. Real-LLM end-to-end is the documented Manual-Only/live_llm item (expected, not a gap). |
| 3 | POST /execute runs the spec → result row in Postgres, retrievable via GET /executions (SC3) | ✓ VERIFIED (no regression) | execution.py runs `uv run pytest <spec>` via create_subprocess_exec (argv list, no shell, never pytest.main); GET /executions/{run_id} resolves by run_id. test_execute.py graph leg green within the 5-passed graph run. |
| 4 | All 10 REST endpoints exist (real + honest 501 stubs) + queue schemas in shared/events/ (SC4) | ✓ VERIFIED (no regression) | All 10 PLAT-02 paths present; 5 stubs return 501 with documented OpenAPI contracts; shared/events has ExploreJob/ExecuteJob/RunStatusEvent (Pydantic v2), no broker import (D-05). Default gate 105 passed covers these. |

**Score:** 4/4 truths verified

### Required Artifacts (delta from prior verification)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apps/api/app/services/explorer.py` | Deterministic crawl, single decrypt surface, parameterized Cypher MERGE that DURABLY commits, read-back guard | ✓ VERIFIED (was STUB-LIKE) | `write_page_graph` now uses `session.execute_write(_write)` (managed tx) + `RETURN count(*)`; `run_explore` raises when `edges < 1` so a 0-node write → `failed`. run_id `SET` on every run. No LLM, get_decrypted_credentials only, parameterized MERGE, own SessionLocal, T-03-09 guard all intact. No debt markers. |
| `apps/api/app/core/neo4j_driver.py` | Lifespan driver (lazy, single pool) tolerant of neo4j container recreation | ✓ VERIFIED | `liveness_check_timeout=0` added so the driver re-dials a recreated neo4j (graph_mode) instead of reusing defunct pooled connections. Lazy connect preserved (api boots when neo4j down, A6). No debt markers. |

All other artifacts from the prior verification (routers, generation.py, execution.py,
templates, stubs, schemas, run_service, models/migration 0004, shared/events,
graph_mode.py, compose neo4j trim) remain ✓ VERIFIED — see prior report; no changes,
no regression observed in the re-run suites.

### Key Link Verification (delta)

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| explorer.py | Neo4j | write_page_graph (managed execute_write, parameterized MERGE) | ✓ WIRED (was NOT COMMITTING) | Edge now durably lands: direct Neo4j query confirms a current-run NavigatesTo edge; the 0-node path now fails the run. |

All other key links remain ✓ WIRED (explore→run_explore BackgroundTask, generation→gateway,
execute→subprocess, GET /executions→run_service).

### Data-Flow Trace (Level 4) (delta)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| /explore → Neo4j | Page/NavigatesTo nodes | explorer.write_page_graph (live crawl, managed tx) | ✓ Yes (real SauceDemo URLs, current run_id, queried from a separate process) | ✓ FLOWING (was DISCONNECTED) |

/execute → Postgres and GET /executions remain ✓ FLOWING.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SC1 graph test (the previously-failing test) | `uv run pytest tests/functional/test_explore.py -m graph -q` | **2 passed in 23.07s** | ✓ PASS |
| No regression — all graph tests | `uv run pytest -m "graph and not live_llm" -q` (graph_mode) | **5 passed, 108 deselected** | ✓ PASS |
| No regression — default fast gate | `uv run pytest -m "not live_llm and not graph" -q` (web up, neo4j down) | **105 passed, 8 deselected** | ✓ PASS |
| Durable commit (independent) | Direct Bolt query post-run: `MATCH (a:Page)-[:NavigatesTo]->(b:Page) RETURN ...` | 1 current-run edge with real SauceDemo URLs (`inventory.html → inventory-item.html?id=4`), run_id `3cd2b1ba…` | ✓ PASS |
| Fix present in running container | `docker exec ... grep execute_write\|liveness_check_timeout` | both present in container's explorer.py / neo4j_driver.py | ✓ PASS |
| graph_mode choreography | `graph_mode.py up` / `down` | exit 0; web stopped→neo4j healthy→web restored | ✓ PASS |
| Stack restored (memory-safe) | `docker ps` | web healthy, neo4j stopped | ✓ PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` declared for this phase; the phase's
runnable checks are the pytest graph/default suites, executed above.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| explorer.py | — | (none) | — | Prior blocker (`session.run()` uncommitted write) is RESOLVED. No TBD/FIXME/XXX/HACK markers in either changed file. |

### Human Verification Required

Two non-blocking, planned Manual-Only items remain (carried, not gaps):

1. **Full live-LLM end-to-end generation** — POST /generate-bdd + /generate-scripts
   against a real provider, then /execute the generated spec. Requires real provider
   keys/spend; the test is marked `live_llm+graph` and its skip is EXPECTED. The gateway
   path itself is verified by deterministic unit tests. Excluded with `not live_llm`.
2. **Host memory fit under the 3 GB WSL cap** while the graph profile is active —
   environmental property; graph_mode up/down ran cleanly (exit 0, neo4j healthy),
   consistent with the cap holding.

These are the documented Phase-3 Manual-Only items, present since planning — they do
not block the phase goal. Status is `passed` with these surfaced for human awareness.

### Gaps Summary

**No gaps remain.** The SC1 blocker is genuinely fixed and independently re-confirmed:
POST /explore now durably writes real Page/NavigatesTo nodes to Neo4j for the current
run_id (verified by the previously-failing graph test passing AND by a direct cross-process
Neo4j query showing a real-URL edge tagged with a fresh run_id), and a zero-node write
now flips the run to `failed` instead of masquerading as `passed`. SC2, SC3, and SC4
remain verified with no regression (5 graph-marked tests pass under graph_mode; 105
default-gate tests pass with neo4j down). The tracer loop is now proven end-to-end across
all four success criteria.

The default memory-safe stack (web up, neo4j stopped) was restored before finishing.

---

_Verified: 2026-06-15T03:30:00Z_
_Verifier: Claude (gsd-verifier)_
