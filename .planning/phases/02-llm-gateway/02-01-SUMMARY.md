---
phase: 02-llm-gateway
plan: 01
subsystem: api
tags: [langchain, init_chat_model, llm-gateway, pricing, ledger, structlog, alembic, tenacity]

# Dependency graph
requires:
  - phase: 01-foundation-dev-environment
    provides: "Settings singleton, async SQLAlchemy Base/session, alembic chain (0001→0002), structlog redaction, live compose stack (Postgres/Redis/api)"
provides:
  - "Provider-agnostic llm_gateway.complete() — the single metered LLM call path every future agent imports"
  - "Effective-dated pricing table (lookup_price + compute_cost) with provider-prefix normalization (_bare_model)"
  - "llm_usage Postgres ledger (model + migration 0003) — one immutable cost row per call"
  - "Redaction-safe usage structlog event (tok_in/tok_out) — real integer counts, no prompt/key leakage"
  - "Wave-0 mocked unit scaffold (fake_chat_model, redis_test) + live_llm marker"
  - "LLM env contract: LLM_DEFAULT_MODEL + provider keys in .env.example and compose api service"
affects: [budget-enforcement, kill-switch, response-cache, explorer, generation, healing, defect-agent]

# Tech tracking
tech-stack:
  added: [langchain==1.*, langchain-anthropic==1.4.*, langchain-openai==1.3.*, tenacity==9.1.*, tiktoken==0.13.*, anthropic==0.109.*, langsmith==0.8.*]
  patterns:
    - "init_chat_model(provider:model) for provider-agnostic instantiation; uniform usage_metadata read"
    - "tenacity retry(retry_if_exception_type(TransientProviderError), wait_exponential, stop_after_attempt(4)) around ainvoke"
    - "Effective-dated pricing keyed on BARE model name; lookup normalizes provider-prefixed input"
    - "Fail-closed cost accounting: unpriced model / missing usage_metadata raises, never logs $0"
    - "Redaction-collision-safe log keys: tok_in/tok_out avoid the SENSITIVE 'token' substring"
    - "In-container functional driver (docker compose exec api uv run python) for live-stack gateway tests"

key-files:
  created:
    - apps/api/app/core/llm_pricing.py
    - apps/api/app/models/llm_usage.py
    - apps/api/app/schemas/llm.py
    - apps/api/app/services/llm_gateway.py
    - apps/api/alembic/versions/0003_llm_usage.py
    - apps/api/tests/unit/conftest.py
    - apps/api/tests/unit/test_pricing.py
    - apps/api/tests/unit/test_gateway_provider.py
    - apps/api/tests/functional/test_usage_ledger.py
    - apps/api/tests/functional/test_llm_log_safety.py
  modified:
    - apps/api/app/core/config.py
    - apps/api/app/main.py
    - apps/api/pyproject.toml
    - .env.example
    - infra/docker-compose.yml

key-decisions:
  - "Usage-event count keys are tok_in/tok_out (NOT tokens_in/tokens_out) — the plan's prescribed names still contain the 'token' substring and would be [REDACTED] by the unchanged SENSITIVE regex"
  - "LLM_DEFAULT_MODEL is a required setting (no default), so compose api env + .env.example carry it (and the optional provider keys) to keep the stack bootable"
  - "Functional gateway tests drive complete() inside the live api container via docker compose exec + uv run python (no HTTP route exists this slice — Plan 02); ledger read back over host asyncpg DSN"
  - "Seeded pricing rows: claude-sonnet-4-5 ($3/$15 per Mtok) and gpt-4.1 ($2/$8 per Mtok), effective 2026-01-01"

patterns-established:
  - "Provider-prefix normalization lives once, in lookup_price (_bare_model); call sites pass the full prefixed model_str"
  - "Money is Decimal/Numeric(12,6) end-to-end; compute_cost quantizes to 6 places"
  - "Mocked unit suite (fake_chat_model) inverts Phase-1 live-only philosophy for zero-spend logic tests"

requirements-completed: [PLAT-05]

# Metrics
duration: ~40min
completed: 2026-06-13
---

# Phase 2 Plan 01: LLM Gateway Slice 1 Summary

**Provider-agnostic `complete()` routing through `init_chat_model`, reconciling USD cost from an effective-dated pricing table, writing one immutable `llm_usage` ledger row, and emitting a redaction-safe usage event with real integer token counts.**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-06-13T16:20Z
- **Completed:** 2026-06-13T16:40Z
- **Tasks:** 3 (Task 1 package gate pre-approved)
- **Files modified/created:** 15

## Accomplishments
- `complete()` selects provider/model by config string (settings default or per-call override) and reads `usage_metadata` uniformly across providers.
- Effective-dated pricing with provider-prefix normalization — a real `anthropic:claude-...` string resolves to the bare-keyed price row (FIX-1), so priced calls cost correctly instead of fail-closing.
- Every non-cached call writes exactly one `llm_usage` row (queryable by `operation_type`/`run_id`) with `Numeric(12,6)` cost; migration `0003` applied to head.
- Fail-closed accounting: unpriced model and missing `usage_metadata` both raise and write no ledger row — never log $0.
- Redaction collision genuinely resolved and proven by a live log-safety test: counts log as integers under `tok_in`/`tok_out`; the `SENSITIVE` regex is unchanged.

## Task Commits

1. **Task 1: Package-legitimacy gate (pre-approved "Approve all")** - `2372a6f` (chore)
2. **Task 2: Wave-0 scaffold (settings, pricing, ledger, schemas, mocked conftest)** - `8e64bf4` (feat)
3. **Task 3: Gateway complete() — TDD**
   - RED: `e9691ec` (test) — failing unit tests
   - GREEN: `6f1e31b` (feat) — implementation + functional tests

_No REFACTOR commit needed (code clean, ruff green)._

## Files Created/Modified
- `apps/api/app/services/llm_gateway.py` - `complete()` entry point, `_invoke` (tenacity), `TransientProviderError`/`MissingUsageMetadataError`, redaction-safe usage event
- `apps/api/app/core/llm_pricing.py` - `PriceRow`, `PRICING`, `_bare_model`, `lookup_price`, `compute_cost`, `UnknownModelPriceError` (no logger)
- `apps/api/app/models/llm_usage.py` - `LLMUsage` ledger model (Numeric cost, no prompt/response columns)
- `apps/api/alembic/versions/0003_llm_usage.py` - `llm_usage` table, `down_revision='0002'`
- `apps/api/app/schemas/llm.py` - `LLMResult` return shape + `KillSwitchRequest` (Plan 02 contract)
- `apps/api/app/core/config.py` - `llm_default_model`, provider keys, langsmith env-gated fields
- `apps/api/app/main.py` - import `LLMUsage` on the metadata path for Alembic discovery
- `apps/api/tests/unit/conftest.py` - `fake_chat_model` + `redis_test` fixtures (no fakeredis)
- `apps/api/tests/unit/{test_pricing,test_gateway_provider}.py` - mocked unit coverage
- `apps/api/tests/functional/{test_usage_ledger,test_llm_log_safety}.py` - in-container live-stack coverage
- `apps/api/pyproject.toml` - LLM-layer deps + `live_llm` marker
- `.env.example`, `infra/docker-compose.yml` - LLM env contract (model required; keys empty)

## Decisions Made
- `tok_in`/`tok_out` log keys (see Deviations Rule 1).
- `LLM_DEFAULT_MODEL` required → wired into compose env and `.env.example` (Rule 3).
- In-container `docker compose exec ... uv run python` driver for functional gateway tests (no HTTP route this slice).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Usage-event token keys renamed tok_in/tok_out (plan's tokens_in/tokens_out still collide)**
- **Found during:** Task 3 (GREEN, log-safety functional test)
- **Issue:** The plan prescribed logging counts under `tokens_in`/`tokens_out` "which the regex does NOT match." But `core/logging.py`'s `SENSITIVE` regex matches the SUBSTRING `token`, and `tokens_in` contains `token` — so those keys rendered `[REDACTED]`. The log-safety test caught this concretely (`assert '[REDACTED]' == 4242`).
- **Fix:** Renamed the usage-event count keys to `tok_in`/`tok_out` (no forbidden substring). `SENSITIVE` regex left unchanged (real credentials still redact); DB columns keep `input_tokens`/`output_tokens` (columns are not log keys). Updated `test_llm_log_safety.py` assertions accordingly.
- **Files modified:** apps/api/app/services/llm_gateway.py, apps/api/tests/functional/test_llm_log_safety.py
- **Verification:** Live log-safety test passes; manual in-container smoke shows `"tok_in": 7, "tok_out": 3` (integers, not redacted).
- **Committed in:** `6f1e31b` (Task 3 GREEN)

**2. [Rule 3 - Blocking] LLM_DEFAULT_MODEL wired into compose env + .env to keep the stack bootable**
- **Found during:** Task 2
- **Issue:** `llm_default_model: str` is a required Settings field (per plan interfaces). The api container enumerates env vars explicitly in compose (it does not pass the whole `.env`), so the container failed to instantiate `Settings()` (`Field required: llm_default_model`) on recreate — the api became unhealthy.
- **Fix:** Added `LLM_DEFAULT_MODEL` (+ optional `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`LANGSMITH_*`) to the compose api `environment:` block and to local `.env`/`.env.example`. Keys are empty placeholders (never literal secrets).
- **Files modified:** infra/docker-compose.yml, .env.example (and local .env, gitignored)
- **Verification:** `docker compose up -d api` → container healthy; full functional suite (46 tests) green.
- **Committed in:** `8e64bf4` (Task 2)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both essential for correctness/operability. The Rule 1 fix is the very redaction-collision the plan flagged as mandatory — the plan's chosen key names were themselves insufficient. No scope creep.

## Issues Encountered
- `docker compose exec api python` runs the system Python (no deps); the container runs via `uv run`. Switched the functional driver to `docker compose exec api uv run python -c`.
- The in-container `exec` process is separate from uvicorn, so its structlog event does not reach `docker compose logs api`. The log-safety test instead captures the driver's own configured structlog stream (same JSON+redaction chain, real container runtime) — the live-stack equivalent of an api-process emission given no gateway HTTP route exists this slice.

## User Setup Required
None required for this slice — unit tests mock `init_chat_model` (no provider keys, no spend). Real `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` are needed only for the live parity test in Plan 02-03 (`.env.example` documents the placeholders).

## Next Phase Readiness
- The single LLM call path + cost-accounting spine is in place; Plan 02 (budget pre-check + kill-switch) and Plan 03 (Redis cache + live parity) layer on top via the named seams (`no_cache`, `cache_hit`, accepted but not yet enforced).
- Pricing table seeded with two rows; add new effective-dated rows (never edit old) when provider prices change.
- RAM blocker (Phase 3+) does not bite this phase — no new heavy services added.

## Threat Flags
None — no security surface introduced beyond the plan's threat register (no new endpoints; gateway is service-internal this slice).

## Self-Check: PASSED

All 11 created files exist on disk; all 4 task commits (`2372a6f`, `8e64bf4`, `e9691ec`, `6f1e31b`) are present in git history. Full suite green: 13 unit + 46 (`-m "not live_llm"`) tests pass; `alembic current` = `0003 (head)`.

---
*Phase: 02-llm-gateway*
*Completed: 2026-06-13*
