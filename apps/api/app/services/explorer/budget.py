"""Explorer budget caps, loop detector, saturation (Phase 4, EXPL-05, D-05/D-06) — PURE.

Code-enforced EXPLORATION termination. NO token/USD tracking here — the Phase-2 gateway
owns spend (D-06); every gateway call passes run_id and a BudgetExceeded ends the run
gracefully (stop_reason="budget"). This module only enforces step/depth/wall-clock caps,
revisits-per-fingerprint, a (fingerprint, action) loop detector, and the saturation
window.

build_budget mirrors llm_gateway._effective_caps' TIGHTEN-ONLY clamp: a Target's
budget_overrides may only LOWER a cap (min(override, global)); a looser override is
clamped to the global ceiling.

All functions are pure (no I/O, no browser, no LLM) so the whole module is unit-testable
with a table of states — no stack, no spend.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ExploreBudget:
    """Per-run exploration caps (resolved from globals + tighten-only target overrides)."""

    max_steps: int
    max_depth: int
    max_revisits_per_fingerprint: int
    wall_clock_seconds: int
    saturation_window: int


def build_budget(target_overrides: dict | None, settings) -> ExploreBudget:
    """Resolve effective caps = global default TIGHTENED by any per-run override (D-06).

    Mirrors llm_gateway._effective_caps: each override may only LOWER its cap
    (min(override, global)); a missing override key keeps the global; a looser override
    is silently clamped to the global ceiling. The override dict keys are the bare cap
    names (max_steps, max_depth, max_revisits_per_fingerprint, wall_clock_seconds,
    saturation_window).
    """
    o = target_overrides or {}

    def clamp(key: str, global_cap: int) -> int:
        override = o.get(key)
        if override is None:
            return global_cap
        return min(int(override), global_cap)

    return ExploreBudget(
        max_steps=clamp("max_steps", settings.explore_max_steps),
        max_depth=clamp("max_depth", settings.explore_max_depth),
        max_revisits_per_fingerprint=clamp(
            "max_revisits_per_fingerprint", settings.explore_max_revisits_per_fingerprint
        ),
        wall_clock_seconds=clamp("wall_clock_seconds", settings.explore_wall_clock_seconds),
        saturation_window=clamp("saturation_window", settings.explore_saturation_window),
    )


def cap_reason(state: dict, budget: ExploreBudget) -> str | None:
    """Return the first breached HARD cap ("max_steps"/"max_depth"/"wall_clock"), else None.

    Pure: reads counters off the state dict (step, depth, started_at) and compares to the
    budget. Wall-clock uses state["started_at"] (a monotonic epoch set at run start); when
    absent, wall-clock is not evaluated (unit tests that omit it test only step/depth).
    """
    if state.get("step", 0) >= budget.max_steps:
        return "max_steps"
    if state.get("depth", 0) >= budget.max_depth:
        return "max_depth"
    started_at = state.get("started_at")
    if started_at is not None and (time.monotonic() - started_at) >= budget.wall_clock_seconds:
        return "wall_clock"
    return None


def is_loop(state: dict, fingerprint: str, chosen_index: int | None, budget: ExploreBudget) -> bool:
    """True when the crawl is looping: a repeated (fingerprint, chosen_index) pair OR the
    revisits-per-fingerprint cap is exceeded for this fingerprint.

    Reads two ledgers off the state:
      - seen_keys: dict[fingerprint -> visit count] (revisit detector)
      - a (fingerprint, chosen_index) recurrence is detected when this fingerprint's visit
        count already exceeds the revisits cap, OR the same pair has been seen before.
    Pure: derives the verdict from state + the candidate (fingerprint, index); the caller
    updates the ledgers in converge.
    """
    seen = state.get("seen_keys", {}) or {}
    visits = int(seen.get(fingerprint, 0))
    if visits > budget.max_revisits_per_fingerprint:
        return True
    # Repeated (fingerprint, chosen_index) pair: the same decision on the same state.
    pairs = state.get("seen_pairs", []) or []
    if chosen_index is not None and [fingerprint, chosen_index] in pairs:
        return True
    return False


def is_saturated(state: dict, budget: ExploreBudget) -> bool:
    """True when no NEW fingerprint has appeared for `saturation_window` steps (D-05).

    The convergence backstop: maintain state["steps_since_new"] (reset to 0 on a new
    fingerprint); two consecutive runs converge to ~the same graph when both stop on
    saturation rather than a hard cap.
    """
    return int(state.get("steps_since_new", 0)) >= budget.saturation_window
