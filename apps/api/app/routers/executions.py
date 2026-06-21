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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.execution import ExecuteTierRequest, TestRunResponse
from app.schemas.run import RunStatus
from app.services import exec_history, exec_service, run_service
from app.services.run_service import RunNotFoundError

log = structlog.get_logger()


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
