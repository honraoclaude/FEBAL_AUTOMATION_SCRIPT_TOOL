# Phase 2: LLM Gateway - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning

<domain>
## Phase Boundary

A single provider-agnostic LLM gateway that **every** future agent LLM call must route through — the money-control chokepoint built before any agent exists, so nothing can spend unmetered. Delivers PLAT-05 (provider-agnostic via `init_chat_model`, Anthropic↔OpenAI by config only) and PLAT-06 (per-call/per-run/per-day token+cost budgets, hard kill-switch, cost-per-operation logging, Redis response caching).

**In scope:** the gateway service/interface, budget enforcement, kill-switch, cost accounting + pricing, usage ledger, response caching, provider/model selection, and a verified two-provider parity run.
**Out of scope (own phases):** any actual agent (Explorer = Phase 4, generation = Phase 6, etc.), per-run UI controls / "stop this exploration" buttons (Phase 4/7), Elasticsearch-backed cost search (Phase 9/10 — emit logs now, index later), Prometheus dashboards (Phase 11 — emit metrics now).

</domain>

<decisions>
## Implementation Decisions

### Budget Enforcement
- **D-01:** Enforcement is **pre-check before spend** — the gateway estimates a call's cost BEFORE issuing it (estimated input tokens + max-output tokens against remaining budget) and **refuses** any call that would breach, so the platform never overspends even by a single call. Actual usage is reconciled against the estimate after the call returns (true cost recorded; counters corrected).
- **D-02:** A breach raises a typed error (e.g. `BudgetExceeded`) from the gateway — callers fail fast, not a silently-ignorable result object. (Combines the "pre-check" + "hard stop" intent: blocked before spend, surfaced as an exception.)
- **D-03:** Budgets are tracked in **both tokens and USD**; a limit can be set on either axis. USD caps are derived from the pricing table (D-08).
- **D-04:** Budget limits are **global env defaults** for all three scopes (per-call, per-run, per-day), with **per-run overrides** a caller may pass to tighten (never loosen beyond a hard global ceiling). Note: the `Target` model already carries `budget_overrides` (Phase 1, plan 01-05) — Phase 4 will feed those in as per-run overrides; the gateway must accept run-level budget params now.

### Kill-Switch
- **D-05:** Tripped **both ways** — a manual admin API endpoint (panic button) AND automatically when the per-day global budget is exhausted.
- **D-06:** **Global blast radius** — while active, every gateway call across every agent/run is refused immediately ("halts all LLM traffic"). No per-run kill in this phase (that's Phase 4/7 run-control).
- **D-07:** Kill-switch flag **and** the live rolling budget counters (per-run, per-day) live in **Redis** — shared across api/workers, survive api restarts, atomic increments, instantly visible everywhere. (Redis 8 already in the stack.)

### Cost Accounting & Storage
- **D-08:** Per-model prices come from a **versioned pricing table in config** (model → {input $, output $} with an **effective-date**, so historical cost rows stay accurate when prices change). Manually maintained; no runtime dependency on provider pricing APIs.
- **D-09:** Usage persists to **both** a durable **Postgres `llm_usage` ledger table** (one row per call: operation_type, run_id, provider, model, input/output tokens, cost, cache_hit, timestamp — queryable per operation via SQL now) **and** **structlog JSON** usage events (for Elasticsearch indexing in Phase 9/10). New Alembic migration chains after `0002_targets`.
- **D-10:** Every gateway call is tagged by the caller with an **`operation_type`** label (e.g. `explore.perceive`, `generate.gherkin`) and a **`run_id`**. Per-run budget binds to `run_id`; cost reports group by `operation_type`. The gateway **generates a `run_id`** if the caller supplies none.

### Cache & Model Selection
- **D-11:** Cache key = **hash(provider, model, full message list, call params)** where params include temperature/max_tokens/tools — exact match only, no false hits.
- **D-12:** Cache **only deterministic calls (temperature == 0)**; non-deterministic calls are never cached. Default TTL ~24h, **env-configurable**, plus a **per-call `no_cache` opt-out**. Cache stored in Redis. A cache hit costs $0 and is recorded with `cache_hit=true` in the ledger.
- **D-13:** A **global default model** (env) with a **per-call model override** — every gateway call may request a specific model string passed to `init_chat_model`, enabling future cost tiering (cheap model for classify, strong for generate) with no code change.

### Claude's Discretion
- Exact gateway interface/function signature (async method shape, where it lives — likely `app/services/llm_gateway.py` mirroring `target_service.py`), the token-estimation method for pre-check (provider tokenizer vs heuristic), retry/backoff specifics via `tenacity` (429/529), and whether LangSmith tracing is wired now (opt-in via env) or deferred — all left to research/planning, provided the locked decisions above hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Stack & decisions (locked technology — do not re-litigate)
- `CLAUDE.md` (Technology Stack → "Agent / LLM Layer") — `init_chat_model` is THE provider-agnostic layer (no custom adapter, no in-process LiteLLM); `langchain-anthropic` 1.4.x / `langchain-openai` 1.3.x provider packages; `tenacity` 9.1.x for 429/529 retries; `redis` 8.0.x for cache + counters; `langsmith` 0.8.x optional tracing; `prometheus-client` for cost gauges. Also the "What NOT to Use" row rejecting LiteLLM-under-LangChain.
- `.planning/REQUIREMENTS.md` — PLAT-05, PLAT-06 (the two requirements this phase closes).
- `.planning/ROADMAP.md` (Phase 2 success criteria) — the three TRUE-conditions: two-provider parity via config only; budgets stop execution + hard kill-switch; per-operation cost logging + Redis caching.

### Existing code this phase extends
- `apps/api/app/services/target_service.py` — service-layer pattern to mirror for the gateway service; also defines `Target.budget_overrides` consumed later as per-run budgets.
- `apps/api/app/core/config.py` — pydantic-settings `Settings` singleton; budget defaults, default model, kill-switch and cache TTL env vars are added here (env names are the contract).
- `apps/api/app/core/logging.py` — structlog config + `redact_sensitive` processor; usage events emit through this (prompts/credentials must never reach log sinks).
- `apps/api/app/db/{base,session}.py` + `apps/api/alembic/` — async SQLAlchemy Base + migration chain; `llm_usage` table + migration chains after `0002_targets`.

No external ADRs/specs beyond the above — requirements fully captured in the decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Service layer pattern** (`target_service.py`): the gateway is a service module (`app/services/llm_gateway.py`) with the encrypt-on-write/single-surface discipline already established for credentials.
- **pydantic-settings `Settings`** (`core/config.py`): one config class for compose + hybrid; add budget/model/cache/kill-switch env vars here.
- **structlog redaction** (`core/logging.py`): usage logging reuses the existing JSON + `redact_sensitive` chain — prompt text and any credential-shaped content must be redacted before logs.
- **Redis** (already in compose, `REDIS_URL` in settings): kill flag + atomic budget counters + response cache all land here. `redis.asyncio` is the client.
- **Async Alembic** (`alembic/env.py`, chain `0001_users` → `0002_targets`): `llm_usage` migration chains next.

### Established Patterns
- Functional tests hit the **live stack over HTTP** (D-02 from Phase 1); a two-provider parity test will need real API keys — plan for a gated/skippable integration test (keys via env, not committed) plus mock-level unit tests for budget/kill-switch/cache logic that need no provider.
- Secrets via env only; never literal in compose/code (Phase 1 threat model). Provider API keys (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) follow the same `.env`/`.env.example` contract.

### Integration Points
- `core/config.py` (new env vars), `alembic/versions/` (new `llm_usage` migration), `app/services/llm_gateway.py` (new), possibly an admin router for the kill-switch endpoint (`app/routers/`), and `app/main.py` (router include). All agents in Phases 3–9 import the gateway as their ONLY LLM path.

</code_context>

<specifics>
## Specific Ideas

- "Pre-check before spend" was chosen deliberately over post-hoc abort — the user wants a guarantee of *never* overspending, even by one call. Research must address: how to estimate cost before the response exists (output tokens unknown) — reserve against `max_tokens` at the call's price, reconcile to actual after.
- Kill-switch is a real **panic button** (manual admin endpoint) plus an automatic daily-budget tripwire — both must exist.
- Pricing table must be **effective-dated** so a price change doesn't rewrite the cost of historical operations.

</specifics>

<deferred>
## Deferred Ideas

- **Per-run kill / "stop this exploration" control** — raised under kill-switch scope; belongs to run-control in Phase 4 (Explorer) / Phase 7 (Execution), not this gateway phase.
- **Per-operation-type budget config** (distinct budgets per explore/generate/classify) — considered for budget config; deferred until those operations exist. The gateway's `operation_type` tagging (D-10) lays the groundwork.
- **Elasticsearch cost/usage search** — structured logs are emitted now (D-09); indexing/search is Phase 9/10.
- **Prometheus cost gauges / Grafana** — `prometheus-client` is in the stack; wiring dashboards is Phase 11. Emitting gauge values from the gateway now is acceptable if cheap, but not required this phase.

None of these block Phase 2 — discussion stayed within the gateway scope.

</deferred>

---

*Phase: 2-LLM Gateway*
*Context gathered: 2026-06-13*
