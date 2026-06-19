"""KG-04 bounded deterministic path-mining proof (default gate — NO keys, NO neo4j).

`mine_flows(graph)` enumerates SIMPLE paths over an in-memory adjacency graph (so the
deterministic proof needs no live driver, RESEARCH Pattern 2). It is bounded three ways
(Pitfall 3): MAX_PATH_LENGTH caps extension, dedup-by-node-set collapses orderings, and
MAX_FLOWS caps the emitted count with a `bounded` flag. Mining seeds from ENTRY pages
(no inbound NavigatesTo). `extract_signals(path)` produces the dict `risk_score` consumes.
"""

from __future__ import annotations

from app.services.kg.flows import (
    MAX_FLOWS,
    MAX_PATH_LENGTH,
    extract_signals,
    mine_flows,
)


def _linear_graph():
    """login -> inventory -> cart -> checkout (a single 4-node journey)."""
    return {
        "nodes": {
            "fp-login": {"label": "Login", "url": "/", "auth_gated": False, "form": False},
            "fp-inv": {"label": "Inventory", "url": "/inventory.html", "auth_gated": True, "form": False},
            "fp-cart": {"label": "Cart", "url": "/cart.html", "auth_gated": True, "form": False},
            "fp-co": {"label": "Checkout", "url": "/checkout.html", "auth_gated": True, "form": True},
        },
        "edges": [
            {"from": "fp-login", "to": "fp-inv", "type": "NavigatesTo", "via": "Login"},
            {"from": "fp-inv", "to": "fp-cart", "type": "NavigatesTo", "via": "Cart"},
            {"from": "fp-cart", "to": "fp-co", "type": "Submits", "via": "Checkout"},
        ],
    }


def test_mines_the_entry_seeded_journey() -> None:
    result = mine_flows(_linear_graph())
    assert result["bounded"] is False
    flows = result["flows"]
    # The longest entry-rooted simple path is login->inventory->cart->checkout; prefixes of it
    # are also valid journeys. Every mined flow must START at the entry page.
    assert all(f["node_fps"][0] == "fp-login" for f in flows)
    full = [f for f in flows if f["node_fps"] == ["fp-login", "fp-inv", "fp-cart", "fp-co"]]
    assert len(full) == 1


def test_dedup_by_node_set_collapses_orderings() -> None:
    # Two edges producing the SAME node-set via different orderings must collapse to one flow.
    graph = {
        "nodes": {
            "a": {"label": "A", "url": "/a", "auth_gated": False, "form": False},
            "b": {"label": "B", "url": "/b", "auth_gated": False, "form": False},
        },
        "edges": [
            {"from": "a", "to": "b", "type": "NavigatesTo", "via": "x"},
            # b also navigates to a, but a is the only entry -> only {a,b} once.
            {"from": "b", "to": "a", "type": "NavigatesTo", "via": "y"},
        ],
    }
    result = mine_flows(graph)
    node_sets = [frozenset(f["node_fps"]) for f in result["flows"]]
    assert len(node_sets) == len(set(node_sets))  # no duplicate node-sets


def test_max_path_length_stops_extension() -> None:
    # A long chain of entry-rooted nodes; no mined path may exceed MAX_PATH_LENGTH nodes.
    n = MAX_PATH_LENGTH + 5
    nodes = {f"n{i}": {"label": f"N{i}", "url": f"/{i}", "auth_gated": False, "form": False} for i in range(n)}
    edges = [{"from": f"n{i}", "to": f"n{i+1}", "type": "NavigatesTo", "via": "next"} for i in range(n - 1)]
    result = mine_flows({"nodes": nodes, "edges": edges})
    assert all(len(f["node_fps"]) <= MAX_PATH_LENGTH for f in result["flows"])


def test_max_flows_cap_sets_bounded_flag() -> None:
    # A star: one entry node fanning out to many leaves yields many 2-node journeys.
    # Force the cap below the natural count to prove the bounded flag + truncation.
    leaves = MAX_FLOWS + 10
    nodes = {"root": {"label": "Root", "url": "/", "auth_gated": False, "form": False}}
    edges = []
    for i in range(leaves):
        nodes[f"leaf{i}"] = {"label": f"L{i}", "url": f"/l{i}", "auth_gated": False, "form": False}
        edges.append({"from": "root", "to": f"leaf{i}", "type": "NavigatesTo", "via": "go"})
    result = mine_flows({"nodes": nodes, "edges": edges})
    assert result["bounded"] is True
    assert len(result["flows"]) <= MAX_FLOWS


def test_no_cycles_simple_paths_only() -> None:
    # A cycle a->b->c->a must never produce a path with a repeated node.
    graph = {
        "nodes": {k: {"label": k, "url": f"/{k}", "auth_gated": False, "form": False} for k in ("a", "b", "c")},
        "edges": [
            {"from": "a", "to": "b", "type": "NavigatesTo", "via": "1"},
            {"from": "b", "to": "c", "type": "NavigatesTo", "via": "2"},
            {"from": "c", "to": "a", "type": "NavigatesTo", "via": "3"},
        ],
    }
    result = mine_flows(graph)
    for f in result["flows"]:
        assert len(f["node_fps"]) == len(set(f["node_fps"]))  # simple path


def test_extract_signals_shape_for_risk_score() -> None:
    graph = _linear_graph()
    result = mine_flows(graph)
    full = next(f for f in result["flows"] if f["node_fps"] == ["fp-login", "fp-inv", "fp-cart", "fp-co"])
    sig = extract_signals(full, graph)
    # The full journey has one Submits edge (state-change), 3 auth-gated pages, 1 form, 4 nodes.
    assert set(sig) == {"has_destructive", "state_change_edges", "auth_gated_steps", "form_count", "path_length"}
    assert sig["state_change_edges"] == 1
    assert sig["auth_gated_steps"] == 3
    assert sig["form_count"] == 1
    assert sig["path_length"] == 4
    assert isinstance(sig["has_destructive"], bool)
