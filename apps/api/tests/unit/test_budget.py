"""Unit tests for explorer.budget (Phase 4, EXPL-05) — pure, no stack, no spend.

Covers: tighten-only clamp (override below/above global), cap_reason at each boundary,
loop detection on a repeated (fingerprint, index) pair + revisits-cap, and saturation.
"""

from types import SimpleNamespace

import pytest

from app.services.explorer.budget import (
    ExploreBudget,
    build_budget,
    cap_reason,
    is_loop,
    is_saturated,
)

# A settings stub carrying only the five explore globals build_budget reads.
_SETTINGS = SimpleNamespace(
    explore_max_steps=60,
    explore_max_depth=6,
    explore_max_revisits_per_fingerprint=2,
    explore_wall_clock_seconds=600,
    explore_saturation_window=8,
)


def _budget(**kw) -> ExploreBudget:
    base = dict(
        max_steps=60,
        max_depth=6,
        max_revisits_per_fingerprint=2,
        wall_clock_seconds=600,
        saturation_window=8,
    )
    base.update(kw)
    return ExploreBudget(**base)


# --- build_budget: tighten-only clamp ---------------------------------------------


def test_build_budget_no_overrides_uses_globals():
    b = build_budget(None, _SETTINGS)
    assert b.max_steps == 60
    assert b.max_depth == 6
    assert b.max_revisits_per_fingerprint == 2
    assert b.wall_clock_seconds == 600
    assert b.saturation_window == 8


def test_build_budget_override_below_global_is_honored():
    """A TIGHTER override (below the global) is applied."""
    b = build_budget({"max_steps": 10, "wall_clock_seconds": 120}, _SETTINGS)
    assert b.max_steps == 10
    assert b.wall_clock_seconds == 120
    # Untouched keys keep globals.
    assert b.max_depth == 6


def test_build_budget_override_above_global_is_clamped():
    """A LOOSER override (above the global) is clamped to the global ceiling."""
    b = build_budget({"max_steps": 9999, "max_depth": 100}, _SETTINGS)
    assert b.max_steps == 60  # clamped to global
    assert b.max_depth == 6  # clamped to global


# --- cap_reason at each boundary --------------------------------------------------


def test_cap_reason_none_below_caps():
    assert cap_reason({"step": 5, "depth": 1}, _budget()) is None


def test_cap_reason_max_steps_boundary():
    assert cap_reason({"step": 60, "depth": 0}, _budget()) == "max_steps"


def test_cap_reason_max_depth_boundary():
    assert cap_reason({"step": 0, "depth": 6}, _budget()) == "max_depth"


def test_cap_reason_wall_clock_boundary():
    import time

    # started_at far enough in the past that elapsed >= wall_clock_seconds.
    state = {"step": 0, "depth": 0, "started_at": time.monotonic() - 5}
    assert cap_reason(state, _budget(wall_clock_seconds=1)) == "wall_clock"


def test_cap_reason_steps_takes_precedence_over_depth():
    """Order is deterministic: steps checked before depth."""
    assert cap_reason({"step": 60, "depth": 6}, _budget()) == "max_steps"


# --- is_loop ----------------------------------------------------------------------


def test_is_loop_false_for_fresh_pair():
    state = {"seen_keys": {"fp1": 1}, "seen_pairs": [["fp1", 0]]}
    assert is_loop(state, "fp1", 1, _budget()) is False


def test_is_loop_true_on_repeated_pair():
    state = {"seen_keys": {"fp1": 1}, "seen_pairs": [["fp1", 2]]}
    assert is_loop(state, "fp1", 2, _budget()) is True


def test_is_loop_true_when_revisits_exceeded():
    # max_revisits_per_fingerprint=2; a 3rd visit (>2) is a loop.
    state = {"seen_keys": {"fp1": 3}, "seen_pairs": []}
    assert is_loop(state, "fp1", 0, _budget()) is True


def test_is_loop_false_at_revisit_cap_boundary():
    # Exactly at the cap (2) is NOT yet a loop; only strictly above.
    state = {"seen_keys": {"fp1": 2}, "seen_pairs": []}
    assert is_loop(state, "fp1", 5, _budget()) is False


# --- is_saturated -----------------------------------------------------------------


def test_is_saturated_true_at_window():
    assert is_saturated({"steps_since_new": 8}, _budget()) is True


def test_is_saturated_false_below_window():
    assert is_saturated({"steps_since_new": 3}, _budget()) is False
