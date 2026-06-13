# Phase 2: LLM Gateway - Research

**Researched:** 2026-06-13
**Domain:** Provider-agnostic LLM gateway (LangChain `init_chat_model`), budget enforcement + kill-switch (Redis atomics), cost accounting (effective-dated pricing + Postgres ledger), response caching (Redis)
**Confidence:** HIGH (stack locked in CLAUDE.md; APIs verified against PyPI + LangChain reference docs)

## Summary

This phase builds the single money-control chokepoint every future agent LLM call routes through. The stack is fully locked by CLAUDE.md (`init_chat_model` as THE provider-agnostic layer — no custom adapter, no LiteLLM under LangChain; `tenacity` for retries; `redis` 8 for counters/cache/kill-switch; Postgres ledger; structlog usage events). The research job here is the **HOW**, not the WHAT: how to instantiate providers by config string, read uniform `usage_metadata`, estimate input tokens *before* the call for the pre-check (D-01), reserve against `max_tokens` and reconcile to actual, drive atomic Redis budget counters with a date-bucketed daily key, and cache deterministic calls in a way that still logs `cache_hit=true` and charges $0.

The single most consequential design call is the **cache**: LangChain's native global cache (`set_llm_cache` + `RedisCache`) is transparent and global — a cache hit returns silently with **no signal** to the caller, so the gateway cannot record `cache_hit=true` in the ledger (D-12) nor cleanly skip budget accounting. **Recommendation: a custom Redis cache wrapper inside the gateway** (deterministic SHA-256 key over provider+model+messages+params, `redis.asyncio` GET/SETEX), which composes with the ledger and budget logic. This is consistent with CLAUDE.md (it lists `redis` for "cache + distributed locks + rate limiting" — not a LangChain global cache).

**Primary recommendation:** Build `app/services/llm_gateway.py` mirroring `target_service.py`: a single async `complete(...)` entry point that runs (1) kill-switch check → (2) pre-check estimate vs Redis budget counters → (3) cache lookup → (4) `init_chat_model(...).ainvoke(...)` with tenacity retry → (5) cost reconciliation from `usage_metadata` + effective-dated pricing → (6) atomic counter increment + Postgres ledger row + structlog event. Provider/model come from settings with a per-call override string passed straight to `init_chat_model`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Provider instantiation (Anthropic/OpenAI by config) | API service (`llm_gateway.py`) | — | `init_chat_model` is in-process; provider is a config string, not a network tier |
| Token pre-estimate (input) | API service | Provider SDK / tiktoken | Anthropic `count_tokens` is a cheap API call; OpenAI uses local tiktoken |
| Budget counters + kill-switch flag | Redis | — | Shared across api/workers, atomic, survives api restart (D-07) |
| Cost calculation | API service | config pricing table | Pure function of `usage_metadata` + effective-dated rates (D-08) |
| Durable usage ledger | PostgreSQL (`llm_usage`) | structlog → ES (Phase 9/10) | SQL-queryable per operation now; ES indexing deferred (D-09) |
| Response cache | Redis | — | Deterministic-call cache, TTL'd, per-call opt-out (D-11/D-12) |
| Kill-switch admin endpoint | API router (`/api/admin/...`) | Redis | Panic button writes the Redis flag (D-05) |

## User Constraints (from CONTEXT.md)

### Locked Decisions (research the HOW, do not re-decide the WHAT)

- **D-01 Pre-check before spend:** estimate cost BEFORE the call (estimated input tokens + max-output tokens at the model's price) vs remaining budget; refuse if it would breach; reconcile actual usage after the call returns (true cost recorded; counters corrected).
- **D-02:** A breach raises a typed `BudgetExceeded` error from the gateway — callers fail fast, not a silently-ignorable result object.
- **D-03:** Budgets tracked in BOTH tokens and USD; a limit can be set on either axis. USD caps derived from the pricing table (D-08).
- **D-04:** Budget limits are global env defaults for all three scopes (per-call, per-run, per-day), with per-run overrides a caller may pass to tighten (never loosen beyond a hard global ceiling). `Target.budget_overrides` (Phase 1) feeds these in Phase 4; the gateway must accept run-level budget params now.
- **D-05:** Kill-switch tripped BOTH ways — manual admin API endpoint AND automatically when the per-day global budget is exhausted.
- **D-06:** Global blast radius — while active, every gateway call across every agent/run is refused immediately. No per-run kill this phase.
- **D-07:** Kill-switch flag AND live rolling budget counters (per-run, per-day) live in Redis.
- **D-08:** Per-model prices from a versioned, effective-dated pricing table in config (model → {input $, output $} with effective_date). Manually maintained; no runtime dependency on provider pricing APIs.
- **D-09:** Usage persists to BOTH a Postgres `llm_usage` ledger table (one row per call) AND structlog JSON usage events. New Alembic migration chains after `0002_targets`.
- **D-10:** Every call tagged with `operation_type` + `run_id`. Per-run budget binds to `run_id`; reports group by `operation_type`. Gateway generates `run_id` if caller supplies none.
- **D-11:** Cache key = hash(provider, model, full message list, call params incl. temperature/max_tokens/tools) — exact match only.
- **D-12:** Cache only deterministic calls (temperature == 0); default TTL ~24h env-configurable; per-call `no_cache` opt-out; Redis-backed; cache hit = $0 + `cache_hit=true` in ledger.
- **D-13:** Global default model (env) + per-call model override string passed to `init_chat_model`.

### Claude's Discretion
- Exact gateway interface/function signature (async method shape; likely `app/services/llm_gateway.py` mirroring `target_service.py`).
- Token-estimation method for the pre-check (provider tokenizer vs heuristic).
- Retry/backoff specifics via `tenacity` (429/529).
- Whether LangSmith tracing is wired now (opt-in via env) or deferred.

### Deferred Ideas (OUT OF SCOPE)
- Per-run kill / "stop this exploration" control → Phase 4/7 run-control.
- Per-operation-type budget config (distinct budgets per explore/generate/classify) → deferred until those operations exist; the `operation_type` tagging lays the groundwork.
- Elasticsearch cost/usage search → structured logs emitted now; indexing/search is Phase 9/10.
- Prometheus cost gauges / Grafana → Phase 11 (emitting gauge values now is acceptable if cheap, not required).

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAT-05 | All agent LLM calls route through a provider-agnostic gateway that works with Anthropic or OpenAI via configuration only | `init_chat_model("anthropic:..." / "openai:...")`; provider/model from settings + per-call override; uniform `usage_metadata` read (Pattern 1, Code Examples) |
| PLAT-06 | Gateway enforces per-call/per-run/per-day token/cost budgets with a hard kill-switch, logs cost per operation | Redis atomic counters + date-bucketed daily key + kill-switch flag (Pattern 3); pre-check/reconcile (Pattern 2); effective-dated pricing → cost (Pattern 4); Postgres `llm_usage` ledger + structlog (Pattern 5); Redis cache (Pattern 6) |

## Project Constraints (from CLAUDE.md)

- **LLM layer is LOCKED.** Use `init_chat_model` (LangChain) as the provider-agnostic layer. Do NOT add a custom adapter over the `anthropic`/`openai` SDKs for the *chat* path, and do NOT put LiteLLM under LangChain (explicit "What NOT to Use" row).
- `langchain-anthropic` and `langchain-openai` are the provider packages consumed by `init_chat_model`.
- `tenacity` is the retry library for 429/529 provider errors (exponential backoff).
- `redis` 8.x with built-in `redis.asyncio` for cache + counters + locks. `aioredis` is dead — do not use it.
- `langsmith` is the optional tracing layer (one env var enables it).
- `prometheus-client` for cost gauges (wiring deferred to Phase 11).
- Secrets via env only; never literal in compose/code. `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` follow the `.env`/`.env.example` contract.
- structlog redaction (`redact_sensitive`) is PLAT-07 control #1 — prompt text and credential-shaped content must never reach a log sink.
- **Version note (discrepancy flagged):** CLAUDE.md (queried 2026-06-12) lists `langchain 1.4.x` and `langchain-anthropic 1.4.x`. As of 2026-06-13 PyPI shows the `langchain` meta-package latest at **1.3.9** while `langchain-core` is at **1.4.7**. The `init_chat_model` symbol is exported from the `langchain` package (`from langchain.chat_models import init_chat_model`). Plan should pin `langchain` to whatever line is current at install time and let `uv` resolve `langchain-core` 1.4.x transitively. See Open Questions Q1.

## Standard Stack

### Core (already installed — Phase 1)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| redis | 8.0.* | Budget counters, kill-switch flag, response cache | Already in pyproject; `redis.asyncio` built in |
| sqlalchemy[asyncio] | 2.0.* | `llm_usage` ORM model | Established async pattern |
| alembic | 1.18.* | `llm_usage` migration chaining after 0002 | Established chain |
| structlog | 26.* | Usage events (redacted) | PLAT-07 logging chain |
| pydantic-settings | 2.14.* | Budget/model/cache/kill-switch env vars | `Settings` singleton (config.py) |
| pydantic | 2.13.* | Pricing-table model, request/response schemas | Established |

### Supporting (NEW — locked by CLAUDE.md, not yet installed)
| Library | Version (verified PyPI 2026-06-13) | Purpose | When to Use |
|---------|------------------------------------|---------|-------------|
| langchain | 1.x (latest meta-pkg 1.3.9; pin `1.*`) | Exports `init_chat_model` | The provider-agnostic entry point |
| langchain-core | 1.4.7 (resolve transitively) | `AIMessage.usage_metadata`, message types, `set_llm_cache` (unused) | Pulled by langchain |
| langchain-anthropic | 1.4.6 | Anthropic provider for `init_chat_model` | Anthropic path |
| langchain-openai | 1.3.2 | OpenAI provider for `init_chat_model` | OpenAI path |
| tenacity | 9.1.4 | Retry 429/529 with exp backoff | Around `ainvoke` |
| langsmith | 0.8.* (optional) | Tracing (env-gated) | Discretion: wire now opt-in or defer |

### Supporting (NEW — token estimation; [ASSUMED], see Package Legitimacy Audit)
| Library | Version (verified PyPI 2026-06-13) | Purpose | When to Use |
|---------|------------------------------------|---------|-------------|
| tiktoken | 0.13.0 | Local input-token count for **OpenAI** models (pre-check D-01) | OpenAI pre-estimate; no live call needed |
| anthropic | 0.109.1 | `client.beta.messages.count_tokens(...)` for **Anthropic** input-token count | Anthropic pre-estimate (one cheap API call) |
| langchain-redis | 0.2.5 | OPTIONAL — only if you choose native `RedisCache` over the custom wrapper (NOT recommended, see D-12 analysis) | Skip — custom wrapper recommended |

> `tiktoken` and `anthropic` are the recommended pre-check tokenizers. The chat path itself never imports the `anthropic`/`openai` SDKs directly (that would violate CLAUDE.md) — `anthropic` is used ONLY for its `count_tokens` helper, which has no chat-adapter equivalent in LangChain that avoids a live call. See Open Questions Q2 for a heuristic-only fallback that avoids both new packages.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom Redis cache wrapper | `set_llm_cache(RedisCache(...))` (langchain-redis) | Native cache is global + transparent: a hit returns silently with NO caller signal, so you cannot set `cache_hit=true` (D-12) or cleanly skip budget accounting. **Rejected.** |
| `anthropic.count_tokens` + `tiktoken` | Heuristic char/4 estimate | Heuristic avoids 2 new deps + an extra Anthropic round-trip per call, but over/under-estimates; pre-check (D-01) becomes looser. Acceptable MVP fallback if package gate is a concern (Q2). |
| `BaseChatModel.get_num_tokens()` | (LangChain built-in) | Exists but for Anthropic it proxies to the same count-tokens API and for OpenAI uses tiktoken internally — using it ties estimation to model instantiation; direct tiktoken/SDK gives clearer control. Reasonable either way. |
| Per-call fresh `init_chat_model` | Cached/configurable model instance | A single configurable instance (`configurable_fields=("model","temperature","max_tokens")`) lets per-call override via `config={"configurable": {...}}` without re-instantiation. Minor; either works. |

**Installation (planner to gate behind `checkpoint:human-verify` per package legitimacy):**
```bash
# Locked LLM layer (CLAUDE.md) + retries
uv add "langchain==1.*" "langchain-anthropic==1.4.*" "langchain-openai==1.3.*" "tenacity==9.1.*"
# Optional tracing
uv add "langsmith==0.8.*"
# Pre-check tokenizers ([ASSUMED] — gate before install)
uv add "tiktoken==0.13.*" "anthropic==0.109.*"
```

**Version verification (run before pinning — registry versions move):**
```bash
pip index versions langchain langchain-core langchain-anthropic langchain-openai tenacity tiktoken anthropic
```

## Package Legitimacy Audit

> slopcheck install/run was DENIED by the environment sandbox (running an agent-chosen, non-manifest package was blocked — itself the supply-chain-safe outcome). Per the graceful-degradation rule, every NEW package below is tagged `[ASSUMED]` and the planner MUST gate each install behind a `checkpoint:human-verify` task. Registry existence + long, monotonic version history were confirmed via `pip index versions` (a slopsquat would not have years of releases), but registry existence alone is not `[VERIFIED]`.

| Package | Registry | Version history depth | Source Repo | slopcheck | Disposition |
|---------|----------|----------------------|-------------|-----------|-------------|
| langchain | PyPI | 1.3.9 latest, long history back to 0.0.1 | github.com/langchain-ai/langchain | unavailable | [ASSUMED] — locked by CLAUDE.md; gate at plan |
| langchain-anthropic | PyPI | 1.4.6 latest, history to 0.0.1 | github.com/langchain-ai/langchain | unavailable | [ASSUMED] — locked; gate |
| langchain-openai | PyPI | 1.3.2 latest, history to 0.0.2 | github.com/langchain-ai/langchain | unavailable | [ASSUMED] — locked; gate |
| tenacity | PyPI | 9.1.4 latest, history to 2.0.0 | github.com/jd/tenacity | unavailable | [ASSUMED] — locked; gate |
| langsmith | PyPI | 0.8.* | github.com/langchain-ai/langsmith-sdk | unavailable | [ASSUMED] — optional; gate if adopted |
| tiktoken | PyPI | 0.13.0 latest, history to 0.1.1 | github.com/openai/tiktoken | unavailable | [ASSUMED] — pre-check tokenizer; gate |
| anthropic | PyPI | 0.109.1 latest, deep history | github.com/anthropics/anthropic-sdk-python | unavailable | [ASSUMED] — pre-check `count_tokens` only; gate |
| langchain-redis | PyPI | 0.2.5 latest, history to 0.0.1 | github.com/langchain-ai/langchain-redis | unavailable | [ASSUMED] — NOT recommended (custom cache wins); list only if native cache chosen |

**Packages removed due to slopcheck [SLOP] verdict:** none (slopcheck did not run).
**Packages flagged as suspicious [SUS]:** none observed via registry inspection.
**Action for planner:** insert a `checkpoint:human-verify` task before the `uv add` step listing the exact names+versions above (mirror the Phase 1 plan 01-02 Task-1 package-legitimacy gate pattern — user approved the full set there).

## Architecture Patterns

### System Architecture Diagram

```
  caller (future agent / test)
   complete(messages, operation_type, run_id?, model?, max_tokens, temperature,
            run_budget_overrides?, no_cache?)
        │
        ▼
 ┌────────────────────── llm_gateway.complete() ──────────────────────┐
 │ 1. run_id := caller's or generated (uuid4)            [D-10]         │
 │ 2. KILL-SWITCH CHECK ── Redis GET llm:killswitch ──► if set: raise  │
 │                                                  KillSwitchActive    │
 │ 3. resolve model/provider (settings default OR per-call override)   │
 │ 4. CACHE LOOKUP (only if temp==0 and not no_cache)  [D-11/D-12]      │
 │        key = sha256(provider|model|messages|params)                 │
 │        Redis GET llm:cache:<key> ──► HIT? → ledger(cache_hit=true,   │
 │                                       cost=0) + return cached        │
 │ 5. PRE-CHECK [D-01]:                                                 │
 │        est_in = count_tokens(provider, model, messages)             │
 │        est_cost = price(model).input*est_in + price.output*max_tok  │
 │        read Redis counters (per-run, per-day) ──► if any scope       │
 │        (call/run/day, tokens OR usd) would breach: raise            │
 │        BudgetExceeded  (NO spend) [D-02/D-03/D-04]                   │
 │ 6. PROVIDER CALL: init_chat_model(model,provider,...).ainvoke()     │
 │        wrapped in tenacity retry(429/529)                           │
 │ 7. RECONCILE [D-01]: actual = resp.usage_metadata                   │
 │        actual_cost = price(model, effective_date).from(actual)      │
 │ 8. Redis INCRBY counters (per-run key, per-day date-bucket key)     │
 │        if per-day USD now ≥ daily cap → SET llm:killswitch [D-05]   │
 │ 9. Postgres INSERT llm_usage row  +  structlog usage event [D-09]   │
 └────────────────────────────────────────────────────────────────────┘
        │
        ▼  AIMessage (content + usage) returned to caller

 Admin panic button:  POST /api/admin/llm/killswitch ─► Redis SET llm:killswitch
                      DELETE /api/admin/llm/killswitch ─► Redis DEL  [D-05/D-06]
```

### Recommended Project Structure
```
apps/api/app/
├── services/
│   └── llm_gateway.py        # the single complete() entry point + helpers
├── core/
│   ├── config.py             # +budget/model/cache/killswitch/provider-key env vars
│   └── llm_pricing.py        # effective-dated pricing table (data + lookup fn)
├── models/
│   └── llm_usage.py          # SQLAlchemy ledger model
├── schemas/
│   └── llm.py                # LLMRequest/LLMResult/RunBudgetOverrides pydantic
├── routers/
│   └── admin_llm.py          # kill-switch endpoints (behind auth)
└── alembic/versions/
    └── 0003_llm_usage.py     # chains after 0002_targets
```

### Pattern 1: Provider-agnostic instantiation + uniform usage read (PLAT-05, D-13)
**What:** One config string selects provider+model; the response exposes the SAME `usage_metadata` shape for both providers.
**When:** Every gateway call.
```python
# Source: https://reference.langchain.com/python/langchain/chat_models/base/init_chat_model
from langchain.chat_models import init_chat_model

# default from settings.llm_default_model, e.g. "anthropic:claude-..." or "openai:gpt-..."
model_str = per_call_model or settings.llm_default_model
chat = init_chat_model(model_str, temperature=temperature, max_tokens=max_tokens)
resp = await chat.ainvoke(messages)          # messages: list[BaseMessage] or list[dict]

# Uniform across Anthropic AND OpenAI:
um = resp.usage_metadata                      # {'input_tokens', 'output_tokens', 'total_tokens', ...}
in_tok  = um["input_tokens"]
out_tok = um["output_tokens"]
finish  = resp.response_metadata.get("stop_reason") or resp.response_metadata.get("finish_reason")
```
> `"anthropic:model"` / `"openai:model"` prefix sets the provider; or pass `model_provider=` separately. Per-call override = a different `model_str` (or a single configurable instance with `config={"configurable": {"model": ...}}`).

### Pattern 2: Pre-check reserve-then-reconcile (D-01)
**What:** Output tokens are unknown before the call, so reserve against `max_tokens`; correct to actual after.
**When:** Step 5 + Step 7 of every non-cached call.
```python
est_in = estimate_input_tokens(provider, model, messages)     # Pattern below
price = lookup_price(model)                                    # effective "now"
reserved_cost = price.input_per_tok * est_in + price.output_per_tok * max_tokens
# check reserved_cost (and est_in+max_tokens) against EACH scope's remaining budget
... call ...
actual_cost = price.input_per_tok * um["input_tokens"] + price.output_per_tok * um["output_tokens"]
# increment counters by ACTUAL, not reserved
```

### Pattern 3: Atomic Redis budget counters + date-bucketed daily key + kill-switch (D-07)
**What:** Counters in Redis, incremented atomically; per-day key is date-bucketed so it self-resets; kill-switch is a flag check.
**When:** Pre-check reads; post-call increments.
```python
# redis.asyncio client (already configured from settings.redis_url)
from datetime import datetime, timezone

today = datetime.now(timezone.utc).strftime("%Y%m%d")
DAY_USD   = f"llm:budget:day:{today}:usd"     # auto-resets by rolling the date in the key
DAY_TOK   = f"llm:budget:day:{today}:tok"
RUN_USD   = f"llm:budget:run:{run_id}:usd"
RUN_TOK   = f"llm:budget:run:{run_id}:tok"
KILL      = "llm:killswitch"

# kill-switch check (hot path, 1 round-trip)
if await r.get(KILL):
    raise KillSwitchActive()

# read both day+run counters in ONE round-trip via MGET
day_usd, day_tok, run_usd, run_tok = await r.mget(DAY_USD, DAY_TOK, RUN_USD, RUN_TOK)
# ...compare reserved est against caps...

# post-call atomic increments (INCRBYFLOAT for usd, INCRBY for tokens); pipeline = 1 round-trip
async with r.pipeline(transaction=True) as p:
    p.incrbyfloat(DAY_USD, actual_cost); p.incrby(DAY_TOK, total_tokens)
    p.incrbyfloat(RUN_USD, actual_cost); p.incrby(RUN_TOK, total_tokens)
    p.expire(DAY_USD, 172800); p.expire(DAY_TOK, 172800)   # 2-day TTL = self-cleanup
    p.expire(RUN_USD, RUN_TTL); p.expire(RUN_TOK, RUN_TTL)
    results = await p.execute()
new_day_usd = results[0]
if new_day_usd >= settings.llm_daily_usd_cap:        # auto-trip (D-05)
    await r.set(KILL, "daily-budget-exhausted")
```
> **Round-trip budget:** kill check (1) + MGET (1) on the hot path before the call; pipeline (1) after. Cache lookup adds 1 GET. ~3-4 Redis ops per call — all sub-ms locally.
> **Daily reset:** rolling the UTC date INTO the key is the standard self-resetting daily-window pattern (no cron, no manual reset). A 2-day TTL garbage-collects old buckets.
> **Race note:** the read-then-call gap (D-01) means two concurrent calls can both pass the pre-check and slightly overshoot. For a single-user platform this is acceptable; if strict, reserve via `INCRBYFLOAT` up front and refund the delta on reconcile (Lua/`WATCH` for full atomicity). Recommend the simple read-check for MVP, documented.

### Pattern 4: Effective-dated pricing table (D-08)
**What:** Prices versioned by `effective_date`; cost of historical rows stays correct when prices change.
**When:** Cost calc at reconcile; the ledger stores the *computed* cost so historical rows are immutable regardless of future table edits.
```python
# app/core/llm_pricing.py  — manually maintained, no runtime pricing API (D-08)
from datetime import date
from pydantic import BaseModel

class PriceRow(BaseModel):
    model: str
    input_per_mtok: float    # USD per 1M input tokens
    output_per_mtok: float   # USD per 1M output tokens
    effective_date: date

PRICING: list[PriceRow] = [
    PriceRow(model="claude-...", input_per_mtok=3.00, output_per_mtok=15.00, effective_date=date(2026,1,1)),
    PriceRow(model="gpt-...",    input_per_mtok=2.50, output_per_mtok=10.00, effective_date=date(2026,1,1)),
    # add a new row (newer effective_date) when a price changes — never edit old rows
]

def lookup_price(model: str, at: date | None = None) -> PriceRow:
    at = at or date.today()
    rows = sorted((p for p in PRICING if p.model == model and p.effective_date <= at),
                  key=lambda p: p.effective_date)
    if not rows:
        raise UnknownModelPriceError(model)   # refuse calls we can't cost (fail-closed)
    return rows[-1]   # most-recent effective row at/under `at`
```
> Use $/1M-token units (current provider convention). Cost = `input_tokens/1e6 * input_per_mtok + output_tokens/1e6 * output_per_mtok`. **Fail closed**: an unknown model raises rather than logging $0 — otherwise budgets are bypassable by passing an unpriced model string.

### Pattern 5: `llm_usage` ledger model + migration (D-09)
**What:** One row per call, SQL-queryable per `operation_type`.
```python
# app/models/llm_usage.py
class LLMUsage(Base):
    __tablename__ = "llm_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)          # D-10 per-run grouping
    operation_type: Mapped[str] = mapped_column(String(64), index=True)  # D-10 report grouping
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6))   # store COMPUTED cost (immutable)
    cache_hit: Mapped[bool] = mapped_column(Boolean, server_default="false")  # D-12
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```
> Migration `0003_llm_usage.py`: `down_revision = "0002"` (chains after targets). Index `run_id` + `operation_type` + `created_at` for the cost-per-operation queries. **Prompt/response text is NOT stored** (PLAT-07; structlog redaction would scrub it anyway). Use `Numeric` not `Float` for money.

### Pattern 6: Custom Redis response cache (D-11/D-12) — RECOMMENDED over native
**What:** Gateway-owned cache so a hit can be logged (`cache_hit=true`) and charged $0.
```python
import hashlib, json

def cache_key(provider, model, messages, params) -> str:
    payload = json.dumps(
        {"provider": provider, "model": model,
         "messages": _normalize(messages),                 # stable serialization
         "params": {"temperature": params.temperature,
                    "max_tokens": params.max_tokens, "tools": params.tools}},
        sort_keys=True, separators=(",", ":"))
    return "llm:cache:" + hashlib.sha256(payload.encode()).hexdigest()

# lookup (only when temperature == 0 and not no_cache — D-12)
if temperature == 0 and not no_cache:
    cached = await r.get(cache_key(...))
    if cached:
        await ledger_insert(..., cost_usd=0, cache_hit=True)   # D-12: $0, logged
        return deserialize(cached)                              # skip provider + budget entirely
# on miss + successful call:
if temperature == 0 and not no_cache:
    await r.setex(cache_key(...), settings.llm_cache_ttl_s, serialize(resp))
```
> A cache hit costs $0, is recorded `cache_hit=true`, and does NOT touch budget counters — exactly D-12. The native `set_llm_cache` global cache cannot do this (no caller-visible hit signal). Serialize `AIMessage` via LangChain's `message.model_dump()` / `messages_to_dict`.

### Anti-Patterns to Avoid
- **Logging prompt/response text to the ledger or structlog.** PLAT-07. Store token counts + cost only; redaction is a backstop, not the primary control.
- **Storing money as `Float`.** Use `Numeric`/`Decimal` for `cost_usd`.
- **Native `set_llm_cache` global cache.** Transparent hits break `cache_hit` logging and budget-skip (D-12).
- **Computing cost from a single mutable price constant.** Effective-dating (D-08) requires versioned rows; store the *computed* cost on the ledger row.
- **Importing the `anthropic`/`openai` SDKs for the chat path.** CLAUDE.md forbids it — use `init_chat_model`. (`anthropic` SDK is permitted ONLY for `count_tokens` pre-estimation.)
- **A non-resetting daily counter.** Date-bucket the key; don't hand-roll a midnight reset job.
- **Logging $0 for unpriced models.** Fail closed (raise) so budgets can't be bypassed with an unknown model string.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Provider abstraction | A custom Anthropic/OpenAI adapter | `init_chat_model` | CLAUDE.md-locked; normalizes messages, tool-calling, streaming, `usage_metadata` |
| OpenAI token count | Manual BPE | `tiktoken` | Exact local encoder; provider-maintained |
| Anthropic token count | Char heuristic (only if avoiding deps) | `anthropic.beta.messages.count_tokens` | Exact server-side count incl. tools/images |
| Retry/backoff for 429/529 | `time.sleep` loops | `tenacity` (`retry` + `wait_exponential` + `retry_if_exception_type`) | CLAUDE.md-locked; jitter, max attempts, async-aware |
| Atomic counters | Read-modify-write in Python | Redis `INCRBY`/`INCRBYFLOAT` | Atomic across api+workers; the whole point of D-07 |
| Daily window reset | Cron/midnight job | Date-bucketed Redis key + TTL | Self-resetting, stateless |
| Response cache | DB table + manual eviction | Redis `SETEX` keyed by content hash | TTL eviction free; matches D-12 |

**Key insight:** Almost everything here is "wire existing primitives correctly," not "build a system." The only genuinely custom code is the **orchestration order** (kill → cache → pre-check → call → reconcile → ledger) and the **cache wrapper** that the native LangChain cache can't satisfy.

## Common Pitfalls

### Pitfall 1: Native LangChain cache silently breaks the ledger
**What goes wrong:** Using `set_llm_cache(RedisCache(...))`, a cache hit returns transparently — the gateway never learns it was a hit, so no `cache_hit=true` row and budget logic still runs on a $0 call.
**Why:** The global cache sits below `ainvoke`; there's no return signal.
**Avoid:** Custom Redis wrapper (Pattern 6) checked BEFORE `init_chat_model`.
**Warning sign:** Ledger has no `cache_hit=true` rows despite repeated identical temp=0 calls.

### Pitfall 2: Reserving against `max_tokens` but never reconciling
**What goes wrong:** Counters drift high (always charge max output) and budgets exhaust prematurely.
**Why:** Output is unknown pre-call; if you forget Step 7 you keep the reservation.
**Avoid:** Increment counters by ACTUAL `usage_metadata`, not the reservation (Pattern 2/3).
**Warning sign:** Daily USD climbs faster than the ledger's summed `cost_usd`.

### Pitfall 3: `usage_metadata` is None / shape differs
**What goes wrong:** Some providers/paths (streaming, certain tool calls) may omit `usage_metadata` or nest details.
**Why:** Provider variance; streaming aggregates differently.
**Avoid:** Use non-streaming `ainvoke` for the MVP; assert `usage_metadata` present and raise if absent (fail-closed — can't cost = can't charge = refuse to silently log $0). Read `input_tokens`/`output_tokens` (not provider-native keys).
**Warning sign:** `KeyError` or $0 costs on real calls.

### Pitfall 4: Daily counter never resets / resets at wrong boundary
**What goes wrong:** A fixed key `llm:budget:day:usd` accumulates forever; or a local-time boundary mismatches UTC ledger timestamps.
**Avoid:** Date-bucket with **UTC** `%Y%m%d` (Pattern 3); TTL old buckets.
**Warning sign:** Kill-switch trips on day 2 with no new spend.

### Pitfall 5: Provider keys / prompts leaking into logs or the ledger
**What goes wrong:** Logging the full request dict dumps prompts (untrusted target-app content later) and possibly keys.
**Avoid:** Log only `{operation_type, run_id, provider, model, input_tokens, output_tokens, cost_usd, cache_hit}`. Never the messages. structlog redaction covers `token|secret|...` keys but don't rely on it for prompt bodies.
**Warning sign:** Log lines longer than a few hundred chars; any `messages`/`content` key in a usage event.

### Pitfall 6: CI runs the parity test without keys and fails (or worse, spends money in CI uncontrolled)
**What goes wrong:** The two-provider parity test needs real keys; running it unconditionally either fails or incurs spend.
**Avoid:** `@pytest.mark.skipif(not (ANTHROPIC_API_KEY and OPENAI_API_KEY))` + a dedicated `live_llm` marker; keep it OUT of the default CI gate, run on demand. All budget/kill-switch/cache logic tested with mocked `init_chat_model` (no keys, no spend).
**Warning sign:** CI bill; or red CI on PRs from forks without secrets.

## Code Examples

### init_chat_model with tenacity retry (verified API)
```python
# Source: https://reference.langchain.com/python/langchain/chat_models/base/init_chat_model
# Source: https://reference.langchain.com/python/langchain-core/messages/ai/UsageMetadata
from langchain.chat_models import init_chat_model
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(retry=retry_if_exception_type(TransientProviderError),
       wait=wait_exponential(multiplier=1, min=1, max=30),
       stop=stop_after_attempt(4), reraise=True)
async def _invoke(model_str, messages, *, temperature, max_tokens):
    chat = init_chat_model(model_str, temperature=temperature, max_tokens=max_tokens)
    return await chat.ainvoke(messages)
```

### Anthropic input-token pre-estimate (verified API)
```python
# Source: https://platform.claude.com/docs/en/build-with-claude/token-counting
import anthropic
_a = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
def anthropic_input_tokens(model, messages) -> int:
    res = _a.messages.count_tokens(model=model, messages=messages)  # GA in current SDK
    return res.input_tokens
```

### OpenAI input-token pre-estimate (local, no call)
```python
# Source: https://github.com/openai/tiktoken
import tiktoken
def openai_input_tokens(model, messages) -> int:
    enc = tiktoken.encoding_for_model(model)             # falls back to o200k_base for new models
    # approximate chat framing overhead (~3 tokens/msg + 3 priming); exact enough for a pre-check
    return sum(len(enc.encode(m["content"])) + 4 for m in messages) + 3
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-provider SDK adapters | `init_chat_model("provider:model")` | LangChain 1.0 GA (Oct 2025) | Provider is a config string; zero adapter code |
| `langgraph.prebuilt.create_react_agent` | `langchain.agents.create_agent` | LangChain 1.x | Not used this phase, but agents (Phase 4+) consume this gateway |
| `aioredis` | `redis.asyncio` (built into `redis`) | redis-py 4.2+ / 8.x | Already the Phase-1 client |
| `langchain.cache` global only | `langchain-redis` `RedisCache`/`RedisSemanticCache` | langchain-redis 0.x | Available, but custom wrapper still preferred here (D-12) |

**Deprecated/outdated:**
- `aioredis` — dead; use `redis.asyncio`.
- A custom LLM adapter / LiteLLM-under-LangChain — explicitly rejected in CLAUDE.md.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `langchain` (meta) pins to 1.x and transitively resolves `langchain-core` 1.4.x exporting current `init_chat_model`; CLAUDE.md's "langchain 1.4.x" is the meta-pkg label, live latest is 1.3.9 | Project Constraints / Standard Stack | Wrong pin → resolver conflict; mitigated by verifying at install time (Q1) |
| A2 | `tiktoken` + `anthropic.count_tokens` are the right pre-check tokenizers; both are [ASSUMED] packages needing a legitimacy gate | Standard Stack / Don't Hand-Roll | If gate rejects them, fall back to char/4 heuristic (Q2) — looser pre-check |
| A3 | Anthropic `messages.count_tokens` is GA (not beta-header-gated) in `anthropic` 0.109.x | Code Examples | If beta-only, add `betas=["token-counting-..."]` header; minor |
| A4 | `resp.usage_metadata` is populated for non-streaming `ainvoke` on BOTH providers in current langchain-anthropic/openai | Pattern 1/3 | If None on a path, fail-closed raise (Pitfall 3); verified by docs for non-streaming |
| A5 | Read-then-check budget race is acceptable for a single-user platform (slight overshoot possible under concurrency) | Pattern 3 | Wrong → minor overspend; upgrade to reserve-via-INCR + refund if strictness needed |
| A6 | Custom Redis cache beats native `set_llm_cache` for D-12 (cache_hit logging + budget skip) | Pattern 6 | Low — native cache demonstrably lacks a hit signal |
| A7 | Storing computed `cost_usd` on the ledger row satisfies effective-dating without a separate price-version FK | Pattern 4/5 | Low — immutable computed cost is the standard ledger approach |

**Note:** A1–A3 concern packages/versions the planner should re-verify at install time and gate per the Package Legitimacy Audit. A4–A7 are design choices the planner/discuss-phase may confirm.

## Open Questions

1. **Exact `langchain` version pin.**
   - Known: `init_chat_model` is `from langchain.chat_models import init_chat_model`; `langchain-core` latest 1.4.7; `langchain` meta latest 1.3.9.
   - Unclear: whether to pin `langchain==1.3.*` (live latest) or `1.4.*` (CLAUDE.md label — may not yet exist for the meta-pkg).
   - Recommendation: pin `langchain==1.*` and `langchain-anthropic==1.4.*`/`langchain-openai==1.3.*`, run `uv lock`, verify `init_chat_model` imports + a smoke `ainvoke`. Let `uv` resolve `langchain-core`.

2. **Token pre-check: SDK tokenizers vs heuristic.**
   - Known: `tiktoken` (OpenAI, local) + `anthropic.count_tokens` (Anthropic, 1 API call) give exact counts but add 2 [ASSUMED] packages and (Anthropic) a round-trip per call.
   - Unclear: whether the user wants exactness or prefers zero new deps.
   - Recommendation: default to exact (tiktoken + anthropic count_tokens); offer char/4 heuristic as the fallback if the package gate is contentious. Discuss-phase can confirm.

3. **LangSmith tracing now or deferred?** (Claude's discretion)
   - Recommendation: wire it env-gated (`LANGSMITH_TRACING`/`LANGSMITH_API_KEY`) but off by default — one env var, no code cost, invaluable when debugging Phase 4 agents. Defer if it adds setup friction.

4. **Per-run budget hard-ceiling enforcement (D-04 "never loosen beyond a hard global ceiling").**
   - Known: per-run overrides may only TIGHTEN.
   - Recommendation: clamp run overrides to `min(override, global_cap)` and reject/ignore any loosening; document. Planner to confirm the clamp-vs-reject behavior.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Redis | counters, kill-switch, cache | ✓ (Phase 1 compose) | 8.x | none needed |
| PostgreSQL | `llm_usage` ledger | ✓ (Phase 1 compose) | 15.x | none needed |
| ANTHROPIC_API_KEY | parity test + Anthropic path | ✗ (user-supplied via .env) | — | skip live tests; mock unit tests |
| OPENAI_API_KEY | parity test + OpenAI path | ✗ (user-supplied via .env) | — | skip live tests; mock unit tests |
| Internet egress to provider APIs | live parity run | host-dependent | — | mock-based unit suite covers all logic |

**Missing dependencies with no fallback:** none — all *logic* is testable without provider keys.
**Missing dependencies with fallback:** provider API keys (live parity test is gated/skippable; all budget/kill-switch/cache logic uses mocked `init_chat_model`). RAM blocker (STATE.md) does NOT bite Phase 2 — no Neo4j/Elasticsearch here; the Phase-1 Postgres+Redis footprint already fits the 3 GB WSL cap.

## Validation Architecture

> nyquist_validation = true (config.json). Section required.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.* + pytest-asyncio 1.4.* (`asyncio_mode = "auto"`) |
| Config file | `apps/api/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd apps/api && uv run pytest tests/functional -m "not live_llm" -x` |
| Full suite command | `cd apps/api && uv run pytest tests` |
| New marker (Wave 0) | `live_llm: needs real provider keys; skipped when absent; off the default gate` |

### Phase Requirements → Test Map
| Req | Behavior | Test Type | Automated Command | File Exists? |
|-----|----------|-----------|-------------------|-------------|
| PLAT-05 | Same gateway call runs on Anthropic AND OpenAI by config only; uniform `usage_metadata` read | integration (live) | `uv run pytest tests/integration/test_llm_parity.py -m live_llm` | ❌ Wave 0 |
| PLAT-05 | Provider/model resolution from settings + per-call override (no live call) | unit (mock `init_chat_model`) | `uv run pytest tests/unit/test_gateway_provider.py` | ❌ Wave 0 |
| PLAT-06 | Pre-check refuses a call that would breach per-call/run/day cap → raises `BudgetExceeded` (no spend) | unit (mock model + fakeredis/real Redis) | `uv run pytest tests/unit/test_budget_precheck.py` | ❌ Wave 0 |
| PLAT-06 | Reconcile increments counters by ACTUAL usage, not reservation | unit | `uv run pytest tests/unit/test_budget_reconcile.py` | ❌ Wave 0 |
| PLAT-06 | Manual kill-switch (admin endpoint) halts ALL calls → `KillSwitchActive` | functional (live HTTP) | `uv run pytest tests/functional/test_killswitch.py` | ❌ Wave 0 |
| PLAT-06 | Daily-budget exhaustion auto-trips kill-switch | unit | `uv run pytest tests/unit/test_killswitch_auto.py` | ❌ Wave 0 |
| PLAT-06 | Cost logged per operation: `llm_usage` row + structlog event with correct USD from effective-dated price | functional | `uv run pytest tests/functional/test_usage_ledger.py` | ❌ Wave 0 |
| PLAT-06 | Effective-dated pricing: a price change does not alter historical row cost | unit | `uv run pytest tests/unit/test_pricing.py` | ❌ Wave 0 |
| PLAT-06 | Cache hit on identical temp=0 call → $0, `cache_hit=true`, no provider call, no budget increment | unit (mock model + Redis) | `uv run pytest tests/unit/test_cache.py` | ❌ Wave 0 |
| PLAT-06 | temp>0 and `no_cache` never cache | unit | `uv run pytest tests/unit/test_cache.py::test_no_cache_paths` | ❌ Wave 0 |
| PLAT-07 | No prompt/response text or keys in ledger or logs | functional | `uv run pytest tests/functional/test_llm_log_safety.py` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit tests/functional -m "not live_llm" -x` (fast, no keys, no spend)
- **Per wave merge:** full functional suite (`-m "not live_llm"`)
- **Phase gate:** full suite green; live parity test (`-m live_llm`) run ON DEMAND with keys present, evidence captured for Success Criterion 1.

### Wave 0 Gaps
- [ ] `tests/unit/conftest.py` — mock `init_chat_model` returning a fake `AIMessage` with controllable `usage_metadata`; a Redis fixture (real Redis from compose, flushed per test, OR `fakeredis`).
- [ ] `live_llm` marker registered in `pyproject.toml` + skipif helper keyed on `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`.
- [ ] `tests/integration/test_llm_parity.py` — the two-provider parity test (Success Criterion 1).
- [ ] Unit/functional test files listed above.
- [ ] Decide Redis test isolation: dedicated test key prefix or separate DB index to avoid clobbering dev counters.

> **`fakeredis` would be a NEW [ASSUMED] package.** Prefer the already-running compose Redis with a test key prefix + flush to avoid another package gate; only add `fakeredis` if isolated unit tests must run with no Redis container.

## Security Domain

> `security_enforcement` not set in config → treated as enabled.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Kill-switch admin endpoint behind existing `get_current_user` (Phase 1 JWT); later RBAC (Phase 10) restricts to Admin |
| V3 Session Management | no | Gateway is service-internal; no new sessions |
| V4 Access Control | yes (partial) | Admin kill-switch must require auth now; role-gating (Admin-only) lands Phase 10 — document the gap |
| V5 Input Validation | yes | Pydantic schemas validate `operation_type`, `run_id`, model string, budget params; reject unpriced models (fail-closed) |
| V6 Cryptography | no (reuse) | No new crypto; provider keys via env only (never logged/committed) |
| V7 Error Handling & Logging | yes | Usage events carry NO prompt/response text or keys; structlog redaction backstop; fail-closed on missing usage/price |
| V9 Communications | yes | httpx/provider SDKs use HTTPS to provider APIs (library default) |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Provider key leakage via logs | Information Disclosure | Keys only in env/Settings; never logged; redaction processor; never store in ledger |
| Prompt/response (untrusted target content later) written to logs | Information Disclosure / Tampering | Log token counts + cost only; no message bodies |
| Budget bypass via unpriced model string | Tampering / Repudiation | Fail-closed: unknown model raises, never logs $0 |
| Kill-switch endpoint abused/unauthenticated | Elevation of Privilege / DoS | Endpoint behind auth now; Admin-RBAC in Phase 10 |
| Counter race causing overspend | Tampering | Atomic Redis INCR; accept minor read-check overshoot for single-user MVP, documented (Pattern 3) |
| Cache poisoning via key collision | Tampering | SHA-256 over full provider+model+messages+params; exact-match only (D-11) |
| Unbounded retries amplifying spend/load | DoS | tenacity `stop_after_attempt` + max backoff; retry only transient (429/529) |

## Sources

### Primary (HIGH confidence)
- LangChain reference — `init_chat_model` signature & per-call config override: https://reference.langchain.com/python/langchain/chat_models/base/init_chat_model
- LangChain reference — `UsageMetadata` (input_tokens/output_tokens/total_tokens/details): https://reference.langchain.com/python/langchain-core/messages/ai/UsageMetadata
- Anthropic token-counting (`messages.count_tokens`): https://platform.claude.com/docs/en/build-with-claude/token-counting
- tiktoken (OpenAI local encoder): https://github.com/openai/tiktoken
- PyPI live version checks (2026-06-13): langchain 1.3.9, langchain-core 1.4.7, langchain-anthropic 1.4.6, langchain-openai 1.3.2, langgraph 1.2.5, tenacity 9.1.4, tiktoken 0.13.0, anthropic 0.109.1, langchain-redis 0.2.5
- Existing codebase: `apps/api/app/core/config.py`, `app/services/target_service.py`, `app/core/logging.py`, `app/models/target.py`, `alembic/versions/0002_targets.py`, `tests/conftest.py`, `pyproject.toml`

### Secondary (MEDIUM confidence)
- LangChain messages docs (usage_metadata example shape): https://docs.langchain.com/oss/python/langchain/messages
- langchain-redis cache classes (`RedisCache`/`RedisSemanticCache`): https://reference.langchain.com/python/integrations/langchain_redis/
- CLAUDE.md Technology Stack tables (locked LLM layer + version compatibility)

### Tertiary (LOW confidence)
- Anthropic count_tokens beta-header detail (A3) — GA in current SDK assumed; verify at install time.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified on PyPI; LLM layer locked by CLAUDE.md.
- Architecture (gateway orchestration, Redis counters, pricing, ledger, cache): HIGH — composes verified primitives; cache decision well-reasoned against D-12.
- `init_chat_model` API + `usage_metadata`: HIGH — confirmed against LangChain reference docs.
- Token pre-check packages (tiktoken/anthropic): MEDIUM — APIs verified; packages are [ASSUMED] pending legitimacy gate (slopcheck blocked by sandbox).
- Pitfalls: HIGH — derived from the locked decisions and verified API behaviors.

**Research date:** 2026-06-13
**Valid until:** 2026-07-13 (fast-moving LangChain ecosystem — re-verify versions if planning slips past ~2 weeks)
