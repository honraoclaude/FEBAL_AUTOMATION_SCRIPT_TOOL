"""/api/coverage/flows — the DASH-04 lifecycle-coverage panel (role-gated).

The graph-derived lifecycle coverage metric (approved scenario AND passing execution), DISTINCT
from the Phase-5 ground-truth coverage at /api/coverage (kg router). This router is role-gated per
the rbac.py endpoint→role matrix: admin, qa_lead, developer.

Mirrors routers/scenarios.py (router-level dependencies gate) + routers/kg.py (on-read graph
compute). When the graph is down, mine_flows_from_neo4j raises ServiceUnavailable which the
main.py _neo4j_unavailable_handler turns into a clean 503 — never a fabricated zero coverage.
No LLM.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_role
from app.db.session import get_db
from app.schemas.coverage_dash import CoverageResponse
from app.services import coverage_dash

router = APIRouter(
    prefix="/api/coverage",
    tags=["coverage"],
    # rbac.py matrix: coverage -> admin, qa_lead, developer. Deny-by-default 403 otherwise.
    dependencies=[Depends(require_role("admin", "qa_lead", "developer"))],
)


@router.get("/flows", response_model=CoverageResponse)
async def coverage_flows(db: AsyncSession = Depends(get_db)) -> CoverageResponse:
    """Lifecycle coverage over the CURRENT mined flows + the honest definition + drill-down."""
    return CoverageResponse(**await coverage_dash.coverage(db))
