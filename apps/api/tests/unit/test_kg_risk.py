"""KG-04 pure risk-formula proof (default gate — NO keys, NO neo4j, NO LLM).

DISTINCT from `tests/unit/test_risk.py` (the explorer ACTION deny-list / origin gate). This
covers `kg/risk.py` — the per-FLOW deterministic 0-100 score (RESEARCH:568 "new kg/risk;
distinct from explorer/risk").

`risk_score(signals)` is a PURE, deterministic, clamped 0-100 weighted sum (D-04: a number
users act on must be reproducible/auditable, never LLM judgment). This table test pins:
  - the three tiers separate at 67 (high) / 34 (medium) / <34 (low),
  - the clamp at BOTH ends (a maximal signal set clamps to 100; an empty set scores 0/low),
  - tier-boundary behavior at 33/34 and 66/67,
  - custom weights change the score (the formula is swappable).

`kg/risk.py` must import NO neo4j / llm_gateway / SessionLocal (verified below) — the safety
discipline mirrors `explorer/risk.py` ("PURE CODE, NEVER LLM JUDGMENT").
"""

from __future__ import annotations

import pytest

from app.services.kg.risk import (
    DEFAULT_WEIGHTS,
    RiskWeights,
    risk_score,
    risk_tier,
)


def _signals(
    *, has_destructive=False, state_change_edges=0, auth_gated_steps=0,
    form_count=0, path_length=0,
):
    return {
        "has_destructive": has_destructive,
        "state_change_edges": state_change_edges,
        "auth_gated_steps": auth_gated_steps,
        "form_count": form_count,
        "path_length": path_length,
    }


def test_empty_signals_score_zero_low() -> None:
    s = _signals()
    assert risk_score(s) == 0
    assert risk_tier(risk_score(s)) == "low"


def test_login_navigation_is_low() -> None:
    # A single login navigation: 2 auth-gated steps over a 2-hop path, no destructive/forms.
    s = _signals(auth_gated_steps=2, path_length=2)
    score = risk_score(s)  # 6*2 + 3*2 = 18
    assert score < 34
    assert risk_tier(score) == "low"


def test_destructive_plus_state_changes_is_high() -> None:
    # Destructive action + several state-change edges -> High (>=67).
    s = _signals(has_destructive=True, state_change_edges=3, auth_gated_steps=2, path_length=3)
    score = risk_score(s)  # 40 + 8*3 + 6*2 + 3*3 = 85
    assert score >= 67
    assert risk_tier(score) == "high"


def test_clamp_at_100() -> None:
    # A maximal signal set overruns the weighted sum well past 100 -> clamps to 100.
    s = _signals(
        has_destructive=True, state_change_edges=20, auth_gated_steps=20,
        form_count=20, path_length=20,
    )
    assert risk_score(s) == 100
    assert risk_tier(risk_score(s)) == "high"


def test_clamp_floor_at_0_with_negative_weights() -> None:
    # Even pathological negative custom weights can never drive the score below 0.
    neg = RiskWeights(destructive_action=-999)
    s = _signals(has_destructive=True)
    assert risk_score(s, neg) == 0


@pytest.mark.parametrize(
    "score,expected_tier",
    [
        (0, "low"),
        (33, "low"),
        (34, "medium"),
        (66, "medium"),
        (67, "high"),
        (100, "high"),
    ],
)
def test_tier_boundaries(score: int, expected_tier: str) -> None:
    assert risk_tier(score) == expected_tier


def test_custom_weights_change_score() -> None:
    s = _signals(state_change_edges=2)
    default = risk_score(s, DEFAULT_WEIGHTS)
    heavier = risk_score(s, RiskWeights(per_state_change=DEFAULT_WEIGHTS.per_state_change + 10))
    assert heavier > default


def test_missing_signal_keys_default_to_zero() -> None:
    # A partial signal dict (only path_length) must not KeyError — absent keys score 0.
    assert risk_score({"path_length": 1}) == DEFAULT_WEIGHTS.depth


def test_risk_module_imports_no_stack() -> None:
    # D-04: the risk module is PURE — it must not import neo4j / llm_gateway / SessionLocal.
    import inspect

    import app.services.kg.risk as risk_mod

    src = inspect.getsource(risk_mod)
    for forbidden in ("neo4j", "llm_gateway", "SessionLocal"):
        assert forbidden not in src, f"risk.py must not reference {forbidden!r} (D-04: pure)"


def test_weights_are_frozen() -> None:
    with pytest.raises(Exception):
        DEFAULT_WEIGHTS.destructive_action = 1  # type: ignore[misc]
