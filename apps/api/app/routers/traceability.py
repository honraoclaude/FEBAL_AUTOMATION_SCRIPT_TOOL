"""/api/traceability — the DASH-05 read-time cross-store traceability viewer (role-gated).

GET /api/traceability resolves the full lifecycle chain (flow ↔ scenario ↔ script ↔ execution ↔
defect) from a SINGLE entry artifact id — a flow_id, scenario_id, run_id, or defect_id passed as a
query param (the ?type=&id= deep-link contract the viewer builds). It is a READ-only join over the
Neo4j flow set + the Postgres lifecycle tables (the service adds NO graph writes).

Role-gated per the rbac.py endpoint→role matrix: admin, qa_lead, developer (router-level
dependencies=[Depends(require_role(...))] — deny-by-default 403 otherwise; 401 unauthenticated).

ROUTER-ORDERING CAVEAT (the defects.py /calibration-before-/{id} lesson): this router exposes ONLY
the static `GET ""` with query params — there is NO typed `/{id}` path converter to shadow, so no
static-before-typed ordering hazard exists here.

EXACTLY ONE ENTRY ID: zero or multiple ids → 422 (the router never silently picks one). An unknown
id is NOT an error — the service returns an honest EMPTY chain and the router returns it at 200 (the
"no chain found" state the viewer renders as gaps, NOT a 404).

GRAPH-DOWN: the service degrades the flow segment to null + a note rather than raising, so a down
graph never 500s the chain (T-10-16). No LLM, no broker.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.neo4j_driver import get_neo4j
from app.core.security import require_role
from app.db.session import get_db
from app.schemas.traceability import TraceabilityResponse
from app.services import traceability

router = APIRouter(
    prefix="/api/traceability",
    tags=["traceability"],
    # rbac.py matrix: traceability -> admin, qa_lead, developer. Deny-by-default 403 otherwise.
    dependencies=[Depends(require_role("admin", "qa_lead", "developer"))],
)


@router.get("", response_model=TraceabilityResponse)
async def get_traceability(
    flow_id: str | None = None,
    run_id: str | None = None,
    scenario_id: int | None = None,
    defect_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> TraceabilityResponse:
    """Assemble the lifecycle chain for EXACTLY one entry artifact id (422 for zero or multiple).

    An unknown id returns an honest empty chain (200, NOT 404). The neo4j driver is passed through
    so the flow segment reads the discovered-flow record; a down graph degrades to flow=null + a
    note (never a 500).
    """
    provided = [v for v in (flow_id, run_id, scenario_id, defect_id) if v is not None]
    if len(provided) != 1:
        raise HTTPException(
            status_code=422,
            detail=(
                "Provide exactly one entry id: flow_id, run_id, scenario_id, or defect_id."
            ),
        )

    # The driver is best-effort — the lazy singleton never connects at construct; a down graph is
    # handled INSIDE traceability.chain (flow=null + note), so fetching it here never blocks.
    driver = get_neo4j()
    result = await traceability.chain(
        db,
        flow_id=flow_id,
        run_id=run_id,
        scenario_id=scenario_id,
        defect_id=defect_id,
        driver=driver,
    )
    return TraceabilityResponse(**result)
