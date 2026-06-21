"""/api/executions — the SINGLE owner of the execution surface (EXEC-02/05, B1/I1).

This router is the ONLY home of the `/api/executions` prefix (B1, T-07-18): exactly one handler
per (method, path). It owns:

  - POST /api/executions {tier}          -> 202 + run_id: resolve the tier (incl. risk-based),
    create a test_run row, enqueue ONE job per chosen flow (per-flow enqueue for all tiers).
  - GET  /api/executions                 -> the test_runs history as TestRunResponse[].
  - GET  /api/executions/{run_id}        -> the run status + per-flow results summary (404 unknown).
  - GET  /api/executions/{run_id}/legacy-status -> the Phase-3 RunStatus poll surface, NAMESPACED
    here so the Phase-3 explore/execute single-spec path stays reachable WITHOUT a duplicate
    (GET, "/{run_id}") registration (the Phase-7 history surface supersedes the old GET "/{run_id}").

AUTH (T-07-10 + I1): the router-level gate accepts EITHER the httpOnly access_token cookie
(`get_current_user`, the dashboard path) OR the scoped `settings.ci_token` as a Bearer credential
(the CI workflow path, Plan 05 — start + poll scope). An unauthenticated request -> 401. The CI
token is compared with `hmac.compare_digest` and is NEVER echoed/logged (T-07-07/08).

Tier resolution + enqueue (resolve_tier / resolve_flows_for_tier / create_test_run / enqueue_jobs)
all live in exec_service — this router only wires the round-trip. NO /api/executions route lives
in execute.py (that file keeps only POST /api/execute).
"""

from __future__ import annotations

import hmac

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.config import settings
from app.core.redis_client import get_redis
from app.core.security import get_current_user
from app.core.workspaces import run_dir
from app.db.session import get_db
from app.schemas.execution import ExecuteTierRequest, TestRunResponse
from app.schemas.run import RunStatus
from app.services import exec_history, exec_service, run_service
from app.services.run_service import RunNotFoundError
from app.services.worker.progress import build_counters
from shared.events import ExecutionProgressEvent

log = structlog.get_logger()

# Media types served by the multi-segment artifact route, by file suffix (W4: screenshot/trace/
# video ONLY — console + network live inside the trace).
_ARTIFACT_MEDIA_TYPES = {
    ".png": "image/png",
    ".zip": "application/zip",
    ".webm": "video/webm",
}


def _ci_token_presented(request: Request) -> bool:
    """True iff a valid scoped CI bearer is present (I1; constant-time compare, never logged).

    Reads `Authorization: Bearer <token>` and accepts it ONLY when settings.ci_token is set and
    the presented value matches it (start + poll scope). The token is compared with
    hmac.compare_digest and is never echoed into logs or responses (T-07-07).
    """
    expected = settings.ci_token
    if not expected:
        return False
    header = request.headers.get("Authorization", "")
    scheme, _, credential = header.partition(" ")
    if scheme.lower() != "bearer" or not credential:
        return False
    return hmac.compare_digest(credential, expected)


async def require_user_or_ci_token(
    request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    """Router gate: accept the access_token cookie OR the scoped ci_token bearer (I1) else 401.

    The CI workflow (Plan 05) authenticates start/poll with the bearer; the dashboard uses the
    cookie. Either satisfies the gate; neither -> 401. Checked bearer-first so a CI request never
    needs a user row; the cookie path delegates to get_current_user (which 401s on its own).
    """
    if _ci_token_presented(request):
        return
    # Falls back to the cookie path; get_current_user raises 401 when the cookie is absent/bad.
    await get_current_user(request, db)


router = APIRouter(
    prefix="/api/executions",
    tags=["executions"],
    # Router-level gate: cookie OR scoped ci_token bearer (I1) — unauth is 401 on every route.
    dependencies=[Depends(require_user_or_ci_token)],
)

_NOT_FOUND = "No execution run found for this run_id"


@router.post("", status_code=202)
async def start_execution(
    body: ExecuteTierRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Start a tier run (B1): resolve tier -> create test_run -> enqueue per-flow jobs -> 202.

    `resolve_tier` validates the tier against the allow-list (422 on the ValueError — T-07-05).
    `resolve_flows_for_tier` materializes the per-flow job list (tag/full from approved scenarios,
    risk-based from rank_risk_flows BEFORE the run phase — D-03b). The run row is created and the
    jobs enqueued; an empty job list is a valid no-flow run (still 202). Mirrors explore.py's 202.
    """
    try:
        selector_tokens = exec_service.resolve_tier(body.tier)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    jobs = await exec_service.resolve_flows_for_tier(db, body.tier)
    selector = " ".join(selector_tokens) if selector_tokens else None
    run = await exec_service.create_test_run(db, body.tier, selector=selector)
    await exec_service.enqueue_jobs(run.run_id, jobs)
    log.info("start_execution", run_id=run.run_id, tier=body.tier, jobs=len(jobs))
    return {"run_id": run.run_id, "status": run.status}


@router.get("", response_model=list[TestRunResponse])
async def list_runs(db: AsyncSession = Depends(get_db)) -> list[TestRunResponse]:
    """The test_runs history newest-first (the Phase-7 history surface supersedes the old dict)."""
    runs = await exec_history.list_runs(db)
    return [TestRunResponse.model_validate(r) for r in runs]


@router.get("/{run_id}")
async def get_execution_status(
    run_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    """The test_run status + per-flow results summary; 404 when the run_id is unknown."""
    status = await exec_history.get_run_status(db, run_id)
    if status is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return status


@router.get("/{run_id}/legacy-status", response_model=RunStatus)
async def get_legacy_run_status(
    run_id: str, db: AsyncSession = Depends(get_db)
) -> RunStatus:
    """The Phase-3 run_id-keyed RunStatus (Execution row else Run row — FIX 1), NAMESPACED.

    Kept reachable for the legacy explore/execute single-spec poll path without a duplicate
    (GET, "/{run_id}") registration (the Phase-7 history surface owns the bare "/{run_id}").
    """
    try:
        status = await run_service.get_status_by_run_id(db, run_id)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return RunStatus(**status)


# --- EXEC-06 live view: SSE re-emit + current-counter reconnect snapshot (D-06, W3) ---------


async def _exec_snapshot_event(db: AsyncSession, run_id: str) -> str | None:
    """A current-state SNAPSHOT frame for a (re)subscribing client (W3 — RICHER than terminal).

    Unlike explore.py's terminal-only snapshot, this builds the CURRENT run counters
    (total/passed/failed/flaky) + the current status from the test_run row + the test_results
    aggregate (via build_counters), so a MID-RUN reconnect sees the live counters — not just a
    terminal/empty state. Returns the JSON frame, or None when the run_id is unknown (no row).
    The per-test delta fields are null on a snapshot (it is a counters-only frame).
    """
    counters = await build_counters(db, run_id)
    # build_counters returns status "running" with zero counters for an unknown run; distinguish
    # an unknown run by checking the row exists (a run with no results is still a valid snapshot).
    status = await exec_history.get_run_status(db, run_id)
    if status is None:
        return None
    event = ExecutionProgressEvent(
        run_id=run_id,
        completed=counters["completed"],
        total=counters["total"],
        passed=counters["passed"],
        failed=counters["failed"],
        flaky=counters["flaky"],
        elapsed_s=0.0,
        status=counters["status"],
    )
    return event.model_dump_json()


@router.get("/{run_id}/events")
async def execution_events(
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """Stream per-test ExecutionProgressEvents via SSE (EventSourceResponse over Redis pub/sub).

    Auth-gated by the router (T-07-13). On (re)subscribe it FIRST emits a current-state snapshot
    (current counters from the test_run row + test_results aggregate — W3, so a mid-run reconnect
    reconciles without replay), then forwards each frame published to `exec:{run_id}`. Breaks on
    client disconnect and unsubscribes the pub/sub in a finally (no leaked subscription).
    """
    snapshot = await _exec_snapshot_event(db, run_id)

    async def event_generator():
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(f"exec:{run_id}")
        try:
            if snapshot is not None:
                yield {"event": "snapshot", "data": snapshot}
            async for message in pubsub.listen():
                if await request.is_disconnected():
                    break
                if message is None or message.get("type") != "message":
                    continue
                yield {"event": "test", "data": message["data"]}
        finally:
            await pubsub.unsubscribe(f"exec:{run_id}")
            await pubsub.aclose()

    return EventSourceResponse(event_generator())


@router.post("/{run_id}/kill")
async def kill_execution(run_id: str) -> dict:
    """Graceful cooperative kill (D-07): set the Redis kill flag + purge the queue. No SIGKILL.

    Delegates to exec_service.kill_run — the worker checks the flag BETWEEN tests and drains
    (remaining flows resolve to `aborted`, not product_failure); the durable exec.jobs queue is
    purged of pending jobs. Returns {stopping: True} immediately (the run shows an honest
    "Stopping…" draining state until the in-flight test finishes).
    """
    await exec_service.kill_run(run_id)
    return {"stopping": True}


@router.get("/{run_id}/artifacts/{flow_id}/{name:path}")
async def execution_artifact(run_id: str, flow_id: str, name: str) -> FileResponse:
    """Serve a per-test artifact (screenshot/trace/video) — multi-segment path-traversal-safe.

    ADAPTS the explore.py bare-filename guard to a MULTI-SEGMENT run-relative path (B2): exec
    artifacts live in per-test subdirs (`<flow_id>/<test-slug>/trace.zip`), so `name` is declared
    a path converter that may carry subdir segments. The full run-relative target is
    `flow_id + "/" + name`; EACH segment is rejected if empty, `.`, `..`, or carrying a
    backslash, BEFORE touching the filesystem. The resolved `run_dir(run_id)/flow_id/name` MUST
    stay inside run_dir(run_id) (realpath containment) — the `{flow_id}` segment participates in
    resolution. A `..`-bearing name → 400; a missing file → 404 (T-07-14).
    """
    segments = [flow_id, *name.split("/")]
    if any(seg in ("", ".", "..") or "\\" in seg for seg in segments):
        raise HTTPException(status_code=400, detail="invalid artifact path")

    base = run_dir(run_id).resolve()
    target = (base / flow_id / name).resolve()
    # Realpath containment: the resolved target MUST stay inside the run's workspace.
    if target != base and base not in target.parents:
        raise HTTPException(status_code=400, detail="invalid artifact path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    media_type = _ARTIFACT_MEDIA_TYPES.get(target.suffix.lower())
    return FileResponse(str(target), media_type=media_type)
