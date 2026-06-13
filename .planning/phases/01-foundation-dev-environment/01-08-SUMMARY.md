---
phase: 01-foundation-dev-environment
plan: 08
subsystem: infra
tags: [phase-gate, verify-stack, dev-setup-docs, clean-state, infra-01, gitignore, pytest-harness]

# Dependency graph
requires:
  - phase: 01-foundation-dev-environment (plan 01-01)
    provides: compose core, .env contract, .wslconfig.example, canonical invocation, docs/dev-setup.md skeleton
  - phase: 01-foundation-dev-environment (plan 01-04)
    provides: full default-profile stack (api + web) and e2e Playwright tests
  - phase: 01-foundation-dev-environment (plan 01-07)
    provides: saucedemo demo target + reset_target.py contract
provides:
  - infra/scripts/verify_stack.py — INFRA-01 evidence script (stdlib-only; services-healthy / dormant-absent / mem-limit / HTTP-entrypoint assertions; self-demonstrating exit codes)
  - docs/dev-setup.md — complete dev workflow for both run modes (Docker stack + hybrid host), test workflow, reset-target, .wslconfig install with low-RAM tuning, verify_stack usage
  - Deterministic full-suite ordering (functional-before-e2e) so the canonical one-command `uv run pytest tests` is green in one process
affects: ["Phase 2 (launches directly off a green Phase 1 gate per D-01)", "every later phase consuming verify_stack.py as the stack health gate"]

# Tech tracking
tech-stack:
  added: []
  patterns: [stdlib-only host evidence script (mirrors reset_target.py), profiles-verified-by-absence, HostConfig.Memory non-zero assertion, collection-order hook to separate asyncio/playwright loop regimes in one process]

key-files:
  created:
    - infra/scripts/verify_stack.py
    - .planning/phases/01-foundation-dev-environment/01-08-SUMMARY.md
  modified:
    - docs/dev-setup.md
    - .gitignore
    - apps/api/tests/conftest.py

key-decisions:
  - "verify_stack.py is stdlib-only (json/subprocess/urllib/pathlib) and resolves the compose file relative to itself, mirroring reset_target.py — runs from any cwd with the host's plain Python, no uv env."
  - "Dormant services verified by ABSENCE from `docker compose ps` (RESEARCH anti-pattern: a profile flag that could silently activate is worse than one that never runs)."
  - "Web entrypoint check accepts 200 OR 3xx: the unauthenticated `/` legitimately 307-redirects to /login, so requiring a flat 200 would false-fail a healthy stack."
  - "One-command full suite fixed via a stdlib collection-ordering hook (e2e last), not a new dependency: pytest-asyncio and pytest-playwright each drive their own event loop and default collection order interleaved them."
  - "On this 5.7 GB host (WSL capped at 3 GB) the full five-service stack cold-starts under `up --build --wait` without OOM or staged startup — recorded as the clean-state truth for this specific low-RAM host."

requirements-completed: [INFRA-01]

# Metrics
duration: ~13min active (automated portion; human gate pending)
completed: 2026-06-13
---

# Phase 01 Plan 08: Phase Gate — verify_stack.py + Dev-Setup Docs + Clean-State Run Summary

**The Phase 1 gate, automated half green from a cold start: `down -v` -> `up --build --wait` (all five services healthy, no OOM on a 3 GB WSL cap) -> full pytest suite 31/31 -> `verify_stack.py` exit 0. INFRA-01 evidence script and complete dev-setup docs shipped; one-command full-suite run fixed. Host-level WSL/Vmmem + UI walkthrough returned to the human as a blocking checkpoint (not self-approved).**

## Performance

- **Duration:** ~13 min active execution (automated tasks); human gate pending
- **Completed:** 2026-06-13 (automated portion)
- **Tasks:** 3 (2 auto complete; 1 checkpoint:human-verify returned, not self-approved)
- **Files modified:** 4 (1 created, 3 modified) + this SUMMARY

## Accomplishments

- **verify_stack.py (INFRA-01 evidence):** stdlib-only script asserting four check groups — (1) default services exactly `{postgres, redis, api, web, saucedemo}` all healthy; (2) dormant `{neo4j, rabbitmq, elasticsearch}` absent; (3) every running container's `HostConfig.Memory` non-zero (api 1g / postgres 512m / redis 256m / saucedemo 128m / web 1.5g confirmed in bytes); (4) api `/health` 200 with postgres+redis true, web 200-or-3xx, saucedemo 200. Prints a PASS/FAIL line per group; exits 0 only if all pass.
- **Self-demonstrated the FAIL path:** stopped redis -> script exited 1 naming `redis` (and api /health correctly 503'd); restarted redis -> exit 0 restored. Meets the "self-demonstrating" acceptance criterion.
- **docs/dev-setup.md completed:** canonical compose invocation, hybrid host mode (D-09, the primary iteration workflow), full test workflow (quick / full / e2e prereqs), reset-target usage with the localStorage honesty note, `.wslconfig` install with a host-RAM tuning table + an explicit low-RAM warning (the 16 GB template wedged this 5.7 GB machine; tune `memory=` down before first `wsl --shutdown`), and verify_stack.py as the INFRA-01 evidence command. T-01-28 verified: only variable NAMES and generation one-liners appear, no secret values (grep-checked against .env; the only .env values present are non-secret localhost URLs).
- **Clean-state phase gate passed end-to-end (zero manual interventions between steps):**
  1. `docker compose ... down -v` — pgdata volume destroyed.
  2. `docker compose ... up -d --build --wait` — all five services Healthy from cold; **no OOM** on the 3 GB WSL cap, no staged startup needed.
  3. `cd apps/api && uv run pytest tests -q` — **31 passed** (22 functional + 9 e2e), stable across two consecutive runs.
  4. `python infra/scripts/verify_stack.py` — exit 0, all four groups PASS.
- **.gitignore sweep:** ignored `*.log` (alembic-run.log, uvicorn.log, verify-t2.log) and `.claude/` (machine-local settings) — the housekeeping item 01-07 deferred to this plan. The log files themselves were NOT committed; `git status` is now clean.

## Task Commits

1. **Task 1: verify_stack.py + complete dev-setup docs** — `66249a6` (feat)
2. **gitignore sweep (housekeeping deferred from 01-07)** — `bdf58cd` (chore)
3. **Task 2 gate fix: order e2e after functional (one-command suite)** — `3dd766c` (fix)

(Task 2's gate run produced no file changes of its own beyond the harness fix above; Task 3 is a returned human-verify checkpoint, documented below.)

## Files Created/Modified

- `infra/scripts/verify_stack.py` — INFRA-01 evidence script (stdlib-only; ps + inspect + HTTP probes; PASS/FAIL table; exit 0 only if all pass)
- `docs/dev-setup.md` — completed: both run modes on one `.env`, test workflow, reset-target, `.wslconfig` install + low-RAM tuning, verify_stack usage
- `.gitignore` — `*.log` and `.claude/` ignored (sweep)
- `apps/api/tests/conftest.py` — `pytest_collection_modifyitems` orders e2e after functional so the single-process full suite is green

## Decisions Made

- **Web entrypoint accepts 200 OR 3xx.** The unauthenticated web root 307-redirects to `/login`; a flat-200 assertion would false-fail a perfectly healthy stack. The probe suppresses redirect-following so it observes the 307 directly.
- **One-command full suite fixed with a collection-order hook, not a dependency.** Running `tests/functional` and `tests/e2e` separately both passed (22 / 9), but `pytest tests` failed with `Cannot run the event loop while another loop is running` / `Runner is closed` — pytest-asyncio and pytest-playwright each drive an event loop and default file order interleaved their teardowns. Sorting e2e last makes the two loop regimes strictly sequential in the one process; no `pytest-xdist` install (which would also be excluded as a package-install auto-fix).
- **Low-RAM cold-start is the recorded gate truth.** The five-service stack reached healthy under one `up --build --wait` on the 3 GB WSL cap without OOM or staged startup, so the plan's "one command from clean state" truth holds on this host as-is.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] One-command full suite failed: asyncio/Playwright event-loop conflict**
- **Found during:** Task 2, gate step 3 (`uv run pytest tests -q`)
- **Issue:** The canonical full-suite command failed (3 failed, 17 errors) with `RuntimeError: Cannot run the event loop while another loop is running` and `Runner is closed`. Functional (pytest-asyncio) and e2e (pytest-playwright) each run their own asyncio loop; pytest's default collection order interleaved them, so an async functional fixture tore down while Playwright's loop was still live. Both suites passed green in isolation (functional 22/22, e2e 9/9) and when explicitly ordered (`pytest tests/functional tests/e2e` -> 31 passed), proving it was an ordering bug, not a stack or application failure.
- **Fix:** Added `pytest_collection_modifyitems` to `apps/api/tests/conftest.py` sorting `tests/e2e/*` after all functional tests. Stdlib-only; no new dependency.
- **Files modified:** apps/api/tests/conftest.py
- **Commit:** 3dd766c
- **Verification:** `uv run pytest tests -q` now passes 31/31, stable across two consecutive runs.

**2. [Rule 3 - Housekeeping] .gitignore sweep for deferred untracked artifacts**
- **Found during:** Task 1 (start-of-plan environment scan)
- **Issue:** Untracked root artifacts (`alembic-run.log`, `uvicorn.log`, `verify-t2.log`, `.claude/`) flagged by 01-07's SUMMARY for a sweep "in 01-08" cluttered `git status` and risked accidental commits.
- **Fix:** Added `*.log` and `.claude/` to `.gitignore`; verified `git check-ignore` matches all four; log files NOT committed.
- **Files modified:** .gitignore
- **Commit:** bdf58cd

**Total deviations:** 2 auto-fixed (1 test-harness bug blocking the gate, 1 planned housekeeping sweep). No scope creep; no architectural changes; no new dependencies.

## Authentication Gates
None.

## Known Stubs
None — verify_stack.py and the docs are fully wired and exercised (script run live PASS, FAIL-on-stopped-service, and PASS-on-restart; docs grep-verified for hybrid/reset_target/.wslconfig and absence of secrets).

## Human Verification (Task 3 — blocking checkpoint, APPROVED 2026-06-13)

The host-level Manual-Only checks (01-VALIDATION.md) plus the UI walkthrough were performed by the human and **approved on 2026-06-13**:

1. **WSL memory cap (INFRA-01 / Pitfall 9):** ✅ after `wsl --shutdown` + Docker Desktop restart + `up -d --wait`, Vmmem/VmmemWSL stayed bounded near the `memory=3GB` cap; `verify_stack.py` exit 0.
2. **UI walkthrough:** ✅ http://localhost:3000 -> /login -> admin login -> register / edit (masked credentials) / deactivate / reactivate a target -> log out, all per the UI contract.
3. **Demo target:** ✅ http://localhost:8080 serves the SauceDemo (Swag Labs) login; `python infra/scripts/reset_target.py saucedemo` exits 0 (corroborated: :8080 returns 200).

Phase 1 gate is GREEN. Per D-01 the green gate flows directly into Phase 2.

## Next Phase Readiness

- All five ROADMAP Phase 1 success criteria are evidenced from a cold start (the automated half); the green gate flows directly into Phase 2 per D-01 once human sign-off lands.
- INFRA-01 evidence (verify_stack.py PASS table) recorded above mitigates T-01-30 ("works on my machine"): the gate ran from `down -v`, not an incrementally-mutated stack.
- **Phase 3 blocker stands (carried, not introduced here):** neo4j (2g, Phase 3) and elasticsearch (1.5g, Phase 9/10) will not fit alongside the current stack under the 3 GB WSL cap on this 5.7 GB host — resolve before Phase 3 (more RAM, remote/managed services, or trimmed mem_limits).

## Self-Check: PASSED

- All key files present on disk: infra/scripts/verify_stack.py, docs/dev-setup.md, apps/api/tests/conftest.py, .gitignore
- All task commits present in git history: 66249a6, bdf58cd, 3dd766c
- must_haves.artifacts `contains` checks: verify_stack.py contains "HostConfig" (YES), docs/dev-setup.md contains "hybrid" (YES)
- Clean-state gate green end-to-end: down -v -> up --build --wait (5/5 healthy) -> pytest 31/31 (x2) -> verify_stack.py exit 0

---
*Phase: 01-foundation-dev-environment*
*Completed: 2026-06-13 — automated + human-verify gate both green*
