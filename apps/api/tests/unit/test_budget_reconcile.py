"""Budget RECONCILE unit test (PLAT-06, D-01, Pitfall 2).

After a successful call the gateway increments Redis day+run counters by the
ACTUAL usage (from usage_metadata), NOT by the reserved max_tokens. The ledger
row's cost_usd equals the day USD counter delta.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

import app.services.llm_gateway as gateway

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


async def test_reconcile_increments_by_actual_not_reserved(
    patch_redis, fake_chat_model, small_input_tokens
):
    """Counters move by ACTUAL (in=100, out=50 -> 150 tokens), not by the reserved
    max_tokens (50_000). Day USD delta equals the ledger row cost_usd."""
    actual_in, actual_out = 100, 50
    fake_chat_model.set(
        content="ok",
        usage_metadata={
            "input_tokens": actual_in,
            "output_tokens": actual_out,
            "total_tokens": actual_in + actual_out,
        },
    )
    run_id = uuid.uuid4().hex
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    db = _DBSentinel()

    result = await gateway.complete(
        db,
        [{"role": "user", "content": "hi"}],
        operation_type="test.reconcile",
        run_id=run_id,
        model=MODEL,
        max_tokens=50_000,  # large reservation — must NOT be what counters move by
    )

    day_tok = await patch_redis.get(f"test:llm:budget:day:{today}:tok")
    run_tok = await patch_redis.get(f"test:llm:budget:run:{run_id}:tok")
    day_usd = await patch_redis.get(f"test:llm:budget:day:{today}:usd")
    run_usd = await patch_redis.get(f"test:llm:budget:run:{run_id}:usd")

    # ACTUAL total tokens, not the reserved 50_000.
    assert int(day_tok) == actual_in + actual_out == 150
    assert int(run_tok) == 150

    # Day USD delta == ledger cost_usd (this was the only call, so delta == counter).
    expected_cost = Decimal("0.000300") + Decimal("0.000750")  # 100*3/1e6 + 50*15/1e6
    assert Decimal(day_usd) == expected_cost
    assert Decimal(run_usd) == expected_cost

    assert len(db.added) == 1, "exactly one ledger row written"
    assert db.added[0].cost_usd == result.cost_usd == expected_cost


async def test_run_counters_have_ttl(patch_redis, fake_chat_model, small_input_tokens):
    """Per-run counters carry the configured TTL (self-cleanup)."""
    fake_chat_model.set(
        content="ok",
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )
    run_id = uuid.uuid4().hex
    await gateway.complete(
        _DBSentinel(),
        [{"role": "user", "content": "hi"}],
        operation_type="test.reconcile",
        run_id=run_id,
        model=MODEL,
        max_tokens=100,
    )
    ttl = await patch_redis.ttl(f"test:llm:budget:run:{run_id}:usd")
    assert ttl > 0, "run counter must expire (TTL set)"
