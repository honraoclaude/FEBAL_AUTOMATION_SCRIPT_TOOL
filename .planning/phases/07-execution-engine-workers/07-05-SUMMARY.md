---
phase: 07-execution-engine-workers
plan: 05
subsystem: api
tags: [execution-engine, ci, github-actions, determinism, scoped-token, planted-spec, reset-target, sc2, sc5, keyless]

# Dependency graph
requires:
  - phase: 07-execution-engine-workers
    provides: "07-01 exec_service (create_test_run + enqueue_jobs), worker plane, settings.amqp_url/exec_prefetch_count; the /api/executions start+poll routes (B1) the CI workflow targets"
  - phase: 06-bdd-playwright-generation
    provides: "the retained test_login.py.j2 planted spec + _render_planted_spec/_plant host-driver helpers (TARGET_BASE_URL-overridable)"
  - phase: 03-tracer-bullet-minimal-end-to-end-loop
    provides: "stability._run_spec_once subprocess primitive (argv list, no shell, TARGET_BASE_URL override)"
  - phase: 01-foundation
    provides: "infra/scripts/reset_target.py generic name->strategy reset contract (exit 0/1/2)"
provides:
  - ".github/workflows/run-suite.yml: workflow_dispatch CI trigger that STARTS a tier run via POST /api/executions and POLLS GET /api/executions/{run_id} back, mapping passed->0 / failed|killed->1 (SAME engine code path, never pytest in CI — D-08)"
  - "settings.ci_token (env CI_TOKEN): the scoped start+poll credential definition (default None; route-level bearer enforcement is plan 07-03)"
  - "tests/unit/test_ci_workflow_contract.py: keyless yaml-parse + start/poll/exit-mapping + no-inline/no-echo token + ci_token-setting contract"
  - "tests/functional/test_determinism.py: two-runs-identical proof (planted spec, reset_target.py between runs, compare on status/verdict not timing, keyless)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CI parity = same-engine start-then-poll (D-08): the GitHub Actions workflow curls POST /api/executions to start and polls GET /api/executions/{run_id}; passed->exit 0, failed|killed->exit 1, timeout->exit 1 — never a separate pytest path in CI"
    - "Scoped, never-echoed CI credential: CI_TOKEN + PLATFORM_API_URL from GitHub `secrets`, presented as a Bearer, NEVER printed; settings.ci_token defines the scope, the route-level bearer check lands in 07-03 (Pitfall 7 / T-07-07/08)"
    - "Determinism proof = run the SAME planted spec twice via _run_spec_once (reused verbatim) with reset_target.py saucedemo between runs; compare ONLY exit_code/passed/derived-verdict, EXCLUDE timing/timestamps/durations (Pitfall 6); proven KEYLESS + neo4j-OFF (Phase-6 planted-spec trick)"
    - "The result-surface assertion (set(result) == {passed, exit_code, output}) structurally guarantees the comparison cannot drift onto a timing/duration key"

key-files:
  created:
    - .github/workflows/run-suite.yml
    - apps/api/tests/unit/test_ci_workflow_contract.py
    - apps/api/tests/functional/test_determinism.py
  modified:
    - apps/api/app/core/config.py

key-decisions:
  - "The workflow header comment was reworded to NOT contain the literal `echo \"$CI_TOKEN\"` — the no-echo unit test (and the plan acceptance grep `echo .*CI_TOKEN`) is content-based and a literal in a comment would (correctly) trip it. The rule is documented in prose without the trigger phrase."
  - "The no-pytest-in-CI assertion ignores comment lines (the header documents the no-pytest rule using the word 'pytest'); it asserts no NON-comment line invokes pytest — the substantive D-08 guarantee."
  - "The POST-start assertion uses a DOTALL regex (`-X POST .* $PLATFORM_API_URL/api/executions`) because the curl is split across lines with `\\` continuations; a single-line anchored regex would false-negative on the readable multi-line form."
  - "test_determinism contains ONE create_subprocess_exec — the reset_target.py invocation (argv list, no shell, honoring exit 0/1/2). The SPEC runner is reused verbatim via _run_spec_once and is NOT re-implemented; the reset subprocess is the Phase-1 reset contract, not a second test runner (see interpretation note below)."
  - "Plan W1 honored: exec_service.py was NOT modified (kept Wave-2 parallel-safe with 07-02); only config.py (ci_token) + the workflow yaml + the two tests changed."

patterns-established:
  - "CI is a thin client of the platform engine — start + poll over HTTP with a scoped bearer; no test logic, no pytest, lives in CI (D-08 single engine path)."
  - "Determinism is asserted on the engine's COMPARABLE surface (status/verdict) with a structural guard (result-key set) against ever comparing timing."

requirements-completed: [EXEC-02]

metrics:
  duration: ~25min
  tasks-completed: 2
  files-created: 3
  files-modified: 1
  completed-date: 2026-06-21
---

# Phase 7 Plan 05: Local/Docker/CI Parity + Determinism Harness Summary

Delivered EXEC-02 (local/Docker/CI execution parity) as a same-engine CI trigger plus the determinism proof. A net-new GitHub Actions workflow (`.github/workflows/run-suite.yml`) STARTS a tier run by calling the platform API (`POST /api/executions`) and POLLS run status back (`GET /api/executions/{run_id}`), mapping `passed`->exit 0 and `failed`/`killed`->exit 1 — the SAME engine code path used locally and in Docker, never a second pytest path in CI (D-08). The scoped `CI_TOKEN` is presented as a Bearer from a GitHub secret and is never echoed; `settings.ci_token` defines the start+poll scope (the route-level bearer check lands in plan 07-03). The determinism harness (`test_determinism.py`) runs the SAME Phase-6 planted spec twice via the reused `_run_spec_once` primitive, calling `reset_target.py saucedemo` between runs, and asserts the two runs are identical on status/verdict — explicitly excluding timing/timestamps/durations (Pitfall 6) — proven KEYLESS and with neo4j OFF.

## What Was Built

**Task 1 — CI trigger workflow + scoped ci_token contract + keyless contract test (`3084251`):**
- `.github/workflows/run-suite.yml` (net-new `.github/` surface): `workflow_dispatch` with a `tier` input (default smoke); a `run` job whose `start` step POSTs `{"tier": <input>}` to `$PLATFORM_API_URL/api/executions` with `Authorization: Bearer $CI_TOKEN`, captures `run_id` via `jq` into `$GITHUB_OUTPUT`; the `poll` step loops `GET $PLATFORM_API_URL/api/executions/$run_id`, mapping `passed`->exit 0, `failed`/`killed`->exit 1, timeout->exit 1. A header comment documents the A5 reachability assumption (self-hosted runner on the dev box OR a tunnel; host port 8001 is local) and the scoped-token requirement (start+poll only; route-level bearer is plan 07-03).
- `config.py`: added `ci_token: str | None = None` (env `CI_TOKEN`), the scoped start+poll credential, default None so the api boots without it.
- `tests/unit/test_ci_workflow_contract.py`: keyless yaml-parse asserting workflow_dispatch+tier input, POST /api/executions + GET /api/executions/{run_id}, secrets-sourced CI_TOKEN/PLATFORM_API_URL, no inlined literal token, no echoed token, the passed->0/failed->1 mapping, and that `settings.ci_token` exists with default None.

**Task 2 — Determinism harness (`058da75`):**
- `tests/functional/test_determinism.py` (marker functional, keyless): renders the SAME Phase-6 planted spec (`_plant` + the `test_login.py.j2` fixed-slot render, TARGET_BASE_URL-overridable), runs it TWICE via `stability._run_spec_once` (reused verbatim — no re-implemented runner), calling `reset_target.py saucedemo` between the two runs (subprocess, argv list, honoring its exit-code contract). Asserts both runs are green and IDENTICAL on `exit_code`/`passed`/derived verdict, and structurally guards against timing comparison by asserting the result surface is exactly `{passed, exit_code, output}` (no duration/timestamp key exists to compare). Docstring documents the D-03b/Phase-6 sequencing (neo4j OFF during the run phase; planted spec needs no graph and no keys) and the SauceDemo localStorage isolation note.

## Verification Evidence

- `uv run pytest tests/unit/test_ci_workflow_contract.py -q` -> **5 passed in 1.72s** (yaml parse, start/poll route, scoped/no-echo token, exit mapping, ci_token setting).
- `uv run pytest tests/functional/test_determinism.py -m functional -q` -> **1 passed in 43.13s** (two planted-spec runs vs reset SauceDemo on host 8080, identical status/verdict, keyless, neo4j off).
- `uv run pytest -m "not live_llm and not graph and not e2e" -q` -> **314 passed, 44 deselected in 126.45s** — no regressions (up from 07-01's 289; includes the two new tests + the worker round-trip).
- Acceptance greps: `.github/workflows/run-suite.yml` has no `echo .*CI_TOKEN|echo .*token` match (token never echoed); `test_determinism.py` references `reset_target`/`reset` (the reset call) and contains no `shell=True`; the spec runs reuse `_run_spec_once` (no re-implemented spec runner).
- SauceDemo confirmed up on host port 8080 (HTTP 200) for the determinism run.

## SC3 Parallel Claim (named, not silently unproven)

SC3 ("two jobs run concurrently") is proven in TWO named parts:
1. **AUTOMATED (prefetch bound):** Plan 07-01's `tests/functional/test_worker_consume.py` asserts `prefetch_count==2` on the real consumer channel — the configured concurrency bound (the positively-tested half).
2. **Manual-Only (memory-fit concurrency):** two browser jobs actually running at once under the 768m worker mem_limit + the 3GB cap is the Plan-04 Manual-Only live end-to-end check (watch two flows progress concurrently under prefetch=2). Explicitly a Manual check — NOT silently assumed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Workflow header comment tripped its own no-echo contract test**
- **Found during:** Task 1 (running `test_ci_workflow_contract.py`).
- **Issue:** the header comment literally contained `echo "$CI_TOKEN"` (as a "do not do this" example), which the no-echo unit test (and the plan acceptance grep `echo .*CI_TOKEN`) correctly flagged — a content-based grep cannot tell a comment from a command.
- **Fix:** reworded the comment to document the no-print rule without the trigger phrase; the substantive guarantee (token never printed) is unchanged.
- **Files modified:** `.github/workflows/run-suite.yml`
- **Commit:** `3084251`

**2. [Rule 1 - Bug] Two over-strict unit-test assertions**
- **Found during:** Task 1.
- **Issue:** (a) the POST-start regex anchored the URL on the same line as `-X POST`, but the curl spans multiple lines via `\` continuations -> false negative; (b) `"pytest" not in text` matched the word "pytest" in the header comment that documents the no-pytest-in-CI rule.
- **Fix:** (a) DOTALL regex matching `-X POST .* $PLATFORM_API_URL/api/executions`; (b) strip comment lines before asserting no pytest invocation on any non-comment line.
- **Files modified:** `apps/api/tests/unit/test_ci_workflow_contract.py`
- **Commit:** `3084251`

### Interpretation note (not a deviation)

The Task-2 acceptance grep (`create_subprocess_exec|shell=True` "shows it reuses stability's helpers (no new shell-based runner)") will surface ONE `create_subprocess_exec` in `test_determinism.py`. That call is the `reset_target.py saucedemo` invocation (argv list, no shell, honoring the script's exit-code contract) — the Phase-1 reset contract the plan explicitly requires between the two runs — NOT a re-implemented spec runner. The SPEC runs themselves go through `_run_spec_once` verbatim (no copy-paste), exactly as the plan directs ("reuse stability's helpers verbatim, do not re-implement the runner"). There is no `shell=True` anywhere.

## Authentication Gates

None — both proofs are keyless. The CI workflow's live trigger reaching the local API is Manual-Only (needs a self-hosted runner / tunnel, documented in the workflow header + plan user_setup); it is not an auth gate in this plan's automated scope.

## Known Stubs

None. The CI workflow is complete for its scope (start+poll contract); its route-level bearer enforcement is intentionally delivered by plan 07-03 (executions.py, I1) per the plan objective — documented, not a silent stub.

## Self-Check: PASSED

- Created files verified present: `.github/workflows/run-suite.yml`, `apps/api/tests/unit/test_ci_workflow_contract.py`, `apps/api/tests/functional/test_determinism.py` — all on disk.
- Commits verified in git log: `3084251`, `058da75` — both present.
