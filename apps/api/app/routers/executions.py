"""GET /executions (PLAT-02, D-04) — the run_id-keyed poll surface.

`GET /executions` lists run + execution rows. `GET /executions/{run_id}` resolves a
single terminal-capable status by run_id for BOTH paths via run_service.get_status_by_run_id
(FIX 1): the Execution row for execute-path run_ids, the Run row for explore-path run_ids.
This is the endpoint poll_until_terminal targets — it terminates for either path.

Every route is behind auth (T-03-07).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.run import ExecutionResponse, RunResponse, RunStatus
from app.services import run_service
from app.services.run_service import RunNotFoundError

router = APIRouter(
    prefix="/api/executions",
    tags=["executions"],
    dependencies=[Depends(get_current_user)],
)

_NOT_FOUND = "No run or execution found for this run_id"


@router.get("", response_model=dict)
async def list_executions(db: AsyncSession = Depends(get_db)) -> dict:
    """List run + execution rows (the slice's full async-job ledger)."""
    runs = await run_service.list_runs(db)
    executions = await run_service.list_executions(db)
    return {
        "runs": [RunResponse.model_validate(r).model_dump(mode="json") for r in runs],
        "executions": [
            ExecutionResponse.model_validate(e).model_dump(mode="json") for e in executions
        ],
    }


@router.get("/{run_id}", response_model=RunStatus)
async def get_execution_status(
    run_id: str, db: AsyncSession = Depends(get_db)
) -> RunStatus:
    """Resolve a single run_id-keyed status (Execution row else Run row — FIX 1)."""
    try:
        status = await run_service.get_status_by_run_id(db, run_id)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return RunStatus(**status)
