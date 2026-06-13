"""Kill-switch auto-trip + hot-path halt unit tests (PLAT-06, D-05/D-06).

- Auto-trip: when a reconcile pushes the day USD counter to >= the daily cap, the
  gateway SETs llm:killswitch; the next call raises KillSwitchActive before any spend.
- Hot-path halt: with the flag already set, complete() raises KillSwitchActive
  BEFORE the pre-check or any provider call.
"""

import uuid
from datetime import datetime, timezone

import pytest

import app.services.llm_gateway as gateway
from app.core.config import settings
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


async def test_daily_exhaustion_auto_trips_and_next_call_halts(
    patch_redis, fake_chat_model, small_input_tokens, monkeypatch
):
    """A reconcile that lands day USD >= the daily cap SETs the kill flag; the very
    next complete() raises KillSwitchActive before invoking the provider."""
    # Cap == the exact actual cost so the pre-check reserve (est_in=100, out=50 ==
    # actual) passes (reserve <= cap) and the reconcile lands day USD == cap, tripping.
    # reserve/actual cost = 100*3/1e6 + 50*15/1e6 = $0.001050.
    monkeypatch.setattr(settings, "llm_daily_usd_cap", 0.001050)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    fake_chat_model.set(
        content="ok",
        usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    )

    # First call succeeds; its reconcile pushes day USD (~$0.00105) >= the cap.
    await gateway.complete(
        _DBSentinel(),
        [{"role": "user", "content": "hi"}],
        operation_type="test.autotrip",
        run_id=uuid.uuid4().hex,
        model=MODEL,
        max_tokens=50,
    )

    flag = await patch_redis.get("test:llm:killswitch")
    assert flag == "daily-budget-exhausted"

    calls_before = len(fake_chat_model.calls)
    with pytest.raises(KillSwitchActive):
        await gateway.complete(
            _DBSentinel(),
            [{"role": "user", "content": "hi"}],
            operation_type="test.autotrip",
            run_id=uuid.uuid4().hex,
            model=MODEL,
            max_tokens=100,
        )
    assert len(fake_chat_model.calls) == calls_before, "no provider call once tripped"


async def test_killswitch_set_halts_on_hot_path(
    patch_redis, fake_chat_model, small_input_tokens
):
    """With the flag already set, complete() raises KillSwitchActive before any
    pre-check or provider invocation."""
    await patch_redis.set("test:llm:killswitch", "manual-panic")

    with pytest.raises(KillSwitchActive):
        await gateway.complete(
            _DBSentinel(),
            [{"role": "user", "content": "hi"}],
            operation_type="test.halt",
            run_id=uuid.uuid4().hex,
            model=MODEL,
            max_tokens=100,
        )
    assert fake_chat_model.calls == [], "kill check must precede the provider call"
