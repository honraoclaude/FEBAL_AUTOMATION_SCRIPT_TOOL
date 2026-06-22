"""HEAL-02 pure 3-outcome resolver proof (default gate — NO keys, NO neo4j, NO LLM, NO browser).

`heal_outcome(conf, live_match_count, *, high, med)` is the PURE confidence-band resolver with
the HARD live-re-validation uniqueness gate (D-04). It mirrors `kg/risk.py` `risk_tier` but adds
the structural false-heal guard FIRST: a non-unique live match (count != 1) can NEVER auto-heal
regardless of confidence — the QUAL-02 false-heal-near-zero guarantee is structural, not score-based.

This table test pins:
  - the uniqueness gate fires BEFORE the band checks (count=0 / count=2 at conf=0.99 -> fail_as_defect),
  - HIGH band + unique -> auto_heal; MED band + unique -> quarantine; below MED -> fail_as_defect,
  - band boundaries are inclusive (conf == high -> auto_heal; conf == med -> quarantine),
  - test_assertion_never_healed: heal_outcome returns ONLY one of three LOCATOR-resolution
    outcomes across the FULL band/count matrix — proving heal can only fail or heal a LOCATOR,
    never weaken an assertion (D-04 invariant; T-08-03).
"""

from __future__ import annotations

import pytest

from app.services.healing.confidence import heal_outcome

_HIGH = 0.85
_MED = 0.60
_OUTCOMES = {"auto_heal", "quarantine", "fail_as_defect"}


def _outcome(conf: float, count: int) -> str:
    return heal_outcome(conf, count, high=_HIGH, med=_MED)


# --- The uniqueness gate is applied FIRST, unconditionally (the structural false-heal guard) ---

def test_zero_live_matches_never_heals_even_at_max_confidence() -> None:
    # count=0: ambiguous/missing -> fail_as_defect BEFORE any band check.
    assert _outcome(0.99, 0) == "fail_as_defect"


def test_multiple_live_matches_never_heals_even_at_max_confidence() -> None:
    # count=2 (>1): non-unique -> fail_as_defect BEFORE any band check.
    assert _outcome(0.99, 2) == "fail_as_defect"


def test_high_confidence_unique_match_auto_heals() -> None:
    assert _outcome(0.90, 1) == "auto_heal"


def test_medium_confidence_unique_match_quarantines() -> None:
    assert _outcome(0.70, 1) == "quarantine"


def test_low_confidence_unique_match_fails_as_defect() -> None:
    assert _outcome(0.40, 1) == "fail_as_defect"


@pytest.mark.parametrize(
    "conf,expected",
    [
        (1.00, "auto_heal"),
        (0.85, "auto_heal"),     # boundary: conf == high is inclusive
        (0.849, "quarantine"),
        (0.60, "quarantine"),    # boundary: conf == med is inclusive
        (0.599, "fail_as_defect"),
        (0.00, "fail_as_defect"),
    ],
)
def test_band_boundaries_with_unique_match(conf: float, expected: str) -> None:
    assert _outcome(conf, 1) == expected


@pytest.mark.parametrize("count", [-1, 0, 2, 3, 99])
def test_non_unique_counts_all_fail_regardless_of_band(count: int) -> None:
    # ANY count != 1 -> fail_as_defect across the whole confidence range.
    for conf in (0.0, 0.60, 0.85, 1.0):
        assert _outcome(conf, count) == "fail_as_defect"


def test_thresholds_are_config_tunable_not_hardcoded() -> None:
    # The resolver reads `high`/`med` from kwargs (callers pass settings) — not hardcoded.
    # A higher `high` threshold demotes a once-auto_heal score to quarantine.
    assert heal_outcome(0.86, 1, high=0.85, med=0.60) == "auto_heal"
    assert heal_outcome(0.86, 1, high=0.90, med=0.60) == "quarantine"


def test_assertion_never_healed() -> None:
    """D-04 invariant: heal_outcome exposes NO assertion-touching path.

    heal_outcome ONLY ever returns one of the three LOCATOR-resolution verdicts. Sweep the
    FULL band x count matrix and assert every result is in the three-string set — proving the
    module can only fail or heal a LOCATOR, never weaken/return an assertion outcome.
    """
    for count in range(-2, 4):
        for conf in (0.0, 0.30, 0.59, 0.60, 0.84, 0.85, 0.99, 1.0):
            verdict = heal_outcome(conf, count, high=_HIGH, med=_MED)
            assert verdict in _OUTCOMES, (
                f"heal_outcome returned {verdict!r} outside the locator-resolution set "
                f"{_OUTCOMES} — heal must never touch assertions"
            )
