---
phase: 06-bdd-playwright-generation
plan: 04
subsystem: api
tags: [stability, seeded-bug, breakage-detection, subprocess-runner, planted-spec, compose, build-arg, oom-sequencing]

# Dependency graph
requires:
  - phase: 06-bdd-playwright-generation
    provides: "codegen.generate_project + conftest.py.j2 reading TARGET_BASE_URL (06-03); retained test_login.py.j2 planted-spec skeleton"
  - phase: 03-tracer-bullet-minimal-end-to-end-loop
    provides: "execution.run_execution subprocess runner shape (create_subprocess_exec, argv list, no shell, _run_cwd, output cap); workspaces run_id-derived spec convention"
  - phase: 01-foundation
    provides: "infra/targets/saucedemo Dockerfile (pinned-SHA nginx build) + docker-compose saucedemo service + profile-gating shape"
provides:
  - "services/stability.run_stability (accept iff all N exit 0, fail-fast), run_seeded_bug (must FAIL vs bug build via TARGET_BASE_URL override), accept_spec (green-vs-std AND red-vs-bug)"
  - "infra/targets/saucedemo/Dockerfile SEED_BUG build-arg (renames .inventory_list -> .inventory_list_BROKEN only when SEED_BUG=1; default build byte-identical)"
  - "infra/docker-compose.yml saucedemo-bug service (profile bugbuild, port 8081:80, mem_limit 128m, SEED_BUG=1)"
  - "STABILITY_RUNS (default 3) + SEEDED_BUG_BASE_URL settings + api env + .env.example"
  - "planted-spec deterministic proof (test_stability.py + test_seeded_bug.py) — passes N vs SauceDemo, fails vs the bug build, no keys"
affects: [07-execution-engine]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "N-run stability gate: run the SAME spec N consecutive isolated subprocesses (uv run pytest, argv list, no shell); accept iff ALL N exit 0; fail-fast on the first non-green run"
    - "Seeded-bug breakage detection: one deterministic DOM mutation via a Dockerfile build-arg (SEED_BUG=1) on the EXISTING target build, profile-gated off by default, distinct port; the SAME accepted spec re-run against it must FAIL"
    - "TARGET_BASE_URL env override repoints the SAME spec at the bug build without re-rendering (the generated conftest reads it)"
    - "OOM sequencing under the 3GB cap: codegen reads the Element Repository under graph_mode, then neo4j is STOPPED before the run phase (saucedemo + saucedemo-bug + Chromium fit without neo4j)"
    - "Planted-spec deterministic proof: render the real generation skeleton with fixed observed slots (no gateway/keys) to prove the whole harness mechanic"

key-files:
  created:
    - apps/api/app/services/stability.py
    - apps/api/tests/functional/test_stability.py
    - apps/api/tests/functional/test_seeded_bug.py
  modified:
    - infra/targets/saucedemo/Dockerfile
    - infra/docker-compose.yml
    - .env.example
    - apps/api/app/core/config.py

key-decisions:
  - "Seeded defect = rename `.inventory_list` -> `.inventory_list_BROKEN` across the served bundle (grep -rl | xargs sed) under SEED_BUG=1; the post-login success assertion (.inventory_list visible) then fails vs the bug build (Open-Q1 decided id+spec together)"
  - "The planted spec is the RETAINED test_login.py.j2 rendered with fixed observed slots, post-processed to read TARGET_BASE_URL (os.environ.get) so the SAME spec serves both the standard run and the seeded-bug run via the env override the generated conftest uses"
  - "The harness functional tests drive run_stability/run_seeded_bug IN-PROCESS on the HOST (mirroring test_codegen's host-driver pattern), so the Chromium subprocess reaches the targets by their HOST-published ports (localhost:8080 std, localhost:8081 bug) — not the in-cluster compose names"
  - "accept_spec requires BOTH halves: a flaky spec is not stable, and a spec that passes vs a known-broken target is not detecting breakage (the rejects-when-bug-run-passes test models the second case by pointing the bug run at the standard build)"
  - "run_stability fail-fasts: a single red run rejects without running all N (no wasted Chromium launches)"

patterns-established:
  - "_run_spec_once shared helper wraps the Phase-3 create_subprocess_exec shape and returns {passed, exit_code, output} (no DB row) — the building block for both run_stability (N x) and run_seeded_bug (1 x with env override)"
  - "Build-arg toggled defect on the existing target image (zero new packages, default build unchanged) as the breakage-detection mechanism"

requirements-completed: [GEN-05]

# Metrics
duration: ~30min
completed: 2026-06-20
---

# Phase 6 Plan 04: N-run Stability + Seeded-Bug Acceptance Harness Summary

**The stability + breakage-detection trust gate (GEN-05 / D-07/D-08): a generated spec is accepted only if it passes N consecutive isolated subprocess runs (env STABILITY_RUNS, default 3) AND fails against a dedicated seeded-bug SauceDemo build (a `SEED_BUG=1` build-arg renaming `.inventory_list` -> `.inventory_list_BROKEN`, served by a profile-gated `saucedemo-bug` compose service on a distinct port). The whole harness is proven deterministically with a planted template-rendered spec — passes N times vs the standard build, fails vs the bug build — with zero provider keys, reusing the Phase-3 subprocess runner verbatim and sequencing for the 3GB memory cap (codegen reads the graph; the run phase stops neo4j first).**

## Performance
- **Duration:** ~30 min
- **Completed:** 2026-06-20
- **Tasks:** 2
- **Files:** 7 (3 created, 4 modified)

## Accomplishments
- **Seeded-bug SauceDemo build (`infra/targets/saucedemo/Dockerfile`, D-08 / T-06-21):** added `ARG SEED_BUG=0` and a final nginx-stage layer that, ONLY when `SEED_BUG=1`, applies ONE deterministic mutation (`grep -rl 'inventory_list' | xargs sed -i 's/inventory_list/inventory_list_BROKEN/g'`) to the served bundle. The default build (`SEED_BUG=0`) is byte-identical to the standard target — the `if` block is skipped. Verified the bug image has 4 `inventory_list_BROKEN` and 0 bare `inventory_list` occurrences; the default image is unchanged.
- **`saucedemo-bug` compose service (`infra/docker-compose.yml`, D-08):** mirrors the `saucedemo` block with `build.args.SEED_BUG: "1"`, `mem_limit 128m`, the same wget healthcheck (127.0.0.1:80), a DISTINCT host port (`8081:80`), and `profiles: [bugbuild]` so a plain `up` NEVER starts it (mirrors neo4j's `profiles:[graph]` — OOM safety). `docker compose --profile bugbuild build saucedemo-bug` succeeds; `docker compose config` confirms the args/port/mem_limit/profile.
- **Settings + env (`config.py`, `.env.example`, compose api env):** `stability_runs: int = 3` (env `STABILITY_RUNS`) and `seeded_bug_base_url: str | None` (env `SEEDED_BUG_BASE_URL`); the api service env block enumerates both (`STABILITY_RUNS`, `SEEDED_BUG_BASE_URL`) per the Phase-2 explicit-enumeration pattern; `.env.example` documents both (no literal secrets).
- **N-run + seeded-bug harness (`services/stability.py`, D-07/D-08 / GEN-05):** `run_stability` runs the spec N times via the Phase-3 `create_subprocess_exec` shape VERBATIM (argv list, no shell, output tail-capped, `_run_cwd`), accepts iff ALL N exit 0, and FAIL-FASTS on the first red run. `run_seeded_bug` re-runs the SAME spec once with `TARGET_BASE_URL` overriding the base URL into the child env (the generated conftest reads it), pointing it at the bug build; `detected_breakage` is True iff the run FAILS. `accept_spec` returns `accepted=True` iff stability is all-green AND the seeded-bug run failed. NEVER in-process pytest (T-06-19); `spec_path` run_id-derived (T-06-18). The module docstring documents and the caller enforces the OOM sequencing (T-06-20).
- **Planted-spec deterministic proof (`test_stability.py`, `test_seeded_bug.py`, no keys):** render the REAL retained `test_login.py.j2` with fixed observed SauceDemo slots (asserting `.inventory_list`), post-processed to read `TARGET_BASE_URL`. `test_stability.py` proves an all-green planted spec is accepted over 3 runs and a deliberately-failing one is rejected (with fail-fast). `test_seeded_bug.py` proves the SAME planted spec FAILS vs `saucedemo-bug`, that `accept_spec` accepts only when green-vs-std AND red-vs-bug, and rejects when the bug run still passes (modelled by pointing it at the standard build).

## Task Commits
1. **Task 1: seeded-bug build-arg + saucedemo-bug service + settings/env** — `f1eafa1` (feat)
2. **Task 2: N-run stability + seeded-bug harness + planted-spec proof** — `3c77027` (feat)

## Files Created/Modified
- `apps/api/app/services/stability.py` — N-run stability + seeded-bug acceptance harness (reuses the Phase-3 subprocess runner; OOM sequencing documented)
- `apps/api/tests/functional/test_stability.py` — planted-spec N-run proof (accepted all-green, rejected on red + fail-fast)
- `apps/api/tests/functional/test_seeded_bug.py` — planted-spec breakage-detection proof (fails vs bug build; accept_spec green-AND-red gate)
- `infra/targets/saucedemo/Dockerfile` — `SEED_BUG` build-arg (one deterministic `.inventory_list` rename only when SEED_BUG=1)
- `infra/docker-compose.yml` — `saucedemo-bug` service (profile bugbuild, port 8081, mem_limit 128m) + `STABILITY_RUNS`/`SEEDED_BUG_BASE_URL` api env
- `.env.example` — `STABILITY_RUNS` + `SEEDED_BUG_BASE_URL` env contract
- `apps/api/app/core/config.py` — `stability_runs` (default 3) + `seeded_bug_base_url` settings

## Decisions Made
See key-decisions in frontmatter. Notably: the seeded defect renames `.inventory_list` (decided id+spec together per Open-Q1); the planted spec is the retained `test_login.py.j2` made env-overridable so the SAME spec serves both runs; the functional tests drive the harness in-process on the host so Chromium reaches the targets by host-published ports (8080/8081).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Planted-spec target URLs use host-published ports, not in-cluster compose names**
- **Found during:** Task 2 (running the planted-spec functional tests)
- **Issue:** The plan's interface notes referenced the in-cluster URL `http://saucedemo:80` (used by `test_execute.py`, which runs the spec INSIDE the api container via the API). These new tests drive `run_stability`/`run_seeded_bug` IN-PROCESS on the host (mirroring `test_codegen.py`'s host-driver pattern), so the Chromium subprocess runs on the host and cannot resolve in-cluster compose names.
- **Fix:** the planted spec targets the HOST-published ports (`http://localhost:8080` std, `http://localhost:8081` bug) — the same host-driver convention `test_codegen.py` uses for the Bolt/Postgres host overrides. The harness itself is host/container-agnostic (it just runs `uv run pytest`); only the target URL the planted spec resolves changed.
- **Files modified:** apps/api/tests/functional/test_stability.py, apps/api/tests/functional/test_seeded_bug.py
- **Verification:** test_stability.py 2 passed; test_seeded_bug.py 3 passed (against the host-published targets).
- **Committed in:** 3c77027 (Task 2)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** No scope change — a host-vs-container target-URL alignment for the in-process host-driven proof; no new packages, no behavior change to the shipped harness.

## Verification Results
- `docker compose --profile bugbuild build saucedemo-bug` → **succeeds**; bug image has 4 `inventory_list_BROKEN` / 0 bare `inventory_list` (mutation applied); default build unchanged (`if` skipped).
- `docker compose config` → `saucedemo-bug` shows `SEED_BUG: "1"`, port `8081:80`, `mem_limit 128m`, `profiles:[bugbuild]`; api env carries `STABILITY_RUNS: "3"` + `SEEDED_BUG_BASE_URL`.
- `settings.stability_runs` → **3**; `settings.seeded_bug_base_url` → None by default (passed explicitly in the proof).
- `uv run pytest tests/functional/test_stability.py -m graph -q` → **2 passed** (all-green accepted over N; failing rejected with fail-fast).
- `uv run pytest tests/functional/test_seeded_bug.py -m graph -q` → **3 passed** (planted spec fails vs bug build; accept_spec green-AND-red; rejects when bug run passes).
- Subprocess discipline (grep `stability.py`): `create_subprocess_exec` present with an argv LIST; `pytest.main`/`shell=True` appear ONLY in docstring negative-assertion prose, never in code.
- `uv run pytest -m "not live_llm and not e2e and not graph" -q` → **286 passed, 44 deselected** (no regressions; the 5 new graph-marked planted-spec tests are correctly deselected from the default gate).

## Manual-Only (provider keys / graph / memory)
- The 5 new planted-spec tests are graph-marked (run under graph_mode per project convention); they need the default stack + `saucedemo` (8080) and `saucedemo-bug` (8081) up — NO neo4j and NO provider keys (the planted spec is deterministic).
- **OOM sequencing (T-06-20, enforced):** codegen reads the Element Repository under graph_mode (neo4j up, web stopped); the RUN phase needs no graph — STOP neo4j before run_stability/run_seeded_bug. `saucedemo-bug` was stopped after the proof to free memory.
- **Manual memory check (06-VALIDATION):** `docker stats` during the seeded-bug harness staying under 3GB is a Manual-Only check; the sequencing keeps saucedemo (128m) + saucedemo-bug (128m) + Chromium comfortably under the cap without neo4j.
- The live generate→review→codegen→stabilize chain (needs provider keys) is Manual-Only per project-wide convention.

## Next Phase Readiness
- GEN-05 (stability half) complete: the N-run stability gate + the seeded-bug breakage-detection acceptance are built, the seeded-bug build + service exist, and the whole mechanic is proven deterministically with a planted spec (no keys), sequenced for the 3GB cap.
- Phase 7 (execution engine) can build the suite-tier / RabbitMQ-worker execution on top of `run_stability` as the per-spec acceptance gate; `accept_spec` is the single green-AND-red acceptance entrypoint.

## Self-Check: PASSED
All three created files exist on disk (`services/stability.py`, `tests/functional/test_stability.py`, `tests/functional/test_seeded_bug.py`); both task commits (`f1eafa1`, `3c77027`) are present in git history.

---
*Phase: 06-bdd-playwright-generation*
*Completed: 2026-06-20*
