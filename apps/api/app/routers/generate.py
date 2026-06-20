"""POST /generate-bdd, /generate-scripts, /generate-scenarios (PLAT-02 / GEN-01, D-07).

These are the metered generation endpoints: each takes the explore run_id, delegates to
the generation service (which routes through the LLM gateway, validates Gherkin, and
renders the spec from a Jinja2 skeleton), and returns the run_id-keyed artifact path.

`/generate-scenarios` (GEN-01 / Slice 2) is the review-queue feeder: it generates quality-gated
DRAFT scenario rows for every mined flow of the run_id (validate-before-persist; only approved
rows later feed codegen — D-01). The generate-scripts CODEGEN wiring (approved-only → Playwright
project) lands in Slice 3; this slice adds the scenarios entrypoint + its request schema only.

Mirrors targets.py: router-level Depends(get_current_user) (T-03-13 / T-06-07) and typed-exception
translation (GenerationError -> 422; an unknown/unexplored run_id -> 404).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.run import GenerateRequest
from app.schemas.scenario import GenerateScenariosRequest, GenerateScriptsRequest
from app.services import generation, run_service
from app.services.codegen import project as codegen_project
from app.services.gates.selector_gate import SelectorGateError

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
    body: GenerateScriptsRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Codegen the full Playwright project from the run's APPROVED scenarios (GEN-04 / D-01/D-06).

    Reads scenario_service.list_approved (approved-only) and renders the Element-Repository-sourced
    project tree (pages/steps/features/conftest/fixtures/utils/data/reports) under
    workspaces/<run_id>/<target>/. Every rendered .py is ast-parsed + freehand-selector-gated
    BEFORE any write; a parse failure or an inline selector literal aborts with 422 (no partial
    write). Returns the project root path. (Supersedes the Phase-3 plain-spec generate-scripts;
    templates/test_login.py.j2 is retained for the planted-spec proof.)
    """
    await _require_run(db, body.run_id)
    try:
        project_root = await codegen_project.generate_project(db, body.run_id)
    except (generation.GenerationError, SelectorGateError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"run_id": body.run_id, "project_root": project_root}


@router.post("/generate-scenarios")
async def generate_scenarios(
    body: GenerateScenariosRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Generate quality-gated DRAFT scenarios for every mined flow of the run_id (GEN-01).

    Routes one metered gateway call per flow (with a deterministic no-key fallback), validates
    lint + no-vacuous BEFORE persisting each draft row, and returns the created scenario ids.
    The review queue (GET /api/scenarios) lists these drafts; only approved rows feed codegen.
    """
    await _require_run(db, body.run_id)
    try:
        scenario_ids = await generation.generate_scenarios(db, body.run_id)
    except generation.GenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"run_id": body.run_id, "scenario_ids": scenario_ids}
