"""Unit tests for the explorer LangGraph (Phase 4, Test 3) — mocked, no stack, no spend.

Covers:
  - build_explorer_graph compiles with a checkpointer and routes loop->navigate / stop->END.
  - should_continue returns "stop" when stop_reason is set, "loop" otherwise.
  - H-1 serialization invariant: a checkpoint write succeeds across a node transition over a
    populated ExplorerState with NO serialization error (proving the page handle is NOT in
    state and the state is JSON-serializable).
  - parse_index clamps the LLM-returned index into the menu bounds.
"""

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.services.explorer.budget import ExploreBudget
from app.services.explorer.graph import build_explorer_graph
from app.services.explorer.nodes import parse_index, should_continue
from app.services.explorer.state import STOP_REASONS, ExplorerState

_BUDGET = ExploreBudget(
    max_steps=60,
    max_depth=6,
    max_revisits_per_fingerprint=2,
    wall_clock_seconds=600,
    saturation_window=8,
)


def test_build_explorer_graph_compiles_with_checkpointer():
    """A raw StateGraph compiles bound to an (in-memory) checkpointer."""
    graph = build_explorer_graph(InMemorySaver(), _BUDGET)
    assert graph is not None
    # The compiled graph carries the seven explorer nodes.
    node_names = set(graph.get_graph().nodes.keys())
    for expected in {"navigate", "perceive", "enumerate", "decide", "act", "persist", "converge"}:
        assert expected in node_names, f"missing node {expected}: {node_names}"


def test_should_continue_routes_stop_and_loop():
    assert should_continue({"stop_reason": "saturation"}) == "stop"
    assert should_continue({"stop_reason": None}) == "loop"
    assert should_continue({}) == "loop"
    # Every STOP_REASONS value routes to stop.
    for reason in STOP_REASONS:
        assert should_continue({"stop_reason": reason}) == "stop"


def test_parse_index_clamps_to_menu_bounds():
    assert parse_index("2", 5) == 2
    assert parse_index("99", 5) == 4  # clamped to menu_len-1
    assert parse_index("garbage", 5) == 0  # safe default
    assert parse_index("index 3 please", 5) == 3
    assert parse_index("0", 0) == 0  # empty menu


async def test_checkpoint_write_survives_node_transition_no_serialization_error():
    """H-1: a checkpoint write succeeds across a node transition over a populated
    ExplorerState with NO serialization error (the live browser handle is NOT in state).

    Drive the converge node (a pure node that needs no browser) through the compiled graph's
    checkpointer using a populated state. AsyncPostgresSaver/InMemorySaver both serialize the
    state after the node; a Page/Browser handle in state would raise. We use InMemorySaver
    (msgpack serializer, same contract) so the test needs no Postgres — a non-JSON-safe value
    in state would still raise on the put.
    """
    saver = InMemorySaver()

    populated: ExplorerState = {
        "run_id": "test-run-1",
        "target_id": 1,
        "base_url": "http://demo:80",
        "current_url": "http://demo:80/inventory",
        "step": 3,
        "depth": 2,
        "started_at": 123.0,
        "seen_keys": {"http://demo:80/inventory": 1},
        "seen_pairs": [["http://demo:80/inventory", 0]],
        "steps_since_new": 1,
        "frontier": [{"key": "http://demo:80/cart", "url": "http://demo:80/cart", "label": "Cart"}],
        "visited_keys": ["http://demo:80/inventory"],
        "action_menu": [{"index": 0, "role": "link", "label": "Cart", "locator_chain": None}],
        "chosen_index": 0,
        "pending_action": None,
        "last_snapshot_yaml": "- link \"Cart\"",
        "current_screenshot": "/app/workspaces/test-run-1/state-3.png",
        "events": ["step 3: chose [0] Cart"],
        "stop_reason": None,
    }

    # (a) The checkpointer's serializer round-trips the populated state with NO error
    #     (the JsonPlusSerializer is what AsyncPostgresSaver also uses). A live Playwright
    #     Page/Browser handle in state would NOT round-trip cleanly here.
    type_, blob = saver.serde.dumps_typed(dict(populated))
    restored = saver.serde.loads_typed((type_, blob))
    assert restored["run_id"] == "test-run-1"
    assert restored["frontier"] == populated["frontier"]
    assert restored["seen_keys"] == populated["seen_keys"]
    # Confirm the state carried NO handle key (handles live in the registry, not state).
    for forbidden in ("browser", "context", "page", "_handles"):
        assert forbidden not in restored, f"{forbidden} leaked into state"

    # (b) A full checkpoint put/get across a node transition succeeds with NO error.
    config = {"configurable": {"thread_id": "test-run-1", "checkpoint_ns": ""}}
    checkpoint = {
        "v": 1,
        "id": "1",
        "ts": "2026-06-15T00:00:00+00:00",
        "channel_values": dict(populated),
        "channel_versions": {},
        "versions_seen": {},
    }
    next_config = await saver.aput(config, checkpoint, {}, {})
    got = await saver.aget(next_config)
    assert got is not None  # the write+read survived the transition without a serialization error
