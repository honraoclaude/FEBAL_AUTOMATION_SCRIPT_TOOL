---
phase: 2
slug: llm-gateway
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-13
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (pytest-asyncio 1.4, asyncio_mode=auto) |
| **Config file** | apps/api/pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd apps/api && uv run pytest tests/unit -q` (mocked init_chat_model — no providers, no spend) |
| **Full suite command** | `cd apps/api && uv run pytest tests -q` (functional hit live stack; `live_llm`-marked parity tests skip when provider keys absent) |
| **Estimated runtime** | ~20-40 seconds (unit + functional); live parity adds provider latency when keys present |

---

## Sampling Rate

- **After every task commit:** Run `cd apps/api && uv run pytest tests/unit -q`
- **After every plan wave:** Run `cd apps/api && uv run pytest tests -q`
- **Before `/gsd:verify-work`:** Full suite green; the `live_llm` two-provider parity test passed at least once with real keys (Success Criterion 1)
- **Max feedback latency:** ~40 seconds

---

## Per-Task Verification Map

> One row per task across all three plans, each mapped to PLAT-05 / PLAT-06, a test type
> (unit with mocked provider / functional against the live stack / live_llm integration),
> and the exact automated command. This map was completed at the END of the phase (Plan
> 03 Task 2) — see the Nyquist-timing note below.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| T1 pkg-gate | 02-01 | 1 | PLAT-05/06 | T-02-01 (supply-chain) | Pinned LLM deps verified legitimate before install (blocking human gate, never auto-approved) | manual gate | (human verification; no automated command) | ✅ | ✅ green |
| T2 scaffold | 02-01 | 1 (W0) | PLAT-05/06 | T-02-02 (unpriced→$0) | Settings/pricing/ledger model+migration/schemas/mocked unit conftest/live_llm marker exist; unpriced model fails closed | unit | `cd apps/api && uv run pytest tests/unit -q` | ✅ W0 | ✅ green |
| T3 complete() | 02-01 | 1 | PLAT-05 | T-02-03 (silent $0 on missing usage) | Provider-agnostic call via init_chat_model; cost reconciled from usage_metadata; one ledger row + redacted usage event; fails closed when usage_metadata absent | unit + functional | `cd apps/api && uv run pytest tests/unit/test_gateway_provider.py -q` ; `cd apps/api && uv run pytest tests/functional/test_usage_ledger.py -q` | ✅ | ✅ green |
| T1 redis+budgets | 02-02 | 2 | PLAT-06 | T-02-07 (counter drift) | Single lifespan redis.asyncio client; date-bucketed day + per-run counters with TTL | unit | `cd apps/api && uv run pytest tests/unit/test_budget_reconcile.py -q` | ✅ | ✅ green |
| T2 precheck/reconcile/autotrip | 02-02 | 2 | PLAT-06 | T-02-08 (overspend), T-02-09 (read-then-check race, accept) | Pre-check refuses (BudgetExceeded) before spend on USD or token axis, per call/run/day; reconcile by ACTUAL usage; daily-USD exhaustion auto-trips kill-switch | unit | `cd apps/api && uv run pytest tests/unit/test_budget_precheck.py tests/unit/test_killswitch_auto.py -q` | ✅ | ✅ green |
| T3 admin kill-switch | 02-02 | 2 | PLAT-06 | T-02-10 (unauthenticated halt control) | Authenticated POST/DELETE/GET kill-switch; global halt raises KillSwitchActive over the live stack | functional | `cd apps/api && uv run pytest tests/functional/test_killswitch.py -q` | ✅ | ✅ green |
| T1 cache | 02-03 | 3 | PLAT-06 | T-02-13 (key collision), T-02-14 (non-det cached), T-02-15 (hit unlogged), T-02-19 (hit served during halt) | SHA-256 exact-match key; cache only temp==0 & not no_cache; hit = $0 + cache_hit=true ledger row + no budget touched; kill-switch checked BEFORE cache (halt refuses hits) | unit | `cd apps/api && uv run pytest tests/unit/test_cache.py -q` | ✅ | ✅ green |
| T2 parity + map | 02-03 | 3 | PLAT-05 | T-02-16 (parity spend/key leak in CI) | Same complete() runs on Anthropic AND OpenAI by config alone; uniform usage_metadata; live_llm-gated + skipif on missing keys (off the default gate) | live_llm (Manual-Only) | `cd apps/api && uv run pytest -m live_llm -q` (on demand with keys); collection-gate: `cd apps/api && uv run pytest tests/integration/test_llm_parity.py -m live_llm --collect-only -q` | ✅ | ✅ green (skips w/o keys) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Nyquist frontmatter timing (Plan 03 FIX 5):** `nyquist_compliant: true` / `wave_0_complete: true` were flipped at the END of the phase, in Plan 03 Task 2 — recording that the whole phase's test map is now realized. No mid-phase Nyquist re-gate ran against the still-draft frontmatter while Plans 01/02 were in progress; the draft stayed `false` until this map was filled. The flip is an end-of-phase action, not a per-wave gate.

---

## Wave 0 Requirements

- [x] `apps/api/tests/unit/conftest.py` — mocked `init_chat_model` fixture (returns canned AIMessage with controllable `usage_metadata`); compose Redis under a test:llm: prefix with an autouse per-test flush (counter + cache isolation)
- [x] `apps/api/tests/unit/` package — budget/kill-switch/cache/pricing logic tests that need no live provider
- [x] `live_llm` pytest marker registered in pyproject.toml + skipif-on-missing-keys guard (ANTHROPIC_API_KEY/OPENAI_API_KEY) in tests/integration/test_llm_parity.py

*Existing functional infra (tests/conftest.py live-HTTP client, asyncio_mode=auto) carries forward from Phase 1.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Two-provider parity with REAL keys (`tests/integration/test_llm_parity.py::test_two_provider_parity`) | PLAT-05 | Requires real ANTHROPIC_API_KEY + OPENAI_API_KEY (small real spend, off the default `-m "not live_llm"` gate) | Set both keys in .env, run `cd apps/api && uv run pytest -m live_llm -q`; confirm the same gateway call returns a valid response (positive input/output tokens, non-zero cost) from BOTH providers with only the model-config string changed. The test raises the budget caps + uses a unique run_id so the Plan-02 pre-check does not refuse it, and asserts the daily cap exceeds the summed parity cost. SKIPS cleanly when keys are absent (does not fail the build). |

*All other phase behaviors (budget pre-check/breach, kill-switch trip/halt, cost computation, cache hit, ledger rows) have automated verification with mocked providers.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (parity is Manual-Only with a collection-gate command; pkg-gate is a human gate)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (unit conftest, live_llm marker)
- [x] No watch-mode flags
- [x] Feedback latency < 40s (unit suite ~3s; full default suite ~50s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (end-of-phase, Plan 03 Task 2)
