"""Two-run DETERMINISTIC convergence proof (Phase 4, EXPL-05) — mocked gateway, zero spend.

This is the HEADLINE convergence guarantee: run the explorer loop TWICE over the SAME fixed
fixture snapshots with a mocked gateway returning deterministic action indices, and assert
  (1) run 2 adds ~0 NEW fingerprints (the fingerprint set is IDENTICAL across the two runs),
  (2) both runs end with stop_reason == "saturation".

It runs with NO provider key, NO graph_mode, NO browser — pure unit. It exercises the REAL
fingerprint + saturation + budget code paths (imported from explorer.fingerprint /
explorer.budget / the converge node) via the `run_over_fixtures` harness, NOT a
reimplementation, so a regression in those modules breaks this proof.
"""

from __future__ import annotations

from app.services.explorer.budget import ExploreBudget, is_saturated
from app.services.explorer.convergence import run_over_fixtures
from app.services.explorer.fingerprint import fingerprint
from tests.fixtures.aria import (
    CART_PAGE,
    PRODUCT_LIST_4,
    PRODUCT_LIST_6,
    PRODUCT_LIST_6_ALT,
)

# A saturating world: a small fixed set of screens the loop revisits. Two of them are the
# SAME logical screen (product list, different instance data) so they fold to ONE fingerprint
# — the world has only two DISTINCT fingerprints, so the loop saturates quickly.
_SATURATING_SNAPSHOTS = [
    PRODUCT_LIST_6,
    CART_PAGE,
    PRODUCT_LIST_4,  # folds onto PRODUCT_LIST_6's fingerprint (template equality)
    PRODUCT_LIST_6_ALT,  # also folds onto the product-list fingerprint
    CART_PAGE,
]

_BUDGET = ExploreBudget(
    max_steps=60,
    max_depth=20,
    max_revisits_per_fingerprint=99,  # high so the LOOP detector doesn't pre-empt saturation
    wall_clock_seconds=600,
    saturation_window=3,  # stop after 3 steps with no new fingerprint
)


def test_two_run_convergence_identical_fp_set_and_saturation():
    """Two runs over the same snapshots converge to the same fingerprint set + saturation."""
    # Deterministic scripted "gateway" indices — the fixture index chosen each step. The same
    # script for both runs (determinism is the whole point).
    script = [0, 1, 2, 3, 4, 0, 1, 2, 3, 4, 0, 1, 2]

    run1 = run_over_fixtures(_SATURATING_SNAPSHOTS, script, _BUDGET)
    run2 = run_over_fixtures(_SATURATING_SNAPSHOTS, script, _BUDGET)

    # (1) Identical fingerprint set across the two runs (run 2 adds ~0 new states).
    assert set(run1["seen_keys"].keys()) == set(run2["seen_keys"].keys())
    # The saturating world has exactly two DISTINCT structural fingerprints.
    assert len(run1["seen_keys"]) == 2

    # (2) Both runs stop on saturation (not a hard cap).
    assert run1["stop_reason"] == "saturation"
    assert run2["stop_reason"] == "saturation"


def test_fingerprint_set_matches_real_fingerprint_module():
    """The harness uses the REAL fingerprint module (not a reimplementation)."""
    run = run_over_fixtures(_SATURATING_SNAPSHOTS, [0, 1, 2, 3, 4], _BUDGET)
    expected = {fingerprint(PRODUCT_LIST_6), fingerprint(CART_PAGE)}
    assert set(run["seen_keys"].keys()) == expected


def test_budget_backstop_halts_non_saturating_world():
    """A non-saturating world (every step a NEW fingerprint) still halts on a hard cap."""
    # Build many DISTINCT screens by deepening the cart table each step so the fingerprint is
    # always new — saturation never triggers, the step cap must.
    distinct = [_nest_cart(i) for i in range(40)]
    script = list(range(40))
    budget = ExploreBudget(
        max_steps=10,
        max_depth=99,
        max_revisits_per_fingerprint=99,
        wall_clock_seconds=600,
        saturation_window=99,  # so saturation can't fire — the cap must
    )
    run = run_over_fixtures(distinct, script, budget)
    assert run["stop_reason"] == "max_steps"
    # Never infinite: a stop_reason is always set.
    assert run["stop_reason"] is not None


def test_is_saturated_is_the_real_predicate():
    """Sanity: the harness's saturation verdict agrees with budget.is_saturated (real code)."""
    run = run_over_fixtures(_SATURATING_SNAPSHOTS, [0, 1, 2, 3, 4, 0, 1, 2], _BUDGET)
    # At termination steps_since_new reached the window per the real predicate.
    assert is_saturated(run, _BUDGET)


def _nest_cart(depth: int) -> dict:
    """A cart page with a row nested `depth` deep — guarantees a unique structural skeleton."""
    node = {"role": "cell", "tag": "td", "attrs": {}, "children": []}
    for _ in range(depth):
        node = {"role": "row", "tag": "tr", "attrs": {}, "children": [node]}
    return {
        "role": "document",
        "tag": "html",
        "attrs": {},
        "children": [
            {
                "role": "table",
                "tag": "table",
                "attrs": {"data-test": "cart"},
                "children": [node],
            }
        ],
    }
