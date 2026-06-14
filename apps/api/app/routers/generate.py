"""POST /generate-bdd, /generate-scripts (PLAT-02, D-07) — every route behind auth.

These are the metered generation endpoints: each takes the explore run_id, delegates to
the generation service (which routes through the LLM gateway, validates Gherkin, and
renders the spec from a Jinja2 skeleton), and returns the run_id-keyed artifact path.

Mirrors targets.py: router-level Depends(get_current_user) (T-03-13) and typed-exception
translation (GenerationError -> 422; an unknown/unexplored run_id -> 404).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.run import GenerateRequest
from app.services import generation, run_service

router = APIRouter(
    prefix="/api",
    tags=["generate"],
    # Router-level gate: neither generate route is reachable unauthenticated (T-03-13).
    dependencies=[Depends(get_current_user)],
)

_RUN_NOT_FOUND = "No explore run found for this run_id"


async def _require_run(db: AsyncSession, run_id: str) -> None:
    """404 when no Run exists for this run_id (generation needs an explored run)."""
    if await run_service.get_run(db, run_id) is None:
        raise HTTPException(status_code=404, detail=_RUN_NOT_FOUND)


@router.post("/generate-bdd")
async def generate_bdd(
    body: GenerateRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Generate + gherkin-validate a .feature for the run_id; return its path."""
    await _require_run(db, body.run_id)
    try:
        feature_path = await generation.generate_bdd(db, body.run_id)
    except generation.GenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"run_id": body.run_id, "feature_path": feature_path}


@router.post("/generate-scripts")
async def generate_scripts(
    body: GenerateRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Render a runnable pytest-playwright spec for the run_id; return its spec_path."""
    await _require_run(db, body.run_id)
    try:
        spec_path = await generation.generate_scripts(db, body.run_id)
    except generation.GenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"run_id": body.run_id, "spec_path": spec_path}
