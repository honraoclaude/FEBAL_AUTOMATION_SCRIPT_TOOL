"""POST /explore (PLAT-02, D-04) — 202 + run_id, deterministic crawl in a BackgroundTask.

The router creates a queued Run, registers the in-process crawl as a BackgroundTask, and
returns immediately (202). The crawl owns its own session (Pitfall 2). Every route is
behind auth (T-03-07).
"""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.run import ExploreRequest
from app.services import run_service
from app.services.explorer import run_explore

router = APIRouter(
    prefix="/api",
    tags=["explore"],
    # Router-level gate: /explore is unreachable unauthenticated (T-03-07).
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
