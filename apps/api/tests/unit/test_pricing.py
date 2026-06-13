"""Unit tests for the effective-dated pricing table (PLAT-06, D-08/D-13).

No provider, no DB, no spend — pure data + function tests. Covers:
  - effective-dating: a NEWER price row does not change a cost computed earlier
  - fail-closed: unknown model raises UnknownModelPriceError
  - compute_cost returns a correct Decimal
  - FIX-1: a provider-PREFIXED model string resolves to the SAME row as its
    bare name (so real init_chat_model-shaped calls cost correctly).
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core import llm_pricing
from app.core.llm_pricing import (
    PRICING,
    PriceRow,
    UnknownModelPriceError,
    compute_cost,
    lookup_price,
)

# A real seeded bare model name to exercise prefix resolution against.
_SEEDED = PRICING[0].model  # e.g. "claude-sonnet-4-5"


def test_lookup_returns_most_recent_effective_row(monkeypatch):
    """With two rows for one model, a date returns the newest row at/under it."""
    old = PriceRow(model="m-x", input_per_mtok=1.0, output_per_mtok=2.0, effective_date=date(2026, 1, 1))
    new = PriceRow(model="m-x", input_per_mtok=5.0, output_per_mtok=9.0, effective_date=date(2026, 6, 1))
    monkeypatch.setattr(llm_pricing, "PRICING", [old, new])

    assert lookup_price("m-x", at=date(2026, 3, 1)) is old  # before the new row
    assert lookup_price("m-x", at=date(2026, 7, 1)) is new  # after the new row


def test_effective_dating_preserves_historical_cost(monkeypatch):
    """Adding a NEWER price row does not change a cost computed at an earlier date."""
    old = PriceRow(model="m-y", input_per_mtok=2.0, output_per_mtok=4.0, effective_date=date(2026, 1, 1))
    monkeypatch.setattr(llm_pricing, "PRICING", [old])
    cost_then = compute_cost(lookup_price("m-y", at=date(2026, 2, 1)), 1_000_000, 1_000_000)

    new = PriceRow(model="m-y", input_per_mtok=99.0, output_per_mtok=99.0, effective_date=date(2026, 5, 1))
    monkeypatch.setattr(llm_pricing, "PRICING", [old, new])
    cost_recomputed_at_old_date = compute_cost(
        lookup_price("m-y", at=date(2026, 2, 1)), 1_000_000, 1_000_000
    )

    assert cost_then == cost_recomputed_at_old_date == Decimal("6.000000")


def test_unknown_model_raises():
    with pytest.raises(UnknownModelPriceError):
        lookup_price("nope-not-a-model")


def test_compute_cost_is_decimal_and_correct():
    price = PriceRow(model="m-z", input_per_mtok=3.0, output_per_mtok=15.0, effective_date=date(2026, 1, 1))
    cost = compute_cost(price, 1000, 2000)
    # 1000/1e6*3 + 2000/1e6*15 = 0.003 + 0.030 = 0.033
    assert isinstance(cost, Decimal)
    assert cost == Decimal("0.033000")


def test_provider_prefixed_resolves_to_bare_row():
    """FIX-1: a provider-prefixed model string resolves to the same row as bare."""
    bare = lookup_price(_SEEDED)
    prefixed = lookup_price(f"anthropic:{_SEEDED}")
    assert prefixed is bare

    # And likewise for the OpenAI-seeded row.
    openai_seeded = PRICING[1].model
    assert lookup_price(f"openai:{openai_seeded}") is lookup_price(openai_seeded)


def test_provider_prefixed_does_not_raise():
    """A real init_chat_model-shaped prefixed string must NOT fail closed."""
    row = lookup_price(f"anthropic:{_SEEDED}")
    assert row.model == _SEEDED
