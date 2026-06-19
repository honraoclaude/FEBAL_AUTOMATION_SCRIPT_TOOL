"""PURE deterministic per-flow risk score (KG-04 / D-04) — NEVER LLM JUDGMENT.

A flow's risk is a clamped 0-100 weighted sum of graph signals (a destructive action in the
path, the count of state-changing edges, auth-gated steps, the form count, the path length).
D-04 REJECTS LLM-judged risk: a number users act on must be reproducible, auditable, and free.
This module mirrors the explorer safety-layer discipline (pure code, table-testable) and the
budget-module shape (a `@dataclass(frozen=True)` of tunable weights + pure functions).

Acceptance (test_kg_risk.py): this module imports NOTHING from the graph driver / the metered
LLM path / the DB session factory — it is stdlib-only (dataclasses). The weights are a STARTING
POINT (RESEARCH A1, LOW confidence on exact values, HIGH on the shape) and swappable per call.
"""

from __future__ import annotations

from dataclasses import dataclass

# Tier thresholds for the UI badge (RESEARCH Pattern 3 / A1 — tunable).
_HIGH_THRESHOLD = 67
_MEDIUM_THRESHOLD = 34


@dataclass(frozen=True)
class RiskWeights:
    """Tunable, FROZEN weights for the risk formula (swap per call via the `w` arg).

    Frozen so a shared DEFAULT_WEIGHTS can never be mutated under callers (the same reason
    explorer/budget.ExploreBudget is frozen). Exact values are RESEARCH A1 starting points.
    """

    destructive_action: int = 40   # binary: ANY destructive verb in the path contributes once
    per_state_change: int = 8      # each Submits/Creates/Updates/Deletes edge in the path
    auth_gated_step: int = 6       # each step behind login
    per_form: int = 5              # each form in the path
    depth: int = 3                 # per hop of path length


DEFAULT_WEIGHTS = RiskWeights()


def risk_score(signals: dict, w: RiskWeights = DEFAULT_WEIGHTS) -> int:
    """PURE: clamped 0-100 weighted sum of a flow's risk signals (D-04).

    `signals` keys (any may be absent -> treated as 0/False):
      has_destructive (bool), state_change_edges (int), auth_gated_steps (int),
      form_count (int), path_length (int).

    No I/O, no LLM, no graph driver. The clamp guarantees the range regardless of the weights
    (even pathological negative custom weights floor at 0; an overrunning sum caps at 100).
    """
    raw = (
        (w.destructive_action if signals.get("has_destructive") else 0)
        + w.per_state_change * int(signals.get("state_change_edges", 0))
        + w.auth_gated_step * int(signals.get("auth_gated_steps", 0))
        + w.per_form * int(signals.get("form_count", 0))
        + w.depth * int(signals.get("path_length", 0))
    )
    return max(0, min(100, raw))


def risk_tier(score: int) -> str:
    """PURE: map a 0-100 score to the UI badge tier — high (>=67) / medium (34-66) / low (<34)."""
    if score >= _HIGH_THRESHOLD:
        return "high"
    if score >= _MEDIUM_THRESHOLD:
        return "medium"
    return "low"
