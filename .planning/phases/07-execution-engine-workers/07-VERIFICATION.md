---
phase: 07-execution-engine-workers
verified: 2026-06-22T00:40:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Live LLM-generated suite end-to-end (generate -> approve -> codegen -> enqueue smoke tier -> live view -> artifacts -> history -> flaky -> kill mid-flight)"
    expected: "A real LLM-generated/approved suite runs through the engine with live progress, evidenced artifacts, history, flaky detection, and a graceful kill"
    why_human: "Needs provider keys + a real explored graph; the EXECUTION loop itself is keyless (SC3 = no LLM) and is fully verified — only the upstream generated-suite source is key-gated"
  - test: "GitHub Actions trigger reaching the local API"
    expected: "The workflow POSTs /api/executions to start a tier and polls status back, mapping passed->success / failed|killed->failure"
    why_human: "GitHub-hosted runners cannot reach local host port 8001; requires a self-hosted runner or tunnel on the dev box (documented in the workflow header)"
  - test: "Memory-fit 2-job concurrency under the 3GB WSL cap (SC3 parallel half)"
    expected: "Two browser flows progress concurrently under prefetch=2 with rabbitmq + worker + 2 Chromium + Postgres/Redis staying under 3GB (neo4j OFF)"
    why_human: "Requires host Vmmem/docker stats observation during a real concurrent run; the prefetch_count==2 CONFIG bound is automated, the memory-fit observation is not"
---

# Phase 7: Execution Engine & Workers Verification Report

**Phase Goal:** User runs tiered regression suites at scale — parallel, observable live, fully evidenced, and reproducible — locally, in Docker, and from CI.
**Verified:** 2026-06-22T00:40:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

The deterministic contract for all 5 success criteria is VERIFIED in code and proven green by an independently-run test suite. The phase is `human_needed` (not `passed`) ONLY because three Manual-Only items remain — all of them require external resources (provider keys, a self-hosted CI runner, host memory observation) and were explicitly scoped as Manual by the planner. None is a code gap. The defining hard invariant (SC3: NO LLM anywhere in the execution loop) is fully verified by both a real import-grep gate and direct source inspection.

### Observable Truths

| # | Truth (Success Criterion) | Status | Evidence |
|---|---------------------------|--------|----------|
| 1 | SC1 — run suites by tier (smoke/sanity/regression/full) + risk-based from flow risk + failure history | ✓ VERIFIED | `exec_service.TIER_SELECTOR` maps tag tiers to `["-m","<tag>"]`, full→`[]`; `resolve_tier` allow-lists (unknown→ValueError→422); `rank_risk_flows` ranks `kg_flows.build_flows` RECORDS (each carries graph `risk_score`) + `failure_rate` over `test_results` — grep `risk_score(` in exec_service.py = NO matches (ranks records, never computes). `test_exec_tiers`+`test_risk_ranking`+`test_codegen_markers` green. |
| 2 | SC2 — same suite runs locally / Docker / GitHub Actions with status reported back | ✓ VERIFIED (contract) | `.github/workflows/run-suite.yml` POSTs `/api/executions` to start + polls `GET /api/executions/{run_id}`, maps passed→0 / failed\|killed→1; NO pytest path in CI (D-08 single engine). Scoped `CI_TOKEN` Bearer from secrets, never echoed. `test_ci_workflow_contract` (5) green. Live GH-runner reach = Manual-Only. |
| 3 | SC3 — parallel via RabbitMQ stateless workers, NO LLM anywhere in the execution loop | ✓ VERIFIED | `test_no_llm_in_worker` scans worker pkg + worker_main for import-shaped LLM/langchain/langgraph/explorer/gateway tokens — green; direct grep confirms only docstring/comment mentions. `consumer.run_consumer` uses `connect_robust` + `set_qos(prefetch_count=2)` + durable `exec.jobs`; `job.run_flow_job` reuses `stability._run_spec_once` VERBATIM (no `create_subprocess_exec`/`shell=True`/`pytest.main` in worker). `test_worker_consume` proves enqueue→consume→subprocess→result row + prefetch==2 against the REAL queue-profile broker. Memory-fit concurrency = Manual-Only. |
| 4 | SC4 — per-step screenshots/video/console+network logs on filesystem, paths in Postgres; history with trends/durations/flaky | ✓ VERIFIED | `job._capture_args`: `--screenshot=on`+`--tracing=on` always, `--video=retain-on-failure`; layout `run_dir(run_id)/<flow_id>/`; `_discover_artifacts` records run-relative multi-segment paths (no binaries) into `TestArtifact`. Pure `classify_retry` (pass-on-retry→flaky, all-fail→product_failure). `exec_history` has pass_rate_trend/durations_by_flow/flaky_leaderboard/list_runs/get_run_status (real SQLAlchemy 2.0). Migration 0007 (down_revision='0006') applied → `alembic current` = `0007 (head)`. `test_flaky_classifier`+`test_artifact_capture`+`test_exec_history` green. |
| 5 | SC5 — live per-test view + kill switch; two consecutive runs vs reset target are identical | ✓ VERIFIED | Per-test Redis→SSE: `progress.publish_test_event` (absolute counters from DB aggregate) → `executions.py /{run_id}/events` (EventSourceResponse + current-counter reconnect snapshot). Graceful kill: `kill_run` sets `run:{run_id}:kill` + `queue.purge` — NO os.kill/SIGKILL (grep = none); worker drains remaining flows to `aborted`. Determinism: `test_determinism` runs the planted spec twice via `_run_spec_once` with `reset_target.py` between, compares status/verdict (not timing). `test_live_exec`+`test_kill_drain`+`test_determinism` green. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/services/worker/consumer.py` | aio-pika robust consumer, prefetch=2 | ✓ VERIFIED | connect_robust + set_qos(2) + durable exec.jobs + poison ack-drop |
| `app/services/worker/job.py` | per-flow runner, retry loop, capture, kill drain | ✓ VERIFIED | reuses `_run_spec_once`; MAX_ATTEMPTS=3; capture flags; `_is_killed` between attempts; `_abort_flow`→aborted |
| `app/services/worker/classifier.py` | pure flaky-vs-product classifier | ✓ VERIFIED | stdlib-only, no I/O; pass-on-retry→flaky, all-fail→product_failure |
| `app/services/worker/progress.py` | per-test Redis publish, absolute counters | ✓ VERIFIED | build_counters from test_runs row + test_results aggregate; shared get_redis() |
| `app/worker_main.py` | worker entrypoint, no neo4j/checkpointer/LLM | ✓ VERIFIED | init_redis + run_consumer only |
| `app/services/exec_service.py` | producer, tiers, risk ranking, kill_run | ✓ VERIFIED | TIER_SELECTOR, rank over build_flows, enqueue persistent, kill flag+purge |
| `app/services/exec_history.py` | trends/durations/flaky/list/status queries | ✓ VERIFIED | real SQLAlchemy 2.0 aggregates |
| `app/routers/executions.py` | single owner of /api/executions | ✓ VERIFIED | one handler per (method,path); SSE/kill/multi-segment artifact guard; cookie-OR-ci_token gate |
| `alembic/versions/0007_execution_history.py` | test_runs/test_results/test_artifacts, down_revision 0006 | ✓ VERIFIED | three tables, run-relative path col (no binary); DB at 0007 (head) |
| `.github/workflows/run-suite.yml` | CI start+poll, scoped token | ✓ VERIFIED | POST start + poll status, no pytest, token never echoed |
| `infra/docker-compose.yml` worker+rabbitmq | queue profile, mem_limit, prefetch | ✓ VERIFIED | worker profiles:[queue], mem_limit 768m, same image, `python -m app.worker_main`; rabbitmq 512m healthcheck |
| `apps/web` executions UI | launcher + history + live view + run detail | ✓ VERIFIED | page.tsx, [runId]/page.tsx, 4 components, lib/api/executions.ts, sidebar entry; tsc clean, 8/8 e2e green |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| exec_service.enqueue_jobs | RabbitMQ exec.jobs | aio-pika default_exchange.publish PERSISTENT | ✓ WIRED | proven by real-broker round-trip test |
| consumer.run_consumer | job.run_flow_job | queue.iterator + message.process | ✓ WIRED | test_worker_consume lands a test_results row |
| job.run_flow_job | subprocess pytest | stability._run_spec_once (verbatim) | ✓ WIRED | extra_args carries capture flags; no shell |
| job.run_flow_job | Postgres | TestResult + TestArtifact in fresh SessionLocal | ✓ WIRED | run-relative paths, inferred kinds |
| worker progress | live UI | Redis exec:{run_id} → executions.py SSE → executions.ts | ✓ WIRED | test_live_exec forwards events in order |
| executions.py kill | worker drain | Redis run:{run_id}:kill + queue.purge | ✓ WIRED | test_kill_drain: drained→aborted, queue purged, no SIGKILL |
| CI workflow | engine | POST/GET /api/executions (same path) | ✓ WIRED (contract) | live reach is Manual-Only |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| executions live view | counters/per-test events | Redis SSE ← worker publish ← test_results aggregate | Yes (real DB aggregate) | ✓ FLOWING |
| executions history table | runs list | GET /api/executions ← exec_history.list_runs ← test_runs | Yes | ✓ FLOWING |
| run detail page | per-flow results | GET /api/executions/{run_id} ← get_run_status | Yes | ✓ FLOWING |
| trend charts | pass-rate/duration series | deriveTrends(runs) client-side from server runs list | Yes (derived from authoritative runs) | ✓ FLOWING (see note) |

Note: `exec_history.pass_rate_trend/durations_by_flow/flaky_leaderboard` are implemented but not wired to a dedicated route; the UI derives trends client-side from the authoritative `list_runs` data (Plan 04 documented deviation). Trends are observable and server-authoritative — not a hollow prop.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Deterministic + functional suite | `uv run pytest -m "not live_llm and not e2e and not graph" -q` | 340 passed, 44 deselected (182s) | ✓ PASS |
| NO-LLM grep gate over real worker source | (within suite) test_no_llm_in_worker | green | ✓ PASS |
| Real-broker round-trip + prefetch==2 | (within suite) test_worker_consume | green (broker up) | ✓ PASS |
| Kill drain + queue.purge + no-SIGKILL | (within suite) test_kill_drain | green | ✓ PASS |
| Two-runs-identical vs reset target | (within suite) test_determinism | green (SauceDemo up) | ✓ PASS |
| Migration head reachable | `uv run python -m alembic current` | 0007 (head) | ✓ PASS |
| Frontend type check | `npx tsc --noEmit` | exit 0 | ✓ PASS |
| Executions e2e | `npx playwright test tests/e2e/executions.spec.ts` | 8 passed (30s) | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes declared or conventional for this phase. Verification is via the pytest functional suite (run above) and the Playwright e2e spec — both executed independently. N/A.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| EXEC-01 | 07-02 | tier suites + risk-based | ✓ SATISFIED | Truth 1 |
| EXEC-02 | 07-05 | local/Docker/CI parity + GH trigger | ✓ SATISFIED (contract; live=Manual) | Truth 2 |
| EXEC-03 | 07-01 | RabbitMQ parallel workers, no LLM | ✓ SATISFIED | Truth 3 |
| EXEC-04 | 07-03 | per-step artifacts, paths in Postgres | ✓ SATISFIED | Truth 4 |
| EXEC-05 | 07-03 | history trends/durations/flaky | ✓ SATISFIED | Truth 4 |
| EXEC-06 | 07-04 | live view + kill switch | ✓ SATISFIED | Truth 5 |

No orphaned requirements — all six EXEC IDs are claimed by plans and verified.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | — | — | No TBD/FIXME/XXX/HACK/PLACEHOLDER debt markers in any phase-7 service file. The two grep hits in `gates/selector_gate.py` are Playwright selector method names (Phase-6), not debt markers. |

Gated-dependency check: exactly two new dependencies added in the whole phase — `aio-pika==9.6.*` (commit c74b49a) and `recharts@^3.8.1` (commit bc47b9b), both the sanctioned/locked-stack additions. No other package crept in. Clean.

### Human Verification Required

### 1. Live LLM-generated suite end-to-end

**Test:** Set provider keys; generate + approve scenarios + codegen; enqueue a `smoke` tier run; watch the live view; confirm artifacts + history + flaky detection; kill a run mid-flight.
**Expected:** The engine runs a real generated suite with live progress, evidence, history, and a graceful kill.
**Why human:** Needs provider keys + a real explored graph. The execution loop itself is keyless (SC3 = no LLM) and is fully verified; only the upstream generated-suite source is key-gated.

### 2. GitHub Actions trigger reaching the local API

**Test:** Configure a self-hosted runner (or tunnel) on the dev box; trigger `run-suite.yml`; confirm it starts a tier via POST /api/executions and reports status back.
**Expected:** Workflow starts a run, polls to terminal, maps passed→success / failed|killed→failure.
**Why human:** GitHub-hosted runners cannot reach local host port 8001; requires a self-hosted runner or tunnel (documented in the workflow header).

### 3. Memory-fit 2-job concurrency under the 3GB cap (SC3 parallel half)

**Test:** `docker stats` during a `prefetch=2` run with neo4j OFF — confirm two flows progress concurrently and rabbitmq + worker + 2 Chromium + Postgres/Redis stay under the cap.
**Expected:** Two concurrent flows; total memory under 3GB.
**Why human:** Requires host Vmmem observation during a real concurrent run. The prefetch_count==2 CONFIG bound is automated (test_worker_consume); the memory-fit observation is not.

### Gaps Summary

No gaps. Every success criterion's deterministic contract is implemented and proven green by an independently-run test suite (340 passed) plus a frontend tsc + 8/8 Playwright e2e. The single hard invariant (SC3 NO LLM in the execution loop) is verified twice — by a real import-grep gate and by direct source inspection of every worker-plane file. The functional tests that require live infrastructure (real RabbitMQ queue-profile broker, SauceDemo reset target) executed and passed during verification, so the queue round-trip, prefetch bound, kill drain/purge, artifact capture, and two-runs-identical determinism are all proven against real infra, not mocks.

Status is `human_needed` solely because three Manual-Only items remain — each requires an external resource (provider keys, a self-hosted CI runner, host memory observation) and was explicitly scoped as Manual by the planner. They are not code gaps and do not block the deterministic contract.

---

_Verified: 2026-06-22T00:40:00Z_
_Verifier: Claude (gsd-verifier)_
