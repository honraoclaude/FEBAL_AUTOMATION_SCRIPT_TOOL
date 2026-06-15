"""Deterministic two-run convergence harness (Phase 4, EXPL-05) — PURE, zero spend.

`run_over_fixtures` drives the REAL explorer convergence machinery — the structural
`fingerprint`, the `budget` predicates (cap/loop/saturation), and the REAL `converge` node
logic — over a fixed list of fixture snapshots with a scripted "gateway" index sequence,
WITHOUT a browser, LLM, provider key, or Neo4j. It exists so the headline convergence proof
(two runs collapse to the same fingerprint set + stop on saturation) exercises the SAME code
paths the live loop uses (it imports converge/fingerprint/budget — it does NOT reimplement
them), giving a genuine regression guard rather than a parallel toy.

Why a harness instead of the live graph: the compiled StateGraph needs a live Playwright
page handle in every node (H-1). The convergence GUARANTEE, however, lives entirely in the
pure machinery: fingerprint identity + the converge node's seen_keys/steps_since_new ledger
+ the budget saturation/cap predicates. The harness feeds those exact functions fixed
snapshots, so a regression in any of them breaks the proof.

Loop model (mirrors the live navigate->perceive->...->converge cycle):
  * The "world" is `snapshots` (a fixed list of node trees) — the pages the crawl can land on.
  * Each step the scripted `index` selects which snapshot is "landed on" (stand-in for the
    gateway's action choice + navigate); its REAL structural fingerprint is the dedup key.
  * A frontier is seeded with every snapshot index and DRAINED one per step (mirrors H-2),
    so the loop keeps exploring until there is nothing new to visit AND no new fingerprint
    has appeared for `saturation_window` steps — exactly the live saturation contract (D-05).
  * The REAL `converge` node updates the ledgers and decides the stop_reason.
"""

from __future__ import annotations

import asyncio

from app.services.explorer.budget import ExploreBudget
from app.services.explorer.fingerprint import fingerprint
from app.services.explorer.nodes import converge


def run_over_fixtures(
    snapshots: list[dict], script: list[int], budget: ExploreBudget
) -> dict:
    """Drive the real converge machinery over fixed snapshots; return the terminal state dict.

    snapshots: the fixed world of page node trees (the crawl lands on one per step).
    script:    deterministic indices into `snapshots` (the mocked gateway's choices).
    budget:    the real ExploreBudget driving cap/loop/saturation.

    Returns the final ExplorerState-shaped dict (seen_keys, steps_since_new, stop_reason, ...).
    Deterministic: same inputs → identical output, with zero spend.
    """
    return asyncio.run(_run(snapshots, script, budget))


async def _run(snapshots: list[dict], script: list[int], budget: ExploreBudget) -> dict:
    if not snapshots:
        return {"seen_keys": {}, "steps_since_new": 0, "stop_reason": "saturation", "frontier": []}

    # Seed the frontier with one entry per distinct snapshot index (H-2: things left to
    # visit). It drains one per step; while non-empty the loop keeps exploring.
    frontier = [{"key": f"idx-{i}", "url": f"about:fixture/{i}", "label": str(i)} for i in
                range(len(snapshots))]

    state: dict = {
        "run_id": "convergence-harness",
        "step": 0,
        "depth": 0,
        "seen_keys": {},
        "seen_pairs": [],
        "steps_since_new": 0,
        "frontier": frontier,
        "stop_reason": None,
    }

    pos = 0
    # Hard safety bound so a misconfigured world can never hang the test process.
    max_iterations = budget.max_steps + len(snapshots) + budget.saturation_window + 5
    for _ in range(max_iterations):
        idx = script[min(pos, len(script) - 1)] if script else 0
        pos += 1
        snapshot = snapshots[idx % len(snapshots)]

        # REAL fingerprint — the dedup key (EXPL-06), exactly as the perceive node computes.
        fp = fingerprint(snapshot)

        # Drain one frontier entry per step (mirrors navigate popping a target).
        fr = list(state.get("frontier", []))
        if fr:
            fr.pop(0)

        chosen_index = idx
        # Hand the REAL converge node the same shape persist produces: _last_from_key is the
        # fingerprint, chosen_index drives the loop detector, the drained frontier gates
        # saturation. converge reads the budget from state["_budget"] (as graph.py injects).
        converge_input = {
            **state,
            "_budget": budget,
            "_last_from_key": fp,
            "current_fingerprint": fp,
            "current_url": f"about:fixture/{idx}",
            "chosen_index": chosen_index,
            "frontier": fr,
        }
        delta = await converge(converge_input)
        state = {**state, **delta, "frontier": fr}

        if state.get("stop_reason"):
            break

    if not state.get("stop_reason"):
        # The safety bound tripped — surface it as a cap so the test never reports a hang.
        state["stop_reason"] = "max_steps"
    return state
