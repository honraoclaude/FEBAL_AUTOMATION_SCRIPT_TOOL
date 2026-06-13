---
phase: 02-llm-gateway
verified: 2026-06-13T23:05:00Z
status: passed
score: 3/3 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: none
human_verification:
  - test: "Two-provider live parity with REAL keys (tests/integration/test_llm_parity.py::test_two_provider_parity)"
    expected: "The same gateway complete() call returns a valid response with positive input/output tokens and non-zero cost from BOTH Anthropic and OpenAI, with only the model-config string changed. Test SKIPS cleanly when keys absent."
    why_human: "Requires real ANTHROPIC_API_KEY + OPENAI_API_KEY (small real spend); documented Manual-Only verification. Absence of a live run is EXPECTED per phase context — the mechanism is verified in code and the test is correctly structured + skippable."
---

# Phase 2: LLM Gateway Verification Report

**Phase Goal:** Every future LLM call flows through one provider-agnostic, budget-enforced gateway — no agent can spend money outside it
**Verified:** 2026-06-13T23:05:00Z
**Status:** passed (with one Manual-Only live-parity item, as designed)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (ROADMAP Success Criteria) | Status | Evidence |
|---|---|---|---|
| 1 | SC-1 (PLAT-05): Same gateway call runs against Anthropic and OpenAI by config only, via `init_chat_model`, no custom adapter | ✓ VERIFIED | `llm_gateway.py` `_invoke()` (L270-273) calls `init_chat_model(model_str, ...)` exclusively for the chat path; `complete()` accepts per-call `model` override (D-13, L296/321); `usage_metadata` read uniformly (L396-402). Parity test exists, `live_llm`-marked + skipif on missing keys; skips cleanly (1 skipped, 66 deselected). Unit `test_gateway_provider.py` proves provider switch by config alone (anthropic↔openai). NO custom adapter; `anthropic` SDK imported ONLY for `count_tokens` (L203-211, never chat). |
| 2 | SC-2 (PLAT-06): Per-call/per-run/per-day token+USD budgets stop execution when exceeded (pre-check before spend, raises BudgetExceeded); hard kill-switch halts all LLM traffic | ✓ VERIFIED | Pre-check (D-01) reserves est_in + max_tokens at model price BEFORE provider call (L361-389); refuses on first breach across all 3 scopes × 2 axes via `_check`/`_check_tok`; `BudgetExceeded` is a typed exception (L86). Tests assert provider NOT invoked + no ledger row on breach. Kill-switch checked FIRST (L331-334, raises `KillSwitchActive`); admin router `/api/admin/llm/killswitch` POST/DELETE/GET auth-gated at router level (401 unauth, verified functionally); daily-USD exhaustion auto-trips (L434-436). Counters + flag in Redis. |
| 3 | SC-3 (PLAT-06): Every LLM operation logs tokens+cost queryable per operation; Redis caching reduces repeat spend | ✓ VERIFIED | `LLMUsage` ledger (operation_type, run_id, provider, model, tokens, `cost_usd Numeric(12,6)`, cache_hit) — migration 0003 creates table + indexes on run_id/operation_type/created_at (queryable per operation, D-09/D-10). Functional `test_usage_ledger.py` SELECTs the real Postgres row. Structured usage event logs `tok_in`/`tok_out` (NOT [REDACTED]) — redaction-collision rename verified by `test_llm_log_safety.py` (asserts values != "[REDACTED]", no prompt/key leak). Custom Redis cache: temp==0 only (L343), $0 hit + `cache_hit=true` ledger row, budget untouched, kill-switch precedes cache (D-06). |

**Score:** 3/3 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `app/services/llm_gateway.py` | Provider-agnostic call + budgets + kill-switch + cache orchestration | ✓ VERIFIED | 550 lines; full 8-step orchestration; init_chat_model; pre-check/reconcile; BudgetExceeded/KillSwitchActive/MissingUsageMetadataError; cache; auto-trip. Wired: imported by admin_llm router + tests. |
| `app/routers/admin_llm.py` | Authenticated kill-switch endpoints | ✓ VERIFIED | POST/DELETE/GET under router-level `Depends(get_current_user)`; included in main.py (L62). |
| `app/models/llm_usage.py` | Ledger model (Numeric cost, cache_hit, run_id, operation_type) | ✓ VERIFIED | All required columns; Numeric(12,6) for money; indexed run_id/operation_type/created_at. |
| `app/core/llm_pricing.py` | Effective-dated pricing, fail-closed | ✓ VERIFIED | `PRICING` rows with `effective_date` (D-08); `lookup_price` normalizes provider-prefixed string, returns most-recent ≤ date; `UnknownModelPriceError` (fail-closed, no $0). |
| `alembic/versions/0003_llm_usage.py` | Migration chaining after 0002 | ✓ VERIFIED | down_revision='0002'; creates llm_usage table + 3 indexes. |
| `app/core/redis_client.py` | Lifespan-managed shared client | ✓ VERIFIED | `init_redis`/`close_redis` singleton; wired into main.py lifespan (L49/52). |
| `tests/integration/test_llm_parity.py` | live_llm-gated two-provider parity | ✓ VERIFIED | pytestmark live_llm + skipif on missing keys; no_cache=True forces real call on both; asserts uniform usage_metadata, positive tokens, non-zero cost, provider from config string. Skips cleanly. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| admin_llm router | main.py | `include_router(admin_llm_router)` | ✓ WIRED | L62 |
| gateway | init_chat_model | `_invoke()` ainvoke | ✓ WIRED | L272-273, sole chat path |
| gateway | Redis | `get_redis()` MGET/pipeline/GET | ✓ WIRED | counters + cache + killswitch flag |
| gateway | llm_usage ledger | `db.add(LLMUsage(...))` + commit | ✓ WIRED | both real-call (L439) and cache-hit (L501) paths |
| redis_client | main.py lifespan | `init_redis()`/`close_redis()` | ✓ WIRED | L49/52 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| llm_usage ledger | cost_usd, tokens | `usage_metadata` from provider, reconciled, `compute_cost()` | Yes — real usage_metadata; fails closed (MissingUsageMetadataError) if absent | ✓ FLOWING |
| budget counters | day/run usd+tok | Redis INCRBYFLOAT/INCRBY by ACTUAL usage (not reservation) | Yes — reconciled from real tokens | ✓ FLOWING |
| cache | content + token counts | Redis SETEX on miss+success, served on hit | Yes — real serialized response | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full non-live suite green | `uv run pytest tests -m "not live_llm" -q` | 66 passed, 1 deselected (56s) | ✓ PASS |
| Live parity skips without keys | `uv run pytest -m live_llm -q` | 1 skipped, 66 deselected (1.5s) | ✓ PASS |
| No debt markers in shipped code | grep TBD/FIXME/XXX on phase files | none found | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| PLAT-05 | 02-01, 02-03 | Provider-agnostic gateway, Anthropic/OpenAI by config only | ✓ SATISFIED | init_chat_model sole chat path; per-call override; parity test; marked Complete in REQUIREMENTS.md L16/138, backed by code |
| PLAT-06 | 02-02, 02-03 | Per-call/run/day token+cost budgets, hard kill-switch, cost-per-operation logging | ✓ SATISFIED | pre-check/reconcile; admin kill-switch + auto-trip; ledger + structured event; cache; marked Complete in REQUIREMENTS.md L17/139, backed by code |

### Locked CONTEXT Decisions Spot-Check (D-01..D-13)

| Decision | Status | Evidence |
|---|---|---|
| D-01 pre-check before spend | ✓ | Reserve (est_in + max_tokens) checked before `_invoke`; reconcile by actual usage |
| D-02 typed BudgetExceeded, no spend/ledger on breach | ✓ | Exception raised before provider; tests assert no provider call, no ledger row |
| D-05 kill-switch both ways (admin + auto) | ✓ | Admin router + daily-USD auto-trip (L434-436) |
| D-06 kill-switch precedes cache (global blast radius) | ✓ | Kill check L331 before cache lookup L349; `test_killswitch_precedes_cache` proves halt refuses would-be hit |
| D-08 effective-dated pricing | ✓ | `effective_date` on PriceRow; lookup returns most-recent ≤ date |
| D-09 ledger + structlog event | ✓ | Postgres row + redaction-safe JSON event |
| D-10 operation_type + run_id tagging, run_id generated if absent | ✓ | Required `operation_type` arg; `run_id = run_id or uuid.uuid4().hex` |
| D-12 cache temp==0 only | ✓ | `cacheable = temperature == 0 and not no_cache`; `test_no_cache_paths` proves temp>0 never caches |
| D-13 default model + per-call override | ✓ | `model or settings.llm_default_model`; per-call override switches provider |

No locked decision is contradicted by the shipped code.

### Anti-Patterns Found

None. No TBD/FIXME/XXX/PLACEHOLDER markers in phase files. The "V4 GAP" comment in admin_llm.py is a documented, intentional scope deferral (Admin-role restriction → Phase 10 RBAC; auth gate is the current control) — not an unreferenced debt marker.

### Human Verification Required

#### 1. Two-Provider Live Parity Proof (Manual-Only, by design)

**Test:** Set real `ANTHROPIC_API_KEY` + `OPENAI_API_KEY` in `.env`, run `cd apps/api && uv run pytest -m live_llm -q`
**Expected:** `test_two_provider_parity` passes — same gateway call returns valid response with positive input/output tokens and non-zero cost from BOTH providers, only the model-config string changed.
**Why human:** Requires real provider keys and incurs small real spend (< $0.01). This is the documented Manual-Only verification in 02-VALIDATION.md. Per phase context (02-CONTEXT.md), absence of a live run is EXPECTED — keys are not necessarily added. The provider-agnostic mechanism is verified in code (init_chat_model, no adapter, uniform usage_metadata) and the test is correctly structured and skips cleanly. This item does NOT block the phase goal; it is the live confirmation of a mechanism already proven structurally.

### VALIDATION.md Check

`nyquist_compliant: true`, `wave_0_complete: true`; Per-Task Verification Map is fully filled (8 tasks across 3 plans, each mapped to PLAT-05/06, test type, automated command, file-exists, status). End-of-phase Nyquist flip timing documented. Sign-off approved. ✓

### Gaps Summary

No gaps. All three ROADMAP success criteria are observably true in the actual codebase, backed by substantive (non-hollow) tests that assert real behaviors: pre-check refuses before spend, kill-switch halts all traffic and precedes cache, ledger persists queryable cost-per-operation, cache hits cost $0 without touching budget, and the provider-agnostic mechanism uses `init_chat_model` with no custom adapter. The full non-live suite is green (66 passed). PLAT-05 and PLAT-06 are marked Complete in REQUIREMENTS.md and the claims are backed by code.

The single live-parity proof requires real API keys and is the documented Manual-Only verification — its absence is expected and does not block the phase goal, since the parity mechanism is verified structurally and the test is correctly gated and skippable.

---

_Verified: 2026-06-13T23:05:00Z_
_Verifier: Claude (gsd-verifier)_
