"""Explorer agent package (Phase 4) — LangGraph StateGraph autonomous web crawl.

Slice 1 modules: state (TypedDict + live-handle registry + STOP_REASONS), budget
(caps/loop/saturation), perception (aria_snapshot), actions (constrained menu), nodes
(navigate/perceive/enumerate/decide/act/persist/converge), graph (build_explorer_graph).

`run_explore` is the POST /explore BackgroundTask entrypoint (the Phase-3 seam this
package evolves). It is re-exported here so `from app.services.explorer import run_explore`
keeps working whether explorer is a module (Phase 3) or this package (Phase 4).

Task 2 transitionally re-exports the Phase-3 deterministic tracer; Task 3 replaces it
with the LangGraph driver in driver.py.
"""

from app.services.explorer.driver import run_explore

__all__ = ["run_explore"]
