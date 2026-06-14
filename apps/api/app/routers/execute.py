"""POST /execute (PLAT-02, D-04) — 202 + run_id, subprocess spec run in a BackgroundTask.

The router DISCOVERS the run's generated spec by the filesystem convention
`workspaces/<run_id>/test_login.py` (FIX 3) — the same gitignored artifact tree the
generation service writes to (Plan 03). A 404 is returned when no spec exists for the
run_id (it was never generated). On success it creates a queued Execution row keyed BY
run_id (FIX 1), registers the subprocess runner as a BackgroundTask (the spec uses the
SYNC Playwright API and MUST run out-of-process — Pitfall 3), and returns 202.

The poll surface is the existing GET /api/executions/{run_id} (Plan 02), which resolves
the Execution row by run_id (FIX 1) — so poll_until_terminal reaches a terminal status.

Mirrors explore.py / targets.py: router-level Depends(get_current_user) (T-03-17).
"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.run import ExecuteRequest
from app.services import run_service
from app.services.execution import run_execution

router = APIRouter(
    prefix="/api",
    tags=["execute"],
    # Router-level gate: /execute is unreachable unauthenticated (T-03-17).
    dependencies=[Depends(get_current_user)],
)

# Repo root (app/routers/execute.py -> routers -> app -> api -> apps -> repo root) holds
# the gitignored workspaces/ tree, matching app.services.generation._workspaces_root.
_WORKSPACES_ROOT = Path(__file__).resolve().parents[4] / "workspaces"


def _spec_path_for(run_id: str) -> Path:
    """workspaces/<run_id>/test_login.py — the run_id-derived spec convention (FIX 3, T-01-26)."""
    return _WORKSPACES_ROOT / run_id / "test_login.py"


@router.post("/execute", status_code=202)
async def execute(
    body: ExecuteRequest,
    bg: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Discover the run's generated spec (404 if absent), enqueue the subprocess run (202)."""
    # FIX 3: resolve + verify the spec by the filesystem convention. A 404 here means the
    # spec was never generated for this run_id (no workspaces/<run_id>/test_login.py).
    spec_path = _spec_path_for(body.run_id)
    if not spec_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"no generated spec for run_id {body.run_id!r}",
        )

    # Create the run_id-keyed Execution row (status 'queued' — FIX 1); the subprocess
    # runner flips THIS row to terminal, observable via GET /executions/{run_id}.
    await run_service.create_execution(db, body.run_id, str(spec_path))
    # The task opens its OWN SessionLocal and runs the spec out-of-process (Pitfall 2/3).
    bg.add_task(run_execution, body.run_id, str(spec_path))
    return {"run_id": body.run_id, "status": "queued"}
