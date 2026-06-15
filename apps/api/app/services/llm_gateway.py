"""LLM gateway — the single money-control surface every agent call routes through
(PLAT-05/PLAT-06).

Slice 1 (Plan 01) implemented the call + cost-accounting path. Slice 2 (Plan 02)
added BUDGET ENFORCEMENT + KILL-SWITCH. Slice 3 (Plan 03) inserts the Redis
RESPONSE CACHE, in this orchestration order:

    1. KILL-SWITCH check (Redis GET) — FIRST hot-path op; raises KillSwitchActive.
    2. CACHE LOOKUP (D-11/D-12): ONLY when temperature==0 and not no_cache. On a
       hit, return the deserialized response for $0 (cache_hit=true ledger row, NO
       provider call, NO budget counter touched), skipping pre-check + provider.
    3. PRE-CHECK (D-01): estimate input tokens + reserve max_tokens at the model
       price; read per-run/per-day counters (one MGET); refuse (BudgetExceeded) if
       reserving would breach per-call/per-run/per-day on EITHER the USD or token
       axis. NO provider call, NO ledger row on breach (D-02/D-03).
    4. PROVIDER CALL via init_chat_model (Plan 01 _invoke, tenacity-retried).
    5. RECONCILE (D-01): increment counters by ACTUAL usage_metadata (NOT the
       reservation, Pitfall 2); pipeline INCRBYFLOAT/INCRBY + TTLs.
    6. CACHE WRITE (D-12): on a miss+success, SETEX the key with LLM_CACHE_TTL_S
       (only temperature==0 and not no_cache).
    7. AUTO-TRIP (D-05): if post-increment day USD >= the daily cap, SET the
       kill-switch flag (global blast radius — D-06).
    8. Ledger row + redaction-safe usage event (Plan 01).

ORDER IS LOAD-BEARING (D-06): the kill-switch check runs BEFORE the cache lookup, so
an active halt refuses EVERY call — including one that would otherwise be a cache hit.
A cached response is still gateway output, and the panic button may be pulled for
non-cost reasons (e.g. a security halt), so the $0 of a hit is irrelevant. A cache hit
NEVER bypasses the kill-switch.

Per-run overrides may only TIGHTEN budgets — clamped to min(override, global cap),
never loosened past the global ceiling (D-04, RESEARCH Q4).

RACE NOTE (RESEARCH Pattern 3, T-02-09 accept): the pre-check READS counters then
the reconcile INCREMENTS them, so two concurrent calls can both pass and slightly
overshoot. Accepted for the single-user MVP; upgradeable to reserve-via-INCR +
refund if strict atomicity is later required.

REDACTION COLLISION (PATTERNS flag #2): core/logging.py's SENSITIVE regex matches
the substring "token", so log keys input_tokens/output_tokens would render
[REDACTED]. The usage event therefore logs counts under tok_in/tok_out (regex-safe).

PLAT-07: prompts/responses and provider keys NEVER enter the ledger or a log event.
The `anthropic` SDK is imported ONLY for count_tokens (the pre-check tokenizer) —
NEVER for the chat path, which stays on init_chat_model (CLAUDE.md).
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import structlog
from langchain.chat_models import init_chat_model
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.llm_pricing import compute_cost, lookup_price
from app.core.redis_client import get_redis
from app.models.llm_usage import LLMUsage
from app.schemas.llm import LLMResult

log = structlog.get_logger()

# Redis key namespace. Tests monkeypatch this to "test:llm:" so the prefixed-flush
# fixture isolates them from dev counters; production uses the bare "llm:" prefix.
_KEY_PREFIX = "llm:"


async def get_run_cost_usd(run_id: str) -> float:
    """Read the per-run accumulated USD cost from the gateway's Redis counter (D-06).

    This is the SINGLE source of run spend — the explorer NEVER computes cost, it reads this
    aggregate for the live ExploreProgressEvent. Returns 0.0 when no call has been metered yet
    (the counter does not exist until the first reconcile INCRBYFLOAT).
    """
    run_usd_key = f"{_KEY_PREFIX}budget:run:{run_id}:usd"
    raw = await get_redis().get(run_usd_key)
    return float(raw) if raw else 0.0


class TransientProviderError(Exception):
    """A retryable provider failure (429/529/transient network) — drives tenacity."""


class MissingUsageMetadataError(Exception):
    """Provider returned no usage_metadata — fail closed (Pitfall 3), never cost $0."""


class BudgetExceeded(Exception):
    """Raised by the pre-check when a call would breach a budget cap (D-02).

    Carries the breached scope+axis for callers/logs. NO provider call is made and
    NO ledger row is written when this raises — the spend is refused before it happens.
    """

    def __init__(self, scope: str, axis: str, detail: str = ""):
        self.scope = scope  # "per_call" | "per_run" | "per_day"
        self.axis = axis  # "usd" | "tokens"
        super().__init__(f"budget exceeded: {scope}/{axis} {detail}".strip())


class KillSwitchActive(Exception):
    """Raised on EVERY gateway call while the kill-switch is set (D-06 global halt)."""

    def __init__(self, reason: str | None = None):
        self.reason = reason
        super().__init__(f"kill-switch active: {reason or 'unknown'}")


# Env-gated LangSmith passthrough (D-discretion). No code cost when off.
if settings.langsmith_tracing:
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    if settings.langsmith_api_key:
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)


def _killswitch_key() -> str:
    return f"{_KEY_PREFIX}killswitch"


def _normalize_messages(messages) -> list[dict]:
    """Stable role+text view of the message list for the cache key (D-11).

    Works on both dict messages and langchain message objects. Only role+text
    participate in the hash — the same logical conversation always hashes the same.
    """
    return [{"role": _role(m), "content": _msg_text(m)} for m in messages]


def _cache_key(provider, model, messages, temperature, max_tokens, tools) -> str:
    """SHA-256 cache key over provider+model+normalized messages+params (D-11).

    Exact-match only: a difference in provider, model, ANY message, temperature,
    max_tokens, or tools produces a different key -> a miss (no false hits, T-02-13).
    Canonical JSON (sort_keys, tight separators) makes the digest stable.

    Key shape (production prefix): "llm:cache:<sha256>".
    """
    payload = json.dumps(
        {
            "provider": provider,
            "model": model,
            "messages": _normalize_messages(messages),
            "params": {
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tools": tools,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{_KEY_PREFIX}cache:" + hashlib.sha256(payload.encode()).hexdigest()


def _serialize_result(content, input_tokens: int, output_tokens: int) -> str:
    """Serialize a cacheable response to JSON for Redis (content + usage counts).

    Only the gateway-relevant fields are stored — enough to rebuild the LLMResult and
    recompute (zero) cost on a hit. No prompt, no provider key (PLAT-07/T-02-17).
    """
    return json.dumps(
        {
            "content": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
    )


def _deserialize_result(raw: str) -> dict:
    """Inverse of _serialize_result: JSON -> {content, input_tokens, output_tokens}."""
    return json.loads(raw)


def _provider_of(model_str: str) -> str:
    """Provider name from a provider-prefixed model string ("anthropic:..." -> "anthropic")."""
    provider, sep, _ = model_str.partition(":")
    return provider if sep else ""


def _estimate_input_tokens(provider: str, model: str, messages) -> int:
    """Estimate input tokens for the pre-check (D-01).

    - OpenAI: local tiktoken encode (no network).
    - Anthropic: the `anthropic` SDK's count_tokens — ONE network round-trip per
      pre-check, an accepted cost for an exact pre-estimate (the SDK is used ONLY
      here for counting, never for the chat path — CLAUDE.md).
    - FALLBACK (char/4): the documented heuristic used when a tokenizer is
      unavailable OR raises (e.g. the tiktoken/anthropic packages were rejected at
      the 02-01 legitimacy gate, an offline Anthropic count, or an unknown model).
      This guarantees the pre-check ALWAYS has a working implementation path
      regardless of package availability (RESEARCH Q2 / Alternatives).
    """
    bare = model.partition(":")[2] or model
    try:
        if provider == "openai":
            import tiktoken

            try:
                enc = tiktoken.encoding_for_model(bare)
            except KeyError:
                enc = tiktoken.get_encoding("o200k_base")
            return sum(len(enc.encode(_msg_text(m))) + 4 for m in messages) + 3
        if provider == "anthropic" and settings.anthropic_api_key:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            res = client.messages.count_tokens(
                model=bare,
                messages=[
                    {"role": _role(m), "content": _msg_text(m)} for m in messages
                ],
            )
            return int(res.input_tokens)
    except Exception:
        # Any tokenizer failure -> documented char/4 fallback (never block the call).
        pass
    return _char4_estimate(messages)


def _char4_estimate(messages) -> int:
    """Documented heuristic: ~1 token per 4 characters (RESEARCH Q2 fallback)."""
    chars = sum(len(_msg_text(m)) for m in messages)
    return max(1, chars // 4)


def _msg_text(m) -> str:
    if isinstance(m, dict):
        content = m.get("content", "")
    else:
        content = getattr(m, "content", "")
    return content if isinstance(content, str) else str(content)


def _role(m) -> str:
    if isinstance(m, dict):
        return m.get("role", "user")
    return getattr(m, "type", "user")


def _effective_caps(run_budget_overrides: dict | None) -> dict:
    """Resolve effective caps = global default, TIGHTENED by any per-run override.

    Per-run overrides may only LOWER a cap (D-04 clamp): the effective cap is
    min(override, global). A looser override is silently clamped to the global
    ceiling; a tighter override is honored. Missing override keys keep the global.
    """
    o = run_budget_overrides or {}

    def clamp(key: str, global_cap):
        override = o.get(key)
        if override is None:
            return global_cap
        return min(override, global_cap)

    return {
        "per_call_usd": clamp("per_call_usd_cap", settings.llm_per_call_usd_cap),
        "run_usd": clamp("run_usd_cap", settings.llm_run_usd_cap),
        "day_usd": clamp("daily_usd_cap", settings.llm_daily_usd_cap),
        "per_call_tok": clamp("per_call_token_cap", settings.llm_per_call_token_cap),
        "run_tok": clamp("run_token_cap", settings.llm_run_token_cap),
        "day_tok": clamp("daily_token_cap", settings.llm_daily_token_cap),
    }


@retry(
    retry=retry_if_exception_type(TransientProviderError),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def _invoke(model_str: str, messages, *, temperature: float, max_tokens: int):
    """Single provider round-trip, retried on TransientProviderError only."""
    chat = init_chat_model(model_str, temperature=temperature, max_tokens=max_tokens)
    return await chat.ainvoke(messages)


async def set_killswitch(reason: str) -> None:
    """Trip the global kill-switch (admin panic button / auto-trip). Redis SET."""
    await get_redis().set(_killswitch_key(), reason)


async def clear_killswitch() -> None:
    """Clear the global kill-switch (admin resume). Redis DEL."""
    await get_redis().delete(_killswitch_key())


async def get_killswitch() -> str | None:
    """Current kill-switch reason, or None when inactive."""
    return await get_redis().get(_killswitch_key())


async def complete(
    db: AsyncSession,
    messages,
    *,
    operation_type: str,
    run_id: str | None = None,
    model: str | None = None,
    temperature: float = 0,
    max_tokens: int,
    no_cache: bool = False,
    run_budget_overrides: dict | None = None,
) -> LLMResult:
    """Route one metered LLM call: kill-check -> pre-check -> invoke -> reconcile -> ledger.

    `model` may be a provider-prefixed string (the form init_chat_model consumes);
    when omitted, settings.llm_default_model is used (D-13). A run_id is generated
    when the caller supplies none (D-10).

    Budget enforcement (D-01/02/03/04): the call is refused with BudgetExceeded
    BEFORE any spend if reserving (estimated input tokens + max_tokens at the model
    price) would breach per-call/per-run/per-day on the USD OR token axis. Per-run
    overrides may only TIGHTEN caps (clamped to the global ceiling).

    Kill-switch (D-05/06): while the flag is set EVERY call raises KillSwitchActive
    immediately (checked first); the daily-USD exhaustion auto-trips it.

    Fails closed when usage_metadata is absent or the model is unpriced (never $0).
    `no_cache` is accepted now as a forward seam (Plan 03 cache).
    """
    run_id = run_id or uuid.uuid4().hex
    model_str = model or settings.llm_default_model
    provider = _provider_of(model_str)
    r = get_redis()

    # ORDER (D-06, load-bearing): kill-switch FIRST, cache SECOND, pre-check THIRD.
    # An active kill-switch refuses EVERY call — including a would-be cache hit — so
    # the kill-switch GET MUST run before the cache lookup. A cache hit NEVER bypasses
    # the kill-switch (the panic button may be pulled for non-cost reasons; $0 is
    # irrelevant during a halt).

    # (1) KILL-SWITCH check FIRST — global blast radius, before any spend (D-06).
    kill_reason = await r.get(_killswitch_key())
    if kill_reason:
        raise KillSwitchActive(kill_reason)

    # Resolve the model price up front (used by both the cache-hit ledger row and the
    # pre-check). UnknownModelPriceError propagates (fail-closed) before any spend.
    price = lookup_price(model_str)

    # (2) CACHE LOOKUP — only for deterministic, cacheable calls (D-11/D-12). temp>0
    # and no_cache=true bypass the cache entirely (no read, no write). Runs AFTER the
    # kill-switch check, so a halt already refused the call above.
    cacheable = temperature == 0 and not no_cache
    cache_key = (
        _cache_key(provider, model_str, messages, temperature, max_tokens, None)
        if cacheable
        else None
    )
    if cache_key is not None:
        cached = await r.get(cache_key)
        if cached is not None:
            return await _serve_cache_hit(
                db,
                _deserialize_result(cached),
                operation_type=operation_type,
                run_id=run_id,
                provider=provider,
                model_str=model_str,
            )

    # (3) PRE-CHECK (D-01). Reserve = estimated input tokens + max_tokens at price.
    # `price` was resolved above (shared with the cache-hit ledger path).
    est_in = _estimate_input_tokens(provider, model_str, messages)
    reserved_tokens = est_in + max_tokens
    reserved_cost = compute_cost(price, est_in, max_tokens)
    caps = _effective_caps(run_budget_overrides)

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    day_usd_key = f"{_KEY_PREFIX}budget:day:{today}:usd"
    day_tok_key = f"{_KEY_PREFIX}budget:day:{today}:tok"
    run_usd_key = f"{_KEY_PREFIX}budget:run:{run_id}:usd"
    run_tok_key = f"{_KEY_PREFIX}budget:run:{run_id}:tok"

    # Read both day+run counters in ONE round-trip.
    day_usd_s, day_tok_s, run_usd_s, run_tok_s = await r.mget(
        day_usd_key, day_tok_key, run_usd_key, run_tok_key
    )
    cur_day_usd = Decimal(day_usd_s) if day_usd_s else Decimal(0)
    cur_run_usd = Decimal(run_usd_s) if run_usd_s else Decimal(0)
    cur_day_tok = int(day_tok_s) if day_tok_s else 0
    cur_run_tok = int(run_tok_s) if run_tok_s else 0

    # Per-call (no accumulation), per-run, per-day on BOTH axes. Refuse on first breach.
    _check(reserved_cost, Decimal(str(caps["per_call_usd"])), "per_call", "usd")
    _check_tok(reserved_tokens, caps["per_call_tok"], "per_call")
    _check(cur_run_usd + reserved_cost, Decimal(str(caps["run_usd"])), "per_run", "usd")
    _check_tok(cur_run_tok + reserved_tokens, caps["run_tok"], "per_run")
    _check(cur_day_usd + reserved_cost, Decimal(str(caps["day_usd"])), "per_day", "usd")
    _check_tok(cur_day_tok + reserved_tokens, caps["day_tok"], "per_day")

    # (4) PROVIDER CALL (Plan 01 path).
    resp = await _invoke(
        model_str, messages, temperature=temperature, max_tokens=max_tokens
    )

    um = getattr(resp, "usage_metadata", None)
    if not um or um.get("input_tokens") is None or um.get("output_tokens") is None:
        # Cannot cost ⇒ refuse; never silently log $0 (Pitfall 3).
        raise MissingUsageMetadataError(operation_type)
    input_tokens = int(um["input_tokens"])
    output_tokens = int(um["output_tokens"])
    total_tokens = input_tokens + output_tokens
    cost_usd = compute_cost(price, input_tokens, output_tokens)

    # (5) RECONCILE: increment counters by ACTUAL usage (NOT the reservation,
    # Pitfall 2). One pipeline round-trip; TTLs self-clean the buckets.
    async with r.pipeline(transaction=True) as p:
        p.incrbyfloat(day_usd_key, float(cost_usd))
        p.incrby(day_tok_key, total_tokens)
        p.incrbyfloat(run_usd_key, float(cost_usd))
        p.incrby(run_tok_key, total_tokens)
        p.expire(day_usd_key, 172800)  # 2-day TTL GCs old daily buckets (Pitfall 4)
        p.expire(day_tok_key, 172800)
        p.expire(run_usd_key, settings.llm_run_ttl_s)
        p.expire(run_tok_key, settings.llm_run_ttl_s)
        results = await p.execute()
    new_day_usd = Decimal(str(results[0]))

    # (6) CACHE WRITE (D-12): on a miss+success, store content+usage with the
    # configured TTL — only for deterministic, cacheable calls (temp==0, not no_cache).
    if cache_key is not None:
        await r.set(
            cache_key,
            _serialize_result(
                getattr(resp, "content", None)
                if isinstance(getattr(resp, "content", None), str)
                else None,
                input_tokens,
                output_tokens,
            ),
            ex=settings.llm_cache_ttl_s,
        )

    # (7) AUTO-TRIP (D-05): daily USD exhaustion sets the global kill-switch.
    if new_day_usd >= Decimal(str(settings.llm_daily_usd_cap)):
        await r.set(_killswitch_key(), "daily-budget-exhausted")

    # (8) Ledger row + redaction-safe usage event (Plan 01).
    row = LLMUsage(
        run_id=run_id,
        operation_type=operation_type,
        provider=provider,
        model=model_str,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        cache_hit=False,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # Counts logged under tok_in/tok_out (the SENSITIVE regex matches "token", so
    # input_tokens/output_tokens/tokens_in would render [REDACTED]). No messages/
    # prompt/response or provider key ever enters the event.
    log.info(
        "llm_usage",
        operation_type=operation_type,
        run_id=run_id,
        provider=provider,
        model=model_str,
        tok_in=input_tokens,
        tok_out=output_tokens,
        cost_usd=str(cost_usd),
        cache_hit=False,
    )

    content = getattr(resp, "content", None)
    return LLMResult(
        content=content if isinstance(content, str) else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        cache_hit=False,
        provider=provider,
        model=model_str,
        run_id=run_id,
        operation_type=operation_type,
    )


async def _serve_cache_hit(
    db: AsyncSession,
    cached: dict,
    *,
    operation_type: str,
    run_id: str,
    provider: str,
    model_str: str,
) -> LLMResult:
    """Serve a Redis cache hit: $0, cache_hit=true ledger row, NO budget touched (D-12).

    A hit is reached only AFTER the kill-switch check passed (D-06). It writes ONE
    llm_usage row with cost_usd=0 and cache_hit=true (the cost-accounting gap a native
    LangChain cache would leave, Pitfall 1), skips the provider AND the budget
    pre-check/reconcile entirely, and returns the deserialized response.
    """
    input_tokens = int(cached["input_tokens"])
    output_tokens = int(cached["output_tokens"])

    row = LLMUsage(
        run_id=run_id,
        operation_type=operation_type,
        provider=provider,
        model=model_str,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=Decimal(0),
        cache_hit=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    log.info(
        "llm_usage",
        operation_type=operation_type,
        run_id=run_id,
        provider=provider,
        model=model_str,
        tok_in=input_tokens,
        tok_out=output_tokens,
        cost_usd="0",
        cache_hit=True,
    )

    return LLMResult(
        content=cached["content"],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=Decimal(0),
        cache_hit=True,
        provider=provider,
        model=model_str,
        run_id=run_id,
        operation_type=operation_type,
    )


def _check(value: Decimal, cap: Decimal, scope: str, axis: str) -> None:
    """Raise BudgetExceeded if `value` would exceed the USD `cap` for `scope`."""
    if value > cap:
        raise BudgetExceeded(scope, axis, f"{value} > {cap}")


def _check_tok(value: int, cap: int, scope: str) -> None:
    """Raise BudgetExceeded if `value` would exceed the token `cap` for `scope`."""
    if value > cap:
        raise BudgetExceeded(scope, "tokens", f"{value} > {cap}")
