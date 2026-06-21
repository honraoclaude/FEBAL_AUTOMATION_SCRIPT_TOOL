"""Tier → pytest-bdd selector map (EXEC-01 / D-01) — pure, keyless, no graph/db.

The tag tiers (smoke/sanity/regression) resolve to a `-m <tag>` pytest-bdd marker selector;
`full` resolves to NO filter (every approved spec). `risk-based` is an allow-listed tier whose
selection is computed dynamically (no -m), so it resolves to an empty selector here. Any tier
NOT on the allow-list raises ValueError (the router maps it to 422 — V5 input validation, T-07-05).
"""

from __future__ import annotations

import pytest

from app.services.exec_service import TIER_SELECTOR, resolve_tier


def test_tag_tiers_resolve_to_marker_selectors() -> None:
    assert resolve_tier("smoke") == ["-m", "smoke"]
    assert resolve_tier("sanity") == ["-m", "sanity"]
    assert resolve_tier("regression") == ["-m", "regression"]


def test_full_resolves_to_no_filter() -> None:
    assert resolve_tier("full") == []


def test_risk_based_is_allow_listed_with_no_marker_filter() -> None:
    # risk-based is a valid tier (dynamic selection) → no -m marker filter here.
    assert resolve_tier("risk-based") == []


def test_tier_selector_map_is_the_source_of_truth() -> None:
    assert TIER_SELECTOR["smoke"] == ["-m", "smoke"]
    assert TIER_SELECTOR["sanity"] == ["-m", "sanity"]
    assert TIER_SELECTOR["regression"] == ["-m", "regression"]
    assert TIER_SELECTOR["full"] == []


@pytest.mark.parametrize("bad", ["", "SMOKE", "drop table", "../etc", "risk_based", "all"])
def test_unknown_tier_raises_valueerror(bad: str) -> None:
    # Unknown tier is rejected against the allow-list (the router maps ValueError → 422).
    with pytest.raises(ValueError):
        resolve_tier(bad)


def test_selector_tokens_are_constants_not_the_client_string() -> None:
    # The selector tokens are module constants; the raw client string is NEVER echoed into argv
    # (T-07-05 — even a valid tier produces the fixed token list, not a reflected input).
    selector = resolve_tier("smoke")
    assert selector is not TIER_SELECTOR["smoke"]  # a copy, never the shared mutable list
    assert selector == ["-m", "smoke"]
