---
phase: 07-execution-engine-workers
plan: 03
subsystem: api
tags: [execution-engine, artifacts, flaky-classifier, retry-loop, exec-history, route-consolidation, ci-token-bearer, exec-04, exec-05, keyless]

# Dependency graph
requires:
  - phase: 07-execution-engine-workers
    plan: 01
    provides: "worker/job.py single-attempt runner + TestRun/TestResult/TestArtifact models + exec_service.create_test_run/enqueue_jobs; stability._run_spec_once subprocess primitive; workspaces.run_dir/spec_path"
  - phase: 07-execution-engine-workers
    plan: 02
    provides: "exec_service.resolve_tier (allow-list) + rank_risk_flows (risk-based ranking)"
  - phase: 07-execution-engine-workers
    plan: 05
    provides: "settings.ci_token (the scoped start+poll credential definition the I1 bearer check enforces)"
  - phase: 03-tracer-bullet-minimal-end-to-end-loop
    provides: "routers/executions.py existing GET ''/GET /{run_id}; run_service.get_status_by_run_id; routers/explore.py 202 shape"
provides:
  - "worker/classifier.py: pure classify_retry (passes-on-retry->flaky; all-fail->product_failure; no I/O/LLM)"
  - "worker/job.py: 2x retry loop (MAX_ATTEMPTS=3, break on exit 0) + per-step capture flags (--screenshot=on/--tracing=on/--video=retain-on-failure/--output) + concrete on-disk layout run_dir(run_id)/<flow_id>/ + run-relative multi-segment TestArtifact paths (kind screenshot|trace|video inferred)"
  - "stability._run_spec_once gains optional extra_args (constant flags appended to the argv list, still no shell)"
  - "exec_history.py: pass_rate_trend / durations_by_flow / flaky_leaderboard / list_runs / get_run_status (SQLAlchemy 2.0 select/scalars)"
  - "exec_service.resolve_flows_for_tier: per-flow enqueue for all tiers (tag/full from approved scenarios keyless; risk-based from rank_risk_flows BEFORE the run phase)"
  - "routers/executions.py SINGLE owner of /api/executions: POST '' 202 round-trip, GET '' -> TestRunResponse[], GET '/{run_id}' -> status+results summary, legacy RunStatus namespaced at '/{run_id}/legacy-status' (one handler per (method,path), T-07-18)"
  - "I1: executions router gate accepts cookie OR scoped ci_token bearer (hmac.compare_digest, never logged)"
affects: [07-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure retry classifier (classifier.py) mirrors kg/risk.py: stdlib-only, no I/O, table-testable; defensive-copies exit_codes; verdict vocab passed|flaky|product_failure (aborted is Plan 04's kill path)"
    - "Worker 2x retry loop: MAX_ATTEMPTS=3 (original + 2), break on exit 0, collect per-attempt exit codes -> classify_retry; ONE TestResult + one TestArtifact per captured file in a FRESH SessionLocal (Pitfall 2)"
    - "Concrete on-disk artifact layout (B2): out_dir = run_dir(run_id)/<flow_id>; pytest-playwright --output writes per-test subdirs UNDER it; TestArtifact.path = file.relative_to(run_dir(run_id)).as_posix() (run-relative, multi-segment, never a basename/absolute); kind inferred from suffix (*.png->screenshot, trace*.zip->trace, *.webm->video); NO console_log/network_log kinds (W4 (a): inside the trace)"
    - "Capture flags appended to stability._run_spec_once via an optional extra_args param (the create_subprocess_exec call stays in the ONE reused primitive — argv list, no shell, run_id-derived output dir T-07-11)"
    - "SINGLE-owner /api/executions (B1): executions.py owns POST '' + GET '' + GET '/{run_id}'; the Phase-3 RunStatus poll surface is NAMESPACED at GET '/{run_id}/legacy-status' so there is EXACTLY ONE handler per (method,path) (test introspects app.routes, T-07-18); execute.py keeps only POST /api/execute"
    - "Per-flow enqueue for ALL tiers (RESEARCH Open Q3): resolve_flows_for_tier returns one job per distinct approved-scenario flow_id (tag/full, Postgres-only keyless) or per top-N ranked flow (risk-based, neo4j UP before the run phase, D-03b)"
    - "I1 dual-credential router gate: require_user_or_ci_token accepts the access_token cookie OR Authorization: Bearer == settings.ci_token (hmac.compare_digest, start+poll scope); the token is never echoed/logged (T-07-07)"

key-files:
  created:
    - apps/api/app/services/worker/classifier.py
    - apps/api/app/services/exec_history.py
    - apps/api/tests/unit/test_flaky_classifier.py
    - apps/api/tests/functional/test_artifact_capture.py
    - apps/api/tests/functional/test_exec_history.py
    - apps/api/tests/functional/test_execute_tier.py
  modified:
    - apps/api/app/services/worker/job.py
    - apps/api/app/services/stability.py
    - apps/api/app/services/exec_service.py
    - apps/api/app/routers/executions.py
    - apps/api/tests/functional/test_worker_consume.py

key-decisions:
  - "Capture flags are appended to stability._run_spec_once via a NEW optional extra_args param rather than re-pasting create_subprocess_exec into job.py — keeps the subprocess-discipline (argv list, no shell) in the ONE battle-tested primitive (the 07-01 verbatim-reuse + DRY directive); the flags are CONSTANTS + a run_id-derived output dir, never raw client input (T-07-11)"
  - "Legacy Phase-3 RunStatus poll surface NAMESPACED at GET /{run_id}/legacy-status (the plan's offered option) — the Phase-7 history surface (status+results summary) takes the bare GET /{run_id}; this yields EXACTLY ONE handler per (method,path) (the alternative — extending the bare /{run_id} — would have dropped the legacy single-spec poll path the explore/execute flow may still use)"
  - "resolve_flows_for_tier sources tag/full flows from DISTINCT approved-scenario flow_ids (Postgres-only, keyless) so smoke/sanity/regression/full never touch the graph; risk-based delegates to rank_risk_flows (graph UP before the run phase, D-03b). An empty job list is a valid no-flow run (still 202), not an error"
  - "I1 bearer is wired as the ROUTER-LEVEL gate (require_user_or_ci_token: cookie OR ci_token bearer) rather than a per-route dep — the router-level Depends(get_current_user) alone would have blocked a bearer-only CI request on the POST; the combined gate keeps every route auth-gated (unauth -> 401) while letting the CI start/poll path authenticate with the scoped token (hmac.compare_digest, never logged)"
  - "Artifact kind enum kept screenshot|trace|video ONLY (W4 (a)); _kind_for returns None for any other file (and the file is NOT recorded) so a stray pytest-playwright artifact never invents a console_log/network_log kind"
  - "GET '/{run_id}' returns a plain dict (status + tier + counters + per-flow results list) not a fixed response_model — the results summary shape is Phase-7-internal and the dashboard/Plan-04 consumer reads it directly; TestRunResponse is used for the GET '' list"

patterns-established:
  - "A tier run is now a real evidenced execution: POST /api/executions resolves the tier, creates a test_run, enqueues per-flow jobs (202+run_id); the worker runs each flow with the 2x retry loop + per-step capture, classifies flaky-vs-product, and persists the verdict + run-relative artifact paths; GET /api/executions[/{run_id}] reads the history/status back — one auth-gated owner"
  - "Loop-bound shared-client hygiene for functional tests that drive run_flow_job directly: share a module-scoped event loop AND reset the module-level engine pool + Redis client (dispose engine; drop the Redis ref without aclose) at setup/teardown so cross-module loops never reuse a handle from a closed loop"

requirements-completed: [EXEC-04, EXEC-05]

metrics:
  duration: ~2h
  tasks-completed: 2
  files-created: 6
  files-modified: 5
  completed-date: 2026-06-21
---

# Phase 7 Plan 03: Evidenced + Historied Tier Runs Summary

Made every run fully EVIDENCED and HISTORIED. The worker job now runs each flow with a 2× retry loop (original + 2 retries, break on a clean exit) feeding a PURE flaky-vs-product classifier (passes-on-a-retry → flaky/infra; all-attempts-fail → product_failure), captures per-step artifacts via the pytest-playwright CLI flags (screenshots + trace always, video on failure only) into the concrete on-disk layout `workspaces/<run_id>/<flow_id>/`, and records ONE `test_results` row plus one `test_artifacts` row per captured file with a RUN-RELATIVE multi-segment path (kind screenshot|trace|video — never a binary in Postgres, never a bare basename). Execution history is exposed via `exec_history.py` (pass-rate trend, per-flow durations, flaky leaderboard, run list/status). And `routers/executions.py` is now the SINGLE owner of `/api/executions` — an auth-gated `POST {tier}` resolves the tier (incl. risk-based), creates a `test_run`, enqueues per-flow jobs and returns `202 + run_id`; the reconciled `GET ""`/`GET /{run_id}` return history/status with EXACTLY ONE handler per (method, path) (the legacy Phase-3 `RunStatus` poll surface namespaced at `/{run_id}/legacy-status`), and the I1 scoped `ci_token` bearer is wired into the router gate. All proven keyless (planted spec, neo4j off).

## What Was Built

**Task 1 — Pure flaky classifier + worker retry loop + per-step capture (`9508892` test RED, `f2f72e9` classifier GREEN, `a1aad58` retry+capture GREEN):**
- `worker/classifier.py`: `classify_retry(exit_codes)` — stdlib-only, no I/O/LLM (mirrors kg/risk.py); any-pass → `flaky` if retried else `passed`, all-fail → `product_failure`; returns `{verdict, attempts, passed, exit_codes}` with a defensive-copied list.
- `worker/job.py`: `MAX_ATTEMPTS=3` retry loop (break on exit 0) collecting per-attempt exit codes → `classify_retry`; the per-attempt argv appends `--screenshot=on --tracing=on --video=retain-on-failure --output <out_dir>` where `out_dir = run_dir(run_id)/<flow_id>` (B2); after the loop, `_discover_artifacts` walks `out_dir.rglob("*")`, infers the kind from the suffix (`*.png`/`trace*.zip`/`*.webm`), and records each file's `file.relative_to(run_dir(run_id)).as_posix()` path; ONE `TestResult` + the `TestArtifact` rows are written in a FRESH `SessionLocal` (Pitfall 2).
- `stability._run_spec_once` gained an optional `extra_args` param so the capture flags ride the ONE reused subprocess primitive (argv list, no shell).
- `tests/unit/test_flaky_classifier.py` (the full verdict table, keyless, pure) + `tests/functional/test_artifact_capture.py` (planted run: passing → screenshot+trace+no-video, run-relative multi-segment paths; failing → video; no binary in DB; no console/network kinds).

**Task 2 — Execution-history queries + consolidate /api/executions (`8dd4b83` test RED, `1a7dcb8` GREEN):**
- `exec_history.py`: `pass_rate_trend` (per-day `sum(passed)/sum(total)` via `date_trunc`), `durations_by_flow` (avg/max `duration_ms`), `flaky_leaderboard` (flaky-verdict count desc), `list_runs` (newest-first), `get_run_status` (run row + per-flow results summary; None → 404) — all SQLAlchemy 2.0 select/scalars.
- `exec_service.resolve_flows_for_tier`: per-flow enqueue for all tiers (tag/full from DISTINCT approved-scenario flow_ids, Postgres-only/keyless; risk-based from `rank_risk_flows`).
- `routers/executions.py` consolidated: `POST ""` (202) resolves the tier (422 on unknown) → `resolve_flows_for_tier` → `create_test_run` → `enqueue_jobs` → `{run_id, status}`; `GET ""` → `TestRunResponse[]` via `exec_history.list_runs`; `GET "/{run_id}"` → status+results via `get_run_status` (404 on None); the legacy `RunStatus` poll surface NAMESPACED at `GET "/{run_id}/legacy-status"`. I1: the router gate `require_user_or_ci_token` accepts the access_token cookie OR `Authorization: Bearer == settings.ci_token` (hmac.compare_digest, never logged).
- `tests/functional/test_exec_history.py` (seeded-row aggregates) + `tests/functional/test_execute_tier.py` (in-process: one handler per (method,path) under /api/executions, no /executions route in execute.py, captured per-flow enqueue; live HTTP: unauth POST → 401, authed POST smoke → 202+run_id, GET status, bogus → 404).

## Verification Evidence

- `uv run pytest tests/unit/test_flaky_classifier.py tests/unit/test_no_llm_in_worker.py -q` → **11 passed** (classifier table + SC3 NO-LLM gate green over the extended worker source).
- `uv run pytest tests/functional/test_artifact_capture.py -m functional -q` → **2 passed**: a passing planted run records screenshot+trace artifacts (run-relative paths containing the `<flow_id>/` segment, files on disk) and NO video; a failing run (3 attempts, product_failure) records a video.
- `uv run pytest tests/functional/test_exec_history.py tests/functional/test_execute_tier.py -m functional -q` → **7 passed**: history aggregates over seeded rows; one handler per (method,path) under /api/executions; no /executions route in execute.py; unauth POST → 401; authed POST smoke → 202+run_id; GET status; bogus → 404; captured per-flow enqueue.
- Acceptance greps: `grep -n "retain-on-failure|--tracing=on|--screenshot=on|--output" worker/job.py` finds all four flags; `grep -rn "shell=True" worker/` → NONE; `grep -n "resolve_tier|enqueue_jobs|resolve_flows_for_tier" executions.py` shows the tier round-trip lives in executions.py; the in-process test confirms execute.py registers NO /executions route; `grep -n "Depends(require_user_or_ci_token)|ci_token" executions.py` confirms the auth gate + the bearer wiring.
- Full regression `uv run pytest -m "not live_llm and not graph and not e2e" -q` → **333 passed, 44 deselected** (up from 07-05's 314; the new classifier/history/capture/tier tests + the hardened 07-01 round-trip, no regressions).
- `ruff check` clean on all created/modified files.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The running api container image lacked aio-pika**
- **Found during:** Task 2 (live HTTP round-trip — the POST route 404'd, then the container crashed on restart).
- **Issue:** `routers/executions.py` (registered in main.py) now imports `exec_service`, which imports `aio_pika`. The running `infra-api` image was built BEFORE 07-01 added aio-pika to `pyproject.toml`/`uv.lock`, so the container crashed at startup with `ModuleNotFoundError: No module named 'aio_pika'`. (Pre-07-03 the api never imported `exec_service` at startup — only host tests did — so the stale image had gone unnoticed.)
- **Fix:** Rebuilt the api image (`docker compose build api` — `uv sync --frozen` installs the already-locked, already-approved aio-pika 9.6.2) and recreated the container with the correct `--env-file ../.env`. No new package — the dependency was approved + locked in 07-01; only the image was stale.
- **Files modified:** none (image rebuild only).
- **Commit:** n/a (infra rebuild; the code change that exposed it is `1a7dcb8`).

**2. [Rule 1 - Bug] Loop-bound shared-client teardown across functional test modules**
- **Found during:** the full-suite regression run.
- **Issue:** `run_flow_job` touches the module-level SQLAlchemy engine pool AND the module-level Redis client, both bound to the running event loop. pytest-asyncio (auto mode) opens a fresh loop per test/module; with the new functional tests added to the suite, `test_worker_consume.py` (07-01, unmodified) began failing with `RuntimeError: Event loop is closed` when a prior module's run had populated those shared clients on a now-closed loop. The classifier/history assertions themselves were green — it was a cross-module teardown artifact, not a logic regression (each file passed in isolation).
- **Fix:** the tests that drive `run_flow_job` directly (`test_artifact_capture.py`, and the hardened `test_worker_consume.py`) share a module-scoped event loop and reset BOTH shared clients at setup/teardown — `await engine.dispose()` and drop the Redis module ref (`redis_client._client = None`, NOT `aclose`, which would touch the dead loop) so the next test re-opens fresh on its own loop. In production the api owns its own long-lived engine/client via the lifespan — this is purely a test-isolation concern.
- **Files modified:** `apps/api/tests/functional/test_artifact_capture.py`, `apps/api/tests/functional/test_worker_consume.py`.
- **Commit:** `65a360f`.

### Interpretation note (not a deviation)

The plan's acceptance grep `grep -rn "/executions" app/routers/execute.py` will surface TWO matches — both in COMMENTS/docstrings (lines describing that the poll surface lives at `GET /api/executions/{run_id}`), not route definitions. The substantive single-owner guarantee is asserted by `test_no_executions_route_in_execute_router` (introspects `execute_router.routes` paths) + `test_exactly_one_handler_per_method_path_under_executions` (introspects `app.routes`). The comments are accurate (the poll surface genuinely is in executions.py) so they were left in place; no actual `/executions` route exists in execute.py.

## Authentication Gates

None — all proofs are keyless (planted spec, neo4j off, no provider keys). The I1 ci_token bearer wiring is exercised structurally (the gate accepts cookie OR bearer; unauth → 401); a live CI bearer call reaching the API stays Manual-Only (Plan 05's self-hosted-runner/tunnel note), not an auth gate in this plan's automated scope.

## Known Stubs

None that block EXEC-04/EXEC-05. The serving-route guard that RESOLVES the run-relative `TestArtifact.path` (and rejects path traversal) is intentionally Plan 04's surface — this plan DEFINES the on-disk layout + records the run-relative paths (the contract Plan 04 consumes), which is exactly the plan's B2 scope. The kill-flag drain + the `aborted` verdict are likewise Plan 04 (the no-op hook shape is kept; no placeholder kill behavior was added).

## Threat Flags

None — no new trust-boundary surface beyond the plan's `<threat_model>` (the POST/GET routes + the artifact filesystem writes are exactly the boundaries enumerated there; T-07-10/T-07-11/T-07-12/T-07-18 mitigations are all implemented and asserted).

## Self-Check: PASSED

- Created files verified present: `app/services/worker/classifier.py`, `app/services/exec_history.py`, `tests/unit/test_flaky_classifier.py`, `tests/functional/test_artifact_capture.py`, `tests/functional/test_exec_history.py`, `tests/functional/test_execute_tier.py` — all on disk.
- Commits verified in git log: `9508892`, `f2f72e9`, `a1aad58`, `8dd4b83`, `1a7dcb8`, `65a360f` — all present.
