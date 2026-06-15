"""ExplorerState schema + STOP_REASONS vocabulary + per-run live-handle registry.

H-1 SERIALIZATION INVARIANT (load-bearing):
  ExplorerState is checkpointed to Postgres by AsyncPostgresSaver after EVERY node, so it
  MUST be 100% JSON-serializable. It holds ONLY JSON-safe values — run_id/current_url
  (str), frontier entries are plain dicts {key, url, label}, seen_keys/visited_keys are str
  keys/counters, step/depth are ints, stop_reason is a str|None from STOP_REASONS.
  It MUST NEVER hold a live Playwright Page/Browser/BrowserContext handle — those are NOT
  serializable and would crash the checkpoint write with a TypeError.

  The live browser/context/page handle lives OUTSIDE the checkpointed state in a per-run
  handle registry (`_RUN_HANDLES` below), keyed by run_id. Nodes resolve the page via
  `get_handles(state["run_id"]).page` — they NEVER read or write the handle from/to
  ExplorerState. The registry is populated (set_handles) before `graph.ainvoke` and torn
  down (clear_handles) in a `finally` around the whole invoke (see driver.py).

L-2: STOP_REASONS is the SINGLE source of the stop_reason enum the 04-04 UI consumes.
"""

from __future__ import annotations

from operator import add
from typing import TYPE_CHECKING, Annotated, NamedTuple, TypedDict

if TYPE_CHECKING:  # handle types referenced ONLY for the registry, never inside ExplorerState
    from playwright.async_api import Browser, BrowserContext, Page

# The shared terminal vocabulary — the ONLY values stop_reason may take (L-2).
STOP_REASONS = (
    "max_steps",
    "max_depth",
    "wall_clock",
    "budget",
    "saturation",
    "converged",
    "failed",
    "stopped",
)


class ExplorerState(TypedDict, total=False):
    """JSON-serializable LangGraph state (H-1). NO browser handle is ever stored here.

    Frontier entries are dicts {key, url, label}; seen_keys maps fingerprint->visit count;
    visited_keys is a list of explored page keys; seen_pairs records (fingerprint, index)
    pairs for the loop detector. events uses the add reducer to accumulate a feed.
    """

    run_id: str
    target_id: int
    base_url: str
    # Safety inputs read from the Target row at run start (EXPL-07/08). sandbox LIFTS the
    # destructive deny (D-03); origin_allowlist gates navigation in code (D-04). Both are
    # JSON-safe (bool / list[str]) so they ride the checkpoint with the rest of state.
    sandbox: bool
    origin_allowlist: list
    current_url: str
    step: int
    depth: int
    started_at: float  # time.monotonic() epoch set at run start (wall-clock cap)
    seen_keys: dict  # fingerprint -> visit count
    seen_pairs: list  # [[fingerprint, chosen_index], ...] for the loop detector
    steps_since_new: int  # saturation counter (D-05)
    frontier: list  # [{key, url, label}, ...] unvisited in-origin candidates
    visited_keys: list  # page keys already explored
    action_menu: list  # constrained menu from the current snapshot (D-02)
    chosen_index: int | None
    pending_action: dict | None  # the chosen menu entry to act on next (else pop frontier)
    last_snapshot_yaml: str
    current_fingerprint: str  # EXPL-06 structural fingerprint of the landed page (dedup key)
    current_screenshot: str | None  # path of the latest evidence screenshot (JSON-safe)
    # EXPL-09: append-only per-element locator history keyed by element key (JSON-safe);
    # a re-observed element APPENDS a step-stamped chain snapshot (Phase 8 healing fallback).
    element_history: dict
    # EXPL-04: the workflow flag the decide node parsed this step ({flow, order}|absent) and
    # the accumulated ordered Workflow→STEP→Page chain ([{flow, order, page_key}], JSON-safe).
    workflow_flag: dict | None
    workflow_chain: list
    # EXPL-04: a gated validation-probe result ({form_id, errors:[{field, message}]}|absent)
    # the act node sets ONLY when the risk gate allowed the submit — persist records the rules.
    validation_submit_result: dict | None
    events: Annotated[list, add]
    stop_reason: str | None
    # Internal scratch (JSON-safe strings) passed between persist -> converge.
    _last_from_key: str
    _last_to_key: str


class BrowserHandles(NamedTuple):
    """The live, NON-serializable browser handles for one run — held OUTSIDE state (H-1)."""

    browser: "Browser"
    context: "BrowserContext"
    page: "Page"


# Module-level per-run registry. Keyed by run_id; single concurrent run this phase.
_RUN_HANDLES: dict[str, BrowserHandles] = {}


def set_handles(run_id: str, handles: BrowserHandles) -> None:
    """Register the live browser handles for a run BEFORE graph.ainvoke (driver.py)."""
    _RUN_HANDLES[run_id] = handles


def get_handles(run_id: str) -> BrowserHandles:
    """Resolve the live page/context/browser for a run. Nodes call this — NEVER read state.

    Raises if no handles are registered (a node ran outside a driver-managed run).
    """
    handles = _RUN_HANDLES.get(run_id)
    if handles is None:
        raise RuntimeError(f"no browser handles registered for run_id {run_id!r}")
    return handles


def clear_handles(run_id: str) -> None:
    """Tear down the per-run registry entry in the driver's finally (idempotent)."""
    _RUN_HANDLES.pop(run_id, None)
