"""/api/dashboards — the three role-gated read-only dashboards (DASH-01/02/03).

Each endpoint is gated PER-ROUTE with `require_role(...)` for its permitted roles (the rbac.py
endpoint→role matrix from Plan 01) — server-side require_role IS the security boundary (the
frontend nav gating in Plan 05 is UX only). Deny-by-default: a disallowed role gets 403, an
unauthenticated request 401.

  - GET /api/dashboards/executive  (admin, qa_lead)              -> ExecutiveDashboard
  - GET /api/dashboards/qa         (admin, qa_lead, qa_engineer) -> QaDashboard
  - GET /api/dashboards/developer  (admin, qa_lead, developer)   -> DeveloperDashboard

The routes are per-route gated (NOT a single router-level dependency) because each dashboard has a
DIFFERENT permitted-role set. Each calls the matching dashboards.* aggregation and returns its
schema. The executive route passes the neo4j driver through to coverage; if the graph is down,
mine_flows_from_neo4j raises ServiceUnavailable which the main.py handler turns into a clean 503
(the relational tiles come from a separate request — never a fabricated zero coverage). No LLM.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_role
from app.db.session import get_db
from app.schemas.dashboards import (
    DeveloperDashboard,
    ExecutiveDashboard,
    QaDashboard,
)
from app.services import dashboards

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


@router.get(
    "/executive",
    response_model=ExecutiveDashboard,
    dependencies=[Depends(require_role("admin", "qa_lead"))],
)
async def executive(db: AsyncSession = Depends(get_db)) -> ExecutiveDashboard:
    """DASH-01: coverage + pass-rate trend + defects trend + KPIs (admin, qa_lead)."""
    return ExecutiveDashboard(**await dashboards.executive(db))


@router.get(
    "/qa",
    response_model=QaDashboard,
    dependencies=[Depends(require_role("admin", "qa_lead", "qa_engineer"))],
)
async def qa(db: AsyncSession = Depends(get_db)) -> QaDashboard:
    """DASH-02: run history + failed tests + artifact refs (admin, qa_lead, qa_engineer)."""
    return QaDashboard(**await dashboards.qa(db))


@router.get(
    "/developer",
    response_model=DeveloperDashboard,
    dependencies=[Depends(require_role("admin", "qa_lead", "developer"))],
)
async def developer(db: AsyncSession = Depends(get_db)) -> DeveloperDashboard:
    """DASH-03: root-cause groups + errors trend + module breakdown (admin, qa_lead, developer)."""
    return DeveloperDashboard(**await dashboards.developer(db))
