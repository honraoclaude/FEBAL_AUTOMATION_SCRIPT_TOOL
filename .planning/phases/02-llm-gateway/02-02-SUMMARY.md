---
phase: 02-llm-gateway
plan: 02
subsystem: api
tags: [llm-gateway, budgets, kill-switch, redis, async, pricing, pytest]

# Dependency graph
requires:
  - phase: 02-llm-gateway (plan 02-01)
    provides: complete() call+accounting path, llm_pricing lookup_price/compute_cost, llm_usage ledger, settings, mocked unit conftest
provides:
  - Shared lifespan-managed redis.asyncio client (app/core/redis_client.py) for the gateway hot path
  - Budget pre-check before spend (per-call/per-run/per-day, USD + token axes) raising BudgetExceeded
  - Reconcile-to-actual-usage after the call (counters incremented by real usage_metadata, not the reservation)
  - Hard kill-switch — auto-trip on daily-USD exhaustion + manual admin endpoints; global halt raising KillSwitchActive
  - Authenticated admin kill-switch API: POST/DELETE/GET /api/admin/llm/killswitch
  - Per-run budget overrides clamped to the global ceiling (tighten-only)
affects: [02-03, "Phase 4+ agents (every LLM call is now budget-gated + kill-switchable)"]

# Tech tracking
tech-stack:
  added: []
  patterns: [single lifespan-managed redis.asyncio client (NOT per-call connect/close), date-bucketed UTC daily counter keys, read-then-check budget race accepted for single-user MVP, autouse unit-test redis isolation (per-test client reset + test: prefix)]

key-files:
  created:
    - apps/api/app/core/redis_client.py
    - apps/api/app/routers/admin_llm.py
    - apps/api/tests/unit/test_budget_precheck.py
    - apps/api/tests/unit/test_budget_reconcile.py
    - apps/api/tests/unit/test_killswitch_auto.py
    - apps/api/tests/functional/test_killswitch.py
  modified:
    - apps/api/app/services/llm_gateway.py
    - apps/api/app/core/config.py
    - apps/api/app/main.py
    - apps/api/app/schemas/llm.py
    - apps/api/tests/unit/conftest.py
    - .env.example

key-decisions:
  - "Unit-test Redis isolation made autouse: reset the module-level redis_client._client between tests (pytest-asyncio fresh loop per test would otherwise reuse a client bound to a closed loop and raise RuntimeError) and pin gateway._KEY_PREFIX to test:llm: so unit tests never touch real dev counters"
  - "Kill-switch check is the FIRST hot-path Redis op (GET before pre-check/provider call) so a halt refuses every call (D-06)"

patterns-established:
  - "Gateway Redis hot path uses one long-lived client from app/core/redis_client.py via get_redis(); helpers set/clear/get_killswitch own the flag"
  - "Budget counters: date-bucketed UTC day keys (2-day TTL self-GC) + per-run keys (LLM_RUN_TTL_S); MGET pre-read, pipeline INCRBYFLOAT/INCRBY reconcile"
  - "Admin endpoints behind router-level Depends(get_current_user); Admin-RBAC restriction deferred to Phase 10 (documented V4 gap)"

requirements-completed: [PLAT-06]

# Metrics
duration: ~2h wall (executor interrupted by session limit mid-GREEN; finished inline on opus)
completed: 2026-06-13
---

# Phase 02 Plan 02: Budgets + Kill-Switch Summary

**Pre-check-before-spend budget enforcement (per-call/run/day, USD+tokens) raising BudgetExceeded, reconciled to actual usage, plus a global kill-switch (auto on daily exhaustion + authenticated admin panic button) raising KillSwitchActive — all over one lifespan-managed Redis client**

## Performance

- **Duration:** ~2h wall (executor wrote Task 1 + RED + most of GREEN, then hit a session limit; verification, isolation fix, Task 3, and closeout finished inline on opus)
- **Completed:** 2026-06-13
- **Tasks:** 3
- **Files modified:** 12

## Accomplishments
- Single long-lived `redis.asyncio` client wired into the FastAPI lifespan (open at startup, close at shutdown) — the net-new hot-path pattern PATTERNS.md flagged, NOT health.py's per-call connect/close
- Budget pre-check reserves estimated input + max_tokens at the model price and refuses (raises BudgetExceeded) any call breaching per-call/per-run/per-day on either USD or token axis — no provider call, no ledger row on breach
- Reconcile increments counters by ACTUAL usage_metadata after the call; per-run overrides clamp to the global ceiling (tighten-only)
- Kill-switch: auto-trips on daily-USD exhaustion and via authenticated POST /api/admin/llm/killswitch; global halt raises KillSwitchActive as the first hot-path check; DELETE/GET clear/read it
- 22 unit tests (mocked provider, no spend) + 2 functional kill-switch tests green; full suite 57 passed (`-m "not live_llm"`)

## Task Commits

1. **Task 1: Shared lifespan Redis client + budget settings** - `c86732d` (feat)
2. **Task 2: Pre-check, reconcile, auto-trip in complete()** - `086ede4` (test RED) → `44aae89` (feat GREEN)
3. **Task 3: Admin kill-switch endpoint + functional halt test** - `33302f3` (feat)

## Files Created/Modified
- `apps/api/app/core/redis_client.py` - single lifespan redis.asyncio client (get_redis/init_redis/close_redis)
- `apps/api/app/services/llm_gateway.py` - BudgetExceeded/KillSwitchActive; pre-check/reconcile/auto-trip; set/clear/get_killswitch helpers
- `apps/api/app/routers/admin_llm.py` - authenticated kill-switch POST/DELETE/GET
- `apps/api/app/core/config.py` + `.env.example` - 6 budget caps (USD+token × call/run/day) + LLM_RUN_TTL_S
- `apps/api/app/main.py` - lifespan init/close_redis; admin_llm router include
- `apps/api/tests/unit/{test_budget_precheck,test_budget_reconcile,test_killswitch_auto}.py` + `tests/functional/test_killswitch.py`
- `apps/api/tests/unit/conftest.py` - autouse gateway-Redis isolation fixture

## Decisions Made
- None beyond plan, except the test-isolation autouse fixture (see Issues) which was necessary for correctness once the gateway hot path began calling Redis.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Cross-test event-loop regression] Unit-test Redis isolation**
- **Found during:** Task 2 verification (resuming after the executor's session-limit cutoff) — 3 Plan-01 `test_gateway_provider` tests failed with an asyncio RuntimeError when run after the budget tests
- **Issue:** `complete()` now calls `get_redis()` on every call (kill-switch check), and `app/core/redis_client.py._client` is a module-level singleton; pytest-asyncio runs each test on a fresh event loop, so a client opened in one test and reused in the next is bound to a closed loop → RuntimeError. Un-patched tests would also write the REAL `llm:` dev counters.
- **Fix:** Added an autouse fixture in `tests/unit/conftest.py` that resets `redis_client._client` before/after each test (each test opens its own client on its own loop, closed in teardown) and pins `gateway._KEY_PREFIX` to `test:llm:` so unit tests never touch real counters.
- **Verification:** full unit suite 22/22 green; full suite 57/57 (`not live_llm`)
- **Committed in:** `44aae89` (Task 2 GREEN)

---

**Total deviations:** 1 auto-fixed (test-isolation correctness, required by the new Redis hot path)
**Impact on plan:** No scope change; the fix is test-only and makes the suite deterministic across event loops.

## Issues Encountered
- The spawning executor agent hit a session limit mid-GREEN (Task 2). Resumed inline: confirmed the uncommitted GREEN logic passed its 9 budget/kill-switch unit tests, diagnosed + fixed the cross-loop test-isolation regression, committed Task 2, then built Task 3 (admin router + functional test) from scratch. The api container needed a `docker compose restart api` (not just `up -d`, which is idempotent when config is unchanged) to load the new router and the lifespan Redis init.

## User Setup Required

None - no external service configuration required. (Provider API keys are only needed for the live parity test in plan 02-03.)

## Next Phase Readiness
- Plan 02-03 (cache + parity) builds on this: the cache lookup must run AFTER the kill-switch check (already the contract); a cache hit is $0 and must still be refused during a halt.
- PLAT-06 fully satisfied: budgets + hard kill-switch + per-operation cost logging (logging from 02-01) all in place.

---
*Phase: 02-llm-gateway*
*Completed: 2026-06-13*
