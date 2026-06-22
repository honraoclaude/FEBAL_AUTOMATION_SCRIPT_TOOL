"""HEAL-01 pure confidence-blend proof (default gate — NO keys, NO neo4j, NO LLM, NO browser).

`confidence(signals, w)` is a PURE, deterministic, clamped [0,1] weighted blend of four
similarity sub-scores (DOM, visual, a11y, history) — the deterministic sibling of
`kg/risk.py` `risk_score` (D-02: keyless, auditable, reproducible; cannot hallucinate a heal).

This table test pins:
  - an all-max signal set blends to exactly 1.0 (normalized by sum-of-weights),
  - an empty signal dict scores 0.0 (every absent sub-score treated as 0.0),
  - custom weights normalize by sum(weights) and the result is ALWAYS clamped to [0,1]
    even for pathological (negative / overrunning) weights,
  - the frozen DEFAULT_WEIGHTS can never be mutated under callers.

`healing/confidence.py` must import NOTHING outside stdlib (no neo4j / llm_gateway /
SessionLocal / playwright) — the discipline mirrors `kg/risk.py`, so the engine stays
deterministic AND byte-vendorable into the in-spec `_healing.py` layer (plan 02).
"""

from __future__ import annotations

import pytest

from app.services.healing.confidence import (
    DEFAULT_WEIGHTS,
    HealWeights,
    confidence,
)


def test_all_max_signals_blend_to_one() -> None:
    # All four sub-scores at 1.0 -> the normalized weighted blend is exactly 1.0.
    assert confidence({"dom": 1.0, "visual": 1.0, "a11y": 1.0, "history": 1.0}) == 1.0


def test_empty_signals_score_zero() -> None:
    # Every absent sub-score is treated as 0.0 -> the blend is 0.0.
    assert confidence({}) == 0.0


def test_partial_signals_default_absent_to_zero() -> None:
    # Only dom present (default weights dom=0.30): 0.30*1 / (0.30+0.20+0.30+0.20) == 0.30.
    assert confidence({"dom": 1.0}) == pytest.approx(0.30)


def test_blend_is_weighted_average_of_present_subscores() -> None:
    # dom=1, a11y=1 (the two 0.30 weights), visual/history absent (0):
    #   (0.30*1 + 0.30*1) / 1.0 == 0.60
    assert confidence({"dom": 1.0, "a11y": 1.0}) == pytest.approx(0.60)


def test_custom_weights_normalize_by_sum() -> None:
    # With a single non-zero weight, a single max sub-score normalizes to 1.0.
    w = HealWeights(dom=1.0, visual=0.0, a11y=0.0, history=0.0)
    assert confidence({"dom": 1.0}, w) == 1.0
    assert confidence({"dom": 0.5}, w) == pytest.approx(0.5)


def test_clamp_ceiling_with_overrunning_signals() -> None:
    # Sub-scores out of range (e.g. 5.0) can never push the blend past 1.0.
    assert confidence({"dom": 5.0, "visual": 5.0, "a11y": 5.0, "history": 5.0}) == 1.0


def test_clamp_floor_with_negative_signals() -> None:
    # Negative sub-scores can never drive the blend below 0.0.
    assert confidence({"dom": -5.0, "visual": -5.0, "a11y": -5.0, "history": -5.0}) == 0.0


def test_zero_total_weight_does_not_divide_by_zero() -> None:
    # Pathological all-zero weights: `(sum or 1.0)` guard avoids ZeroDivisionError -> 0.0.
    w = HealWeights(dom=0.0, visual=0.0, a11y=0.0, history=0.0)
    assert confidence({"dom": 1.0}, w) == 0.0


def test_result_always_in_unit_interval() -> None:
    # Across a matrix of signal values and a heavy custom weight, the result stays in [0,1].
    w = HealWeights(dom=10.0, visual=0.1, a11y=0.1, history=0.1)
    for v in (-3.0, 0.0, 0.25, 0.5, 1.0, 7.0):
        c = confidence({"dom": v, "visual": v, "a11y": v, "history": v}, w)
        assert 0.0 <= c <= 1.0


def test_default_weights_match_research_starting_points() -> None:
    # RESEARCH A1 starting points (tunable, documented as such).
    assert DEFAULT_WEIGHTS == HealWeights(dom=0.30, visual=0.20, a11y=0.30, history=0.20)


def test_weights_are_frozen() -> None:
    with pytest.raises(Exception):
        DEFAULT_WEIGHTS.dom = 1.0  # type: ignore[misc]


def test_confidence_module_imports_no_stack() -> None:
    # D-02: the confidence module is PURE — no neo4j / llm / DB / browser imports.
    import inspect

    import app.services.healing.confidence as conf_mod

    src = inspect.getsource(conf_mod)
    for forbidden in ("neo4j", "llm_gateway", "SessionLocal", "playwright", "init_chat_model"):
        assert forbidden not in src, f"confidence.py must not reference {forbidden!r} (D-02: pure)"
