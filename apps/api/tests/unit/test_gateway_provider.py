"""Unit tests for the LLM gateway complete() — mocked provider, no spend (PLAT-05/06).

Drives the gateway through the `fake_chat_model` fixture (patches
app.services.llm_gateway.init_chat_model). A lightweight capture session stands
in for the DB so the pure call/cost/exception logic needs no live Postgres.
"""

from decimal import Decimal

import pytest

from app.core.llm_pricing import (
    PRICING,
    UnknownModelPriceError,
    compute_cost,
    lookup_price,
)
from app.services import llm_gateway

_ANTHROPIC_MODEL = f"anthropic:{PRICING[0].model}"  # seeded claude row
_OPENAI_MODEL = f"openai:{PRICING[1].model}"  # seeded gpt row


class CaptureSession:
    """Stand-in AsyncSession that records added rows; commit/refresh are no-ops."""

    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        return None

    async def refresh(self, row):
        return None


async def test_default_model_resolves_provider(fake_chat_model):
    """With no per-call model, the settings default model is passed to init_chat_model."""
    db = CaptureSession()
    fake_chat_model.set(
        content="hi",
        usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    )
    result = await llm_gateway.complete(
        db,
        [{"role": "user", "content": "hi"}],
        operation_type="test.op",
        max_tokens=64,
    )
    # The gateway resolved the settings default and called init_chat_model with it.
    assert fake_chat_model.calls, "init_chat_model was not called"
    model_str = fake_chat_model.calls[-1]["model_str"]
    assert ":" in model_str  # provider-prefixed
    assert result.provider == model_str.split(":", 1)[0]
    assert result.input_tokens == 100
    assert result.output_tokens == 50


async def test_per_call_model_override(fake_chat_model):
    """A per-call model overrides the default and changes the resolved provider."""
    db = CaptureSession()
    fake_chat_model.set(
        usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}
    )
    result = await llm_gateway.complete(
        db,
        [{"role": "user", "content": "x"}],
        operation_type="test.op",
        model=_OPENAI_MODEL,
        max_tokens=8,
    )
    assert fake_chat_model.calls[-1]["model_str"] == _OPENAI_MODEL
    assert result.provider == "openai"
    assert result.model == _OPENAI_MODEL


async def test_run_id_generated_when_absent(fake_chat_model):
    db = CaptureSession()
    fake_chat_model.set(
        usage_metadata={"input_tokens": 2, "output_tokens": 2, "total_tokens": 4}
    )
    result = await llm_gateway.complete(
        db, [{"role": "user", "content": "x"}], operation_type="op", max_tokens=8
    )
    assert result.run_id  # non-empty uuid hex


async def test_run_id_used_when_provided(fake_chat_model):
    db = CaptureSession()
    fake_chat_model.set(
        usage_metadata={"input_tokens": 2, "output_tokens": 2, "total_tokens": 4}
    )
    result = await llm_gateway.complete(
        db,
        [{"role": "user", "content": "x"}],
        operation_type="op",
        run_id="run-abc",
        max_tokens=8,
    )
    assert result.run_id == "run-abc"


async def test_cost_matches_pricing_for_prefixed_model(fake_chat_model):
    """FIX-1: cost == compute_cost(lookup_price(PREFIXED model_str), in, out), non-zero."""
    db = CaptureSession()
    fake_chat_model.set(
        usage_metadata={"input_tokens": 1000, "output_tokens": 2000, "total_tokens": 3000}
    )
    result = await llm_gateway.complete(
        db,
        [{"role": "user", "content": "x"}],
        operation_type="op",
        model=_ANTHROPIC_MODEL,
        max_tokens=2048,
    )
    expected = compute_cost(lookup_price(_ANTHROPIC_MODEL), 1000, 2000)
    assert result.cost_usd == expected
    assert result.cost_usd > Decimal("0")
    # Exactly one ledger row written.
    assert len(db.added) == 1
    assert db.added[0].cost_usd == expected


async def test_unpriced_model_raises_and_writes_no_row(fake_chat_model):
    db = CaptureSession()
    fake_chat_model.set(
        usage_metadata={"input_tokens": 5, "output_tokens": 5, "total_tokens": 10}
    )
    with pytest.raises(UnknownModelPriceError):
        await llm_gateway.complete(
            db,
            [{"role": "user", "content": "x"}],
            operation_type="op",
            model="anthropic:not-a-real-model",
            max_tokens=8,
        )
    assert db.added == []


async def test_missing_usage_metadata_fails_closed(fake_chat_model):
    """usage_metadata None -> raise, never log $0 (Pitfall 3)."""
    db = CaptureSession()
    fake_chat_model.set(usage_metadata=None)
    with pytest.raises(Exception):  # noqa: B017 -- fail-closed of any type, no ledger row
        await llm_gateway.complete(
            db,
            [{"role": "user", "content": "x"}],
            operation_type="op",
            model=_ANTHROPIC_MODEL,
            max_tokens=8,
        )
    assert db.added == []
