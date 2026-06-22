"""PURE deterministic heal confidence blend + 3-outcome resolver (HEAL-01 / HEAL-02, D-02/D-04).

The deterministic, keyless sibling of `kg/risk.py`: a `@dataclass(frozen=True)` of tunable
weights + a pure clamped blend of four [0,1] similarity sub-scores (DOM structure, bounding-box
visual, a11y role+name, historical-chain) into a [0,1] confidence, and a pure band resolver
that maps (confidence, live-match-count) to ONE of three locator-resolution outcomes.

D-04 — the HARD live-re-validation uniqueness gate is applied FIRST in `heal_outcome`, BEFORE any
confidence band: a candidate that resolves to 0 or >1 live elements can NEVER auto-heal, no matter
the score. This is the structural false-heal guarantee (QUAL-02), independent of the thresholds.
Assertions are NEVER a heal target — `heal_outcome` only ever returns one of the three LOCATOR
verdicts ("auto_heal" | "quarantine" | "fail_as_defect").

Acceptance (test_heal_confidence.py / test_heal_outcome.py): this module imports NOTHING from the
browser, the DB session, the graph driver, or the LLM path — it is stdlib-only (dataclasses). The
weights (RESEARCH A1) and bands are STARTING POINTS, config-tunable via settings, passed per call.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HealWeights:
    """Tunable, FROZEN blend weights for the four similarity sub-scores (swap per call via `w`).

    Frozen so a shared DEFAULT_WEIGHTS can never be mutated under callers (same reason
    `kg/risk.RiskWeights` and `explorer/budget.ExploreBudget` are frozen). The values are
    RESEARCH A1 starting points (LOW confidence on exact values, HIGH on the shape) — they are
    tuned empirically by the mutation harness (QUAL-02) and may be overridden per call.
    """

    dom: float = 0.30      # DOM-structure Jaccard + tag bonus + xpath-ancestry overlap
    visual: float = 0.20   # bounding-box IoU + size proximity (geometry only, no pixel decode)
    a11y: float = 0.30     # role equality blended with accessible-name difflib ratio
    history: float = 0.20  # candidate chain matches a prior history_json snapshot


DEFAULT_WEIGHTS = HealWeights()


def confidence(signals: dict, w: HealWeights = DEFAULT_WEIGHTS) -> float:
    """PURE: weighted blend of four [0,1] sub-scores -> clamped [0,1]. No I/O, no LLM, no browser.

    `signals` keys (any may be absent -> treated as 0.0): dom, visual, a11y, history.

    The blend is normalized by the SUM of the weights (so an all-max signal set blends to exactly
    1.0 regardless of the relative weight values), then clamped to [0,1]. The clamp guarantees the
    range even for pathological signals (out-of-range or negative) or weights; the `or 1.0` guard
    avoids a divide-by-zero when all weights are zero.
    """
    raw = (
        w.dom * float(signals.get("dom", 0.0))
        + w.visual * float(signals.get("visual", 0.0))
        + w.a11y * float(signals.get("a11y", 0.0))
        + w.history * float(signals.get("history", 0.0))
    )
    total = (w.dom + w.visual + w.a11y + w.history) or 1.0
    return max(0.0, min(1.0, raw / total))


def heal_outcome(conf: float, live_match_count: int, *, high: float, med: float) -> str:
    """PURE: the 3-outcome resolver with the HARD uniqueness gate FIRST (HEAL-02 / D-04).

    Returns exactly one of the three LOCATOR-resolution verdicts:
      "auto_heal"      — conf >= high AND the candidate re-validates to EXACTLY ONE live element
      "quarantine"     — conf >= med  (and unique) — held for human review
      "fail_as_defect" — below med, OR a non-unique match (feeds Phase 9 as a product failure)

    The `live_match_count != 1` gate is applied UNCONDITIONALLY before any band comparison: a
    candidate matching 0 or >1 live elements can NEVER auto-heal regardless of `conf`. This is the
    structural false-heal guard (QUAL-02), independent of the thresholds. `high`/`med` are passed
    by callers from `settings.heal_high_threshold` / `settings.heal_med_threshold` (config-tunable,
    like `stability_runs`) — never hardcoded here. Assertions are never a heal target.
    """
    if live_match_count != 1:
        return "fail_as_defect"  # ambiguous/missing -> never auto-heal (structural guard)
    if conf >= high:
        return "auto_heal"
    if conf >= med:
        return "quarantine"
    return "fail_as_defect"
