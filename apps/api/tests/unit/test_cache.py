"""Custom Redis response-cache unit tests (PLAT-06, D-11/D-12, T-02-13/14/15/19).

The gateway caches ONLY deterministic (temperature==0, not no_cache) calls. A cache
HIT returns the stored content for $0, writes ONE ledger row with cache_hit=true and
cost_usd=0, makes NO provider call, and touches NO budget counter. The cache key is a
SHA-256 over provider+model+normalized messages+params; any difference misses.

CRITICAL (D-06, T-02-19): the kill-switch GET runs BEFORE the cache lookup, so an active
halt refuses even a would-be cache hit (Test 5) — a cached response is still gateway
output and the panic button may be pulled for non-cost reasons.

Uses the autouse gateway-Redis isolation fixture (test:llm: prefix, per-test client) from
tests/unit/conftest.py plus fake_chat_model (no provider, no spend).
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

import app.services.llm_gateway as gateway
from app.services.llm_gateway import KillSwitchActive

MODEL = "anthropic:claude-sonnet-4-5"


@pytest.fixture
def patch_redis(monkeypatch, redis_test):
    monkeypatch.setattr(gateway, "get_redis", lambda: redis_test)
    monkeypatch.setattr(gateway, "_KEY_PREFIX", "test:llm:")
    return redis_test


@pytest.fixture
def small_input_tokens(monkeypatch):
    monkeypatch.setattr(
        gateway, "_estimate_input_tokens", lambda provider, model, messages: 100
    )


class _DBSentinel:
    def __init__(self):
        self.added: list = []

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        return None

    async def refresh(self, row):
        return None


def _msgs():
    return [{"role": "user", "content": "what is 2+2?"}]


async def _counters(redis_test, run_id):
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return {
        "day_usd": await redis_test.get(f"test:llm:budget:day:{today}:usd"),
        "day_tok": await redis_test.get(f"test:llm:budget:day:{today}:tok"),
        "run_usd": await redis_test.get(f"test:llm:budget:run:{run_id}:usd"),
        "run_tok": await redis_test.get(f"test:llm:budget:run:{run_id}:tok"),
    }


# --- Test 1 + budget-untouched: identical temp==0 calls -> 2nd is a cache hit -----
async def test_identical_temp0_second_call_hits_cache(
    patch_redis, fake_chat_model, small_input_tokens
):
    fake_chat_model.set(
        content="four",
        usage_metadata={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
    )
    run_id = uuid.uuid4().hex

    first = await gateway.complete(
        _DBSentinel(),
        _msgs(),
        operation_type="test.cache",
        run_id=run_id,
        model=MODEL,
        temperature=0,
        max_tokens=100,
    )
    assert first.cache_hit is False
    calls_after_first = len(fake_chat_model.calls)
    assert calls_after_first == 1
    counters_after_first = await _counters(patch_redis, run_id)

    # Identical second call -> served from cache.
    second = await gateway.complete(
        _DBSentinel(),
        _msgs(),
        operation_type="test.cache",
        run_id=run_id,
        model=MODEL,
        temperature=0,
        max_tokens=100,
    )
    assert second.cache_hit is True
    assert second.content == "four"
    assert second.cost_usd == Decimal(0)
    # Provider NOT called a second time.
    assert len(fake_chat_model.calls) == calls_after_first == 1
    # Budget counters UNCHANGED by the hit.
    assert await _counters(patch_redis, run_id) == counters_after_first


# --- Test 2: cache hit still writes ONE ledger row (cache_hit=true, cost 0) --------
async def test_cache_hit_writes_ledger_row(
    patch_redis, fake_chat_model, small_input_tokens
):
    fake_chat_model.set(
        content="four",
        usage_metadata={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
    )
    run_id = uuid.uuid4().hex
    await gateway.complete(
        _DBSentinel(), _msgs(), operation_type="test.cache",
        run_id=run_id, model=MODEL, temperature=0, max_tokens=100,
    )
    db2 = _DBSentinel()
    result = await gateway.complete(
        db2, _msgs(), operation_type="test.cache",
        run_id=run_id, model=MODEL, temperature=0, max_tokens=100,
    )
    assert result.cache_hit is True
    assert len(db2.added) == 1, "cache hit writes exactly one ledger row (D-12)"
    row = db2.added[0]
    assert row.cache_hit is True
    assert Decimal(str(row.cost_usd)) == Decimal(0)
    # Token counts come from the cached usage, not zero.
    assert row.input_tokens == 12
    assert row.output_tokens == 3


# --- Test 3: key sensitivity — any param/message/model diff misses -----------------
@pytest.mark.parametrize(
    "variant",
    ["model", "message", "temperature_nonzero_skip", "max_tokens", "tools"],
)
async def test_key_sensitivity_misses(
    patch_redis, fake_chat_model, small_input_tokens, variant
):
    fake_chat_model.set(
        content="four",
        usage_metadata={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
    )
    run_id = uuid.uuid4().hex
    base = dict(
        operation_type="test.cache", run_id=run_id, model=MODEL,
        temperature=0, max_tokens=100,
    )
    # Prime cache.
    await gateway.complete(_DBSentinel(), _msgs(), **base)
    calls_after_prime = len(fake_chat_model.calls)
    assert calls_after_prime == 1

    # A varied call must MISS -> provider invoked again.
    if variant == "model":
        await gateway.complete(
            _DBSentinel(), _msgs(),
            **{**base, "model": "openai:gpt-4.1"},
        )
    elif variant == "message":
        await gateway.complete(
            _DBSentinel(), [{"role": "user", "content": "different question"}], **base
        )
    elif variant == "max_tokens":
        await gateway.complete(_DBSentinel(), _msgs(), **{**base, "max_tokens": 200})
    elif variant == "tools":
        key_a = gateway._cache_key("anthropic", MODEL, _msgs(), 0, 100, None)
        key_b = gateway._cache_key(
            "anthropic", MODEL, _msgs(), 0, 100, [{"name": "t"}]
        )
        assert key_a != key_b
        return
    elif variant == "temperature_nonzero_skip":
        # temperature>0 is never cached at all (no read, no write) -> always a miss.
        await gateway.complete(_DBSentinel(), _msgs(), **{**base, "temperature": 0.7})

    assert len(fake_chat_model.calls) == calls_after_prime + 1, "varied call missed cache"


# --- Test 4: no-cache paths — temp>0 and no_cache never read/write -----------------
async def test_no_cache_paths(patch_redis, fake_chat_model, small_input_tokens):
    fake_chat_model.set(
        content="four",
        usage_metadata={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
    )
    run_id = uuid.uuid4().hex

    # temperature>0: never cached. Two identical calls both hit the provider.
    await gateway.complete(
        _DBSentinel(), _msgs(), operation_type="test.cache",
        run_id=run_id, model=MODEL, temperature=0.7, max_tokens=100,
    )
    await gateway.complete(
        _DBSentinel(), _msgs(), operation_type="test.cache",
        run_id=run_id, model=MODEL, temperature=0.7, max_tokens=100,
    )
    assert len(fake_chat_model.calls) == 2, "temp>0 never caches (no read/write)"
    # And no cache key was written.
    keys = [k async for k in patch_redis.scan_iter(match="test:llm:cache:*")]
    assert keys == [], "temp>0 wrote no cache entry"

    # no_cache=true at temp==0: never read, never written.
    await gateway.complete(
        _DBSentinel(), _msgs(), operation_type="test.cache",
        run_id=run_id, model=MODEL, temperature=0, max_tokens=100, no_cache=True,
    )
    await gateway.complete(
        _DBSentinel(), _msgs(), operation_type="test.cache",
        run_id=run_id, model=MODEL, temperature=0, max_tokens=100, no_cache=True,
    )
    assert len(fake_chat_model.calls) == 4, "no_cache=true never caches even at temp==0"
    keys = [k async for k in patch_redis.scan_iter(match="test:llm:cache:*")]
    assert keys == [], "no_cache=true wrote no cache entry"


# --- Test 5: kill-switch precedes cache (D-06, T-02-19) ---------------------------
async def test_killswitch_precedes_cache(
    patch_redis, fake_chat_model, small_input_tokens
):
    """Prime the cache with one temp==0 call, then set the kill-switch. The next
    identical (would-be cache-hit) call MUST raise KillSwitchActive, NOT serve the
    cached value, and NOT invoke the provider — kill-switch is checked BEFORE cache."""
    fake_chat_model.set(
        content="four",
        usage_metadata={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
    )
    run_id = uuid.uuid4().hex
    await gateway.complete(
        _DBSentinel(), _msgs(), operation_type="test.cache",
        run_id=run_id, model=MODEL, temperature=0, max_tokens=100,
    )
    calls_before = len(fake_chat_model.calls)
    assert calls_before == 1

    # Trip the kill-switch under the test prefix.
    await patch_redis.set("test:llm:killswitch", "security-halt")

    with pytest.raises(KillSwitchActive):
        await gateway.complete(
            _DBSentinel(), _msgs(), operation_type="test.cache",
            run_id=run_id, model=MODEL, temperature=0, max_tokens=100,
        )
    # No provider call AND no cached value served (the call raised, returned nothing).
    assert len(fake_chat_model.calls) == calls_before, "halt: no provider call"
