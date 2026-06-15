"""POST /explore (PLAT-02, D-04) + the EXPL-01 live-progress seam (SSE/screenshot/stop).

The router creates a queued Run, registers the in-process crawl as a BackgroundTask, and
returns 202 immediately (the crawl owns its own session — Pitfall 2). EXPL-01 (D-07) adds:
  - GET /explore/{run_id}/events — sse-starlette EventSourceResponse over a Redis pub/sub
    subscription to `explore:{run_id}`; emits a current-state SNAPSHOT first so a (re)connect
    reconciles without replay, then forwards each published ExploreProgressEvent; unsubscribes
    in a finally on client disconnect (T-04-16 auth gate; T-04-18 cleanup).
  - GET /explore/{run_id}/screenshot/{name} — FileResponse PNG resolved ONLY inside the run's
    workspace; a separator/`..`/escape is rejected (T-04-17 path-traversal guard).
  - POST /explore/{run_id}/stop — sets the L-3 cooperative-cancel flag in Redis.

Every route is behind the router-level auth gate (T-03-07/T-04-16); EventSource can't set
headers, so the httpOnly access_token cookie (same-origin proxy) is the only auth.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.redis_client import get_redis
from app.core.security import get_current_user
from app.core.workspaces import run_dir
from app.db.session import get_db
from app.schemas.run import ExploreRequest
from app.services import run_service
from app.services.explorer import run_explore

router = APIRouter(
    prefix="/api",
    tags=["explore"],
    # Router-level gate: /explore is unreachable unauthenticated (T-03-07/T-04-16).
    dependencies=[Depends(get_current_user)],
)


@router.post("/explore", status_code=202)
async def explore(
    body: ExploreRequest,
    bg: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Enqueue a deterministic explore crawl; return 202 + the threading run_id."""
    run = await run_service.create_run(db, kind="explore", target_id=body.target_id)
    # The task opens its OWN SessionLocal — never the request's db (Pitfall 2).
    bg.add_task(run_explore, run.run_id, body.target_id)
    return {"run_id": run.run_id, "status": "queued"}


async def _snapshot_event(db: AsyncSession, run_id: str) -> str | None:
    """Resolve a current-state SNAPSHOT for a (re)subscribing client (no full replay).

    If the run already reached a terminal status, emit a synthetic terminal progress event so
    a late/reconnecting client renders the correct end state immediately. Returns None for an
    in-flight run with no terminal state yet (the live stream is then the source of truth).
    """
    run = await run_service.get_run(db, run_id)
    if run is None:
        return None
    stop_reason = getattr(run, "stop_reason", None)
    status = getattr(run, "status", None)
    if status in {"passed", "failed"} or stop_reason:
        # Terminal: map failed -> "failed" so the UI shows the red state even if the row has
        # no explicit stop_reason; otherwise use the recorded reason.
        reason = stop_reason or ("failed" if status == "failed" else "stopped")
        return json.dumps(
            {
                "run_id": run_id,
                "step": 0,
                "pages_found": 0,
                "actions_taken": 0,
                "current_url": "",
                "current_title": "",
                "screenshot_path": None,
                "feed_line": "snapshot: run already terminal",
                "cost_usd": 0.0,
                "elapsed_s": 0.0,
                "stop_reason": reason,
            }
        )
    return None


@router.get("/explore/{run_id}/events")
async def explore_events(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """Stream ExploreProgressEvents for a run via SSE (EventSourceResponse over Redis pub/sub).

    Auth-gated by the router (T-04-16). On (re)subscribe, first emits a current-state snapshot
    (so reconnection reconciles without replay), then forwards each message published to
    `explore:{run_id}`. Breaks on client disconnect and unsubscribes the pub/sub in a finally
    (T-04-18 — no leaked subscription holds the stream open).
    """
    snapshot = await _snapshot_event(db, run_id)

    async def event_generator():
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(f"explore:{run_id}")
        try:
            if snapshot is not None:
                yield {"event": "snapshot", "data": snapshot}
            async for message in pubsub.listen():
                if await request.is_disconnected():
                    break
                if message is None or message.get("type") != "message":
                    continue
                yield {"event": "step", "data": message["data"]}
        finally:
            # Release the subscription + connection regardless of how the stream ended.
            await pubsub.unsubscribe(f"explore:{run_id}")
            await pubsub.aclose()

    return EventSourceResponse(event_generator())


@router.get("/explore/{run_id}/screenshot/{name}")
async def explore_screenshot(run_id: str, name: str) -> FileResponse:
    """Serve a run-scoped evidence screenshot PNG (M-1) — auth-gated + path-traversal-safe.

    Resolves ONLY within WORKSPACES_DIR/<run_id>: a `name` carrying a path separator or `..`,
    or a resolved target that escapes the run workspace, is rejected (T-04-17). The browser
    <img src> reaches this over the same-origin proxy so the httpOnly cookie authenticates it.
    """
    # Reject anything that is not a bare filename BEFORE touching the filesystem.
    if not name or "/" in name or "\\" in name or os.sep in name or ".." in name:
        raise HTTPException(status_code=400, detail="invalid screenshot name")

    base = run_dir(run_id).resolve()
    target = (base / name).resolve()
    # Containment guard: the resolved target MUST stay inside the run's workspace.
    if target != base and base not in target.parents:
        raise HTTPException(status_code=400, detail="invalid screenshot path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="screenshot not found")
    return FileResponse(str(target), media_type="image/png")


@router.post("/explore/{run_id}/stop")
async def explore_stop(run_id: str) -> dict:
    """L-3 cooperative Stop: set the Redis cancel flag the explorer loop honors at loop-top.

    The crawl's check_cancel node reads `explore:cancel:{run_id}` at the top of each iteration
    and short-circuits to stop_reason="stopped" + a terminal progress event. Durable/forceful
    cancellation stays Phase 7 — this is the minimal cooperative stop the UI's Stop button needs.
    """
    await get_redis().set(f"explore:cancel:{run_id}", "1")
    return {"stopping": True}
