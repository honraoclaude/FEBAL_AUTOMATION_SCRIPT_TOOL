"""Live-progress publish side (EXPL-01, D-07) — the explorer's Redis pub/sub seam.

The explorer emits an `ExploreProgressEvent` to the Redis pub/sub channel `explore:{run_id}`
after each step; the SSE endpoint (`GET /api/explore/{run_id}/events`) re-emits it to the
browser, which renders the Live Exploration View (04-UI-SPEC). Counters are ABSOLUTE values
(the live view takes the latest event's values directly — never deltas).

D-06: `cost_usd` is SOURCED from the gateway's per-run counter and PASSED INTO
build_progress_event — the explorer NEVER computes spend here. `screenshot_path` is reduced
to the run-RELATIVE basename (e.g. "state-3.png") so the frontend builds the auth-gated URL
`/api/explore/{run_id}/screenshot/{name}` (M-1) rather than ever seeing a filesystem path.

PUB/SUB is NEW Redis usage (Phase 1-3 used GET/SET/MGET). We REUSE the SAME lifespan
get_redis() client — never construct a second client (PITFALLS memory note).
"""

from __future__ import annotations

import os

from app.core.redis_client import get_redis
from shared.events import ExploreProgressEvent


def _screenshot_name(screenshot: str | None) -> str | None:
    """Reduce a (possibly absolute) screenshot path to its run-RELATIVE basename (M-1).

    perceive.capture_screenshot stores an absolute filesystem path on state; the live view
    must only ever see the basename so it builds the auth-gated screenshot URL — a raw
    filesystem path would both leak the layout and never load over the proxy.
    """
    if not screenshot:
        return None
    return os.path.basename(screenshot)


def build_progress_event(
    state: dict,
    *,
    cost_usd: float,
    elapsed_s: float,
    feed_line: str,
    current_title: str = "",
    stop_reason: str | None = None,
) -> ExploreProgressEvent:
    """Build an ExploreProgressEvent from explorer state + the gateway-sourced cost (D-06).

    `cost_usd` is an INPUT (read from the gateway's per-run counter) — never computed here.
    pages_found derives from the count of DISTINCT visited page keys; actions_taken tracks
    the step counter. screenshot_path is reduced to the run-relative basename (M-1).
    """
    visited = state.get("visited_keys") or []
    return ExploreProgressEvent(
        run_id=state["run_id"],
        step=int(state.get("step", 0)),
        pages_found=len(set(visited)),
        actions_taken=int(state.get("step", 0)),
        current_url=state.get("current_url") or "",
        current_title=current_title or "",
        screenshot_path=_screenshot_name(state.get("current_screenshot")),
        feed_line=feed_line,
        cost_usd=float(cost_usd),
        elapsed_s=float(elapsed_s),
        stop_reason=stop_reason,
    )


async def publish_progress(run_id: str, event: ExploreProgressEvent) -> None:
    """Publish the serialized event to the per-run pub/sub channel `explore:{run_id}`.

    REUSES the shared lifespan client (get_redis()). The payload is model_dump_json() text
    (the SSE endpoint forwards it verbatim as the event `data`). Best-effort: a publish to a
    channel with zero subscribers is a no-op, not an error.
    """
    await get_redis().publish(f"explore:{run_id}", event.model_dump_json())
