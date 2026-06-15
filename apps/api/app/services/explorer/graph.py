"""build_explorer_graph — raw LangGraph StateGraph (CLAUDE.md-locked; NOT create_agent).

Explicit nodes navigate -> perceive -> enumerate -> decide -> act -> persist -> converge,
with a conditional edge that loops back to navigate or stops (RESEARCH Pattern 1):
    add_conditional_edges("converge", should_continue, {"loop": "navigate", "stop": END})
Compiled WITH the AsyncPostgresSaver checkpointer so runs are resumable/cancellable by
thread_id=run_id.

The ExploreBudget is bound into the converge node via a closure (NOT stored in the
checkpointed ExplorerState — the frozen dataclass is not part of the JSON-serializable
state contract, H-1). converge reads budget from the closure rather than state["_budget"].
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.services.explorer.budget import ExploreBudget
from app.services.explorer.nodes import (
    act,
    converge,
    decide,
    enumerate_node,
    navigate,
    perceive_node,
    persist_to_neo4j,
    should_continue,
)
from app.services.explorer.state import ExplorerState


def build_explorer_graph(checkpointer, budget: ExploreBudget):  # noqa: ANN001
    """Build + compile the explorer StateGraph bound to a checkpointer and a per-run budget.

    The budget is closed over by a converge wrapper so it never enters the checkpointed
    state (H-1 serialization invariant).
    """

    async def _converge(state: dict) -> dict:
        return await converge({**state, "_budget": budget})

    g = StateGraph(ExplorerState)
    g.add_node("navigate", navigate)
    g.add_node("perceive", perceive_node)
    g.add_node("enumerate", enumerate_node)
    g.add_node("decide", decide)
    g.add_node("act", act)
    g.add_node("persist", persist_to_neo4j)
    g.add_node("converge", _converge)

    g.add_edge(START, "navigate")
    g.add_edge("navigate", "perceive")
    g.add_edge("perceive", "enumerate")
    g.add_edge("enumerate", "decide")
    g.add_edge("decide", "act")
    g.add_edge("act", "persist")
    g.add_edge("persist", "converge")
    g.add_conditional_edges("converge", should_continue, {"loop": "navigate", "stop": END})

    return g.compile(checkpointer=checkpointer)
