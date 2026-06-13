"""Effective-dated LLM pricing table + cost computation (PLAT-06, D-08).

Prices are versioned by effective_date so a price change never rewrites the
cost of a historical operation: the ledger stores the COMPUTED cost, and a
lookup at a past date still returns the row that was effective then.

CANONICAL KEY (D-08/D-13, FIX-1): init_chat_model resolves models as the
provider-PREFIXED string ("anthropic:claude-...", "openai:gpt-..."), but the
PRICING rows below are keyed on the BARE model name. The single canonical key
is the bare name; lookup_price normalizes the incoming (possibly prefixed)
string via _bare_model BEFORE matching, so both lookup_price("claude-...") and
lookup_price("anthropic:claude-...") resolve to the same row. Fail closed: an
unpriced model raises UnknownModelPriceError rather than logging $0.

This module deliberately has NO logger (mirrors crypto.py) — pure data + functions.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel


class UnknownModelPriceError(Exception):
    """Raised when no pricing row matches a model — fail-closed (never cost $0)."""


class PriceRow(BaseModel):
    model: str  # BARE model name (no provider prefix)
    input_per_mtok: float  # USD per 1M input tokens
    output_per_mtok: float  # USD per 1M output tokens
    effective_date: date


# Manually maintained; no runtime dependency on provider pricing APIs (D-08).
# Add a NEW row (newer effective_date) when a price changes — never edit old rows.
PRICING: list[PriceRow] = [
    PriceRow(
        model="claude-sonnet-4-5",
        input_per_mtok=3.00,
        output_per_mtok=15.00,
        effective_date=date(2026, 1, 1),
    ),
    PriceRow(
        model="gpt-4.1",
        input_per_mtok=2.00,
        output_per_mtok=8.00,
        effective_date=date(2026, 1, 1),
    ),
]


def _bare_model(model: str) -> str:
    """Strip a leading '<provider>:' prefix, returning the bare model name.

    "anthropic:claude-sonnet-4-5" -> "claude-sonnet-4-5"
    "claude-sonnet-4-5"           -> "claude-sonnet-4-5"
    """
    _, sep, rest = model.partition(":")
    return rest if sep else model


def lookup_price(model: str, at: date | None = None) -> PriceRow:
    """Most-recent effective PriceRow at/under `at` for `model`.

    `model` may be provider-prefixed (the form init_chat_model consumes); it is
    normalized to the bare key before matching. Raises UnknownModelPriceError
    when nothing matches (fail-closed — refuse calls we cannot cost).
    """
    at = at or date.today()
    bare = _bare_model(model)
    rows = sorted(
        (p for p in PRICING if p.model == bare and p.effective_date <= at),
        key=lambda p: p.effective_date,
    )
    if not rows:
        raise UnknownModelPriceError(model)
    return rows[-1]


def compute_cost(price: PriceRow, input_tokens: int, output_tokens: int) -> Decimal:
    """USD cost as Decimal (money is never float at storage), quantized to 6 places."""
    cost = (
        Decimal(input_tokens) / Decimal(1_000_000) * Decimal(str(price.input_per_mtok))
        + Decimal(output_tokens) / Decimal(1_000_000) * Decimal(str(price.output_per_mtok))
    )
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
