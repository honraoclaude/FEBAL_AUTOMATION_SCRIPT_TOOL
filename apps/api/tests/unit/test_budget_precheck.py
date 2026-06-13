"""Budget PRE-CHECK unit tests (PLAT-06, D-01/D-02/D-03/D-04).

Mocked init_chat_model (no provider, no spend) + the compose Redis under a test
key prefix. These assert the gateway refuses budget-breaching calls BEFORE any
provider invocation, on EITHER the USD or token axis, in any scope, and that a
per-run override may only TIGHTEN (RESEARCH Q4 clamp).
"""

import uuid

import pytest

import app.services.llm_gateway as gateway
from app.core.config import settings
from app.services.llm_gateway import BudgetExceeded

# A pricing row exists for "anthropic:claude-sonnet-4-5": $3/Mtok in, $15/Mtok out.
MODEL = "anthropic:claude-sonnet-4-5"


@pytest.fixture
def patch_redis(monkeypatch, redis_test):
    """Point the gateway's get_redis() at the prefixed-flush test client.

    Also namespaces the gateway's Redis keys under the test prefix so the
    redis_test fixture's flush cleans them and dev counters are never touched.
    """
    monkeypatch.setattr(gateway, "get_redis", lambda: redis_test)
    monkeypatch.setattr(gateway, "_KEY_PREFIX", "test:llm:")
    return redis_test


@pytest.fixture
def small_input_tokens(monkeypatch):
    """Force the input-token pre-estimate to a fixed small value (no live count)."""
    monkeypatch.setattr(
        gateway, "_estimate_input_tokens", lambda provider, model, messages: 100
    )


async def test_precheck_per_call_usd_breach_refuses_before_spend(
    patch_redis, fake_chat_model, small_input_tokens, monkeypatch
):
    """A reserved estimate over the per-call USD cap raises BudgetExceeded and
    makes NO provider call and writes NO ledger row."""
    monkeypatch.setattr(settings, "llm_per_call_usd_cap", 0.01)  # tiny cap
    # reserve: 100 in + 1_000_000 out at $15/Mtok out ≈ $15 >> $0.01 cap.
    sentinel = _DBSentinel()

    with pytest.raises(BudgetExceeded):
        await gateway.complete(
            sentinel,
            [{"role": "user", "content": "hi"}],
            operation_type="test.precheck",
            run_id=uuid.uuid4().hex,
            model=MODEL,
            max_tokens=1_000_000,
        )

    assert fake_chat_model.calls == [], "provider must not be invoked on breach"
    assert sentinel.added == [], "no ledger row on breach"


async def test_precheck_under_caps_proceeds(
    patch_redis, fake_chat_model, small_input_tokens
):
    """A call comfortably under all caps proceeds and invokes the provider."""
    fake_chat_model.set(
        content="ok",
        usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    )
    sentinel = _DBSentinel()

    result = await gateway.complete(
        sentinel,
        [{"role": "user", "content": "hi"}],
        operation_type="test.precheck",
        run_id=uuid.uuid4().hex,
        model=MODEL,
        max_tokens=200,
    )

    assert len(fake_chat_model.calls) == 1
    assert result.input_tokens == 100
    assert result.output_tokens == 50


async def test_precheck_per_run_token_breach(
    patch_redis, fake_chat_model, small_input_tokens, monkeypatch
):
    """Seed the run token counter near the cap; a call that would push it over
    raises BudgetExceeded (token axis, run scope) with no spend."""
    monkeypatch.setattr(settings, "llm_run_token_cap", 1000)
    run_id = uuid.uuid4().hex
    # Seed run token counter to 950; reserve = 100 in + 200 out = 300 -> 1250 > 1000.
    await patch_redis.set(f"test:llm:budget:run:{run_id}:tok", 950)

    with pytest.raises(BudgetExceeded):
        await gateway.complete(
            _DBSentinel(),
            [{"role": "user", "content": "hi"}],
            operation_type="test.precheck",
            run_id=run_id,
            model=MODEL,
            max_tokens=200,
        )
    assert fake_chat_model.calls == []


async def test_precheck_per_day_usd_breach(
    patch_redis, fake_chat_model, small_input_tokens, monkeypatch
):
    """Seed the day USD counter near the cap; a reserve that would push it over
    raises BudgetExceeded (USD axis, day scope)."""
    from datetime import datetime, timezone

    monkeypatch.setattr(settings, "llm_daily_usd_cap", 1.0)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    await patch_redis.set(f"test:llm:budget:day:{today}:usd", "0.99")

    # reserve ~ 100*3/1e6 + 100_000*15/1e6 ≈ $1.5 -> 0.99 + 1.5 = 2.49 > 1.0 cap.
    with pytest.raises(BudgetExceeded):
        await gateway.complete(
            _DBSentinel(),
            [{"role": "user", "content": "hi"}],
            operation_type="test.precheck",
            run_id=uuid.uuid4().hex,
            model=MODEL,
            max_tokens=100_000,
        )
    assert fake_chat_model.calls == []


async def test_per_run_override_clamps_to_global_ceiling(
    patch_redis, fake_chat_model, small_input_tokens, monkeypatch
):
    """A per-run override LOOSER than the global cap is clamped DOWN (cannot loosen);
    a TIGHTER override is honored."""
    monkeypatch.setattr(settings, "llm_per_call_usd_cap", 0.01)
    run_id = uuid.uuid4().hex

    # Loose override ($100) must NOT loosen past the $0.01 global ceiling -> still breaches.
    with pytest.raises(BudgetExceeded):
        await gateway.complete(
            _DBSentinel(),
            [{"role": "user", "content": "hi"}],
            operation_type="test.precheck",
            run_id=run_id,
            model=MODEL,
            max_tokens=1_000_000,  # reserve ~ $15
            run_budget_overrides={"per_call_usd_cap": 100.0},
        )
    assert fake_chat_model.calls == []

    # Tighter override honored: a generous global cap but a tiny run override breaches.
    monkeypatch.setattr(settings, "llm_per_call_usd_cap", 1000.0)
    fake_chat_model.set(
        content="ok",
        usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    )
    with pytest.raises(BudgetExceeded):
        await gateway.complete(
            _DBSentinel(),
            [{"role": "user", "content": "hi"}],
            operation_type="test.precheck",
            run_id=uuid.uuid4().hex,
            model=MODEL,
            max_tokens=1_000_000,
            run_budget_overrides={"per_call_usd_cap": 0.01},  # tighter -> breaches
        )


class _DBSentinel:
    """Stand-in AsyncSession recording add()/commit()/refresh() so tests can assert
    NO ledger row was written on a budget breach."""

    def __init__(self):
        self.added: list = []
        self.committed = False

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.committed = True

    async def refresh(self, row):
        return None
