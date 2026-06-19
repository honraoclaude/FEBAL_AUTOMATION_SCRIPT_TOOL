"""The remaining honest 501 PLAT-02 stub endpoints — heal, create-defect, dashboard.

These are the not-yet-built PLAT-02 endpoints. (`/flows` + `/coverage` were Phase-3 501
stubs here too; Phase 5 / slice 03 made them REAL read-only endpoints in `routers/kg.py`,
so they no longer live in this module.) Each endpoint:
  - is behind the router-level auth gate (Depends(get_current_user) — T-03-17),
  - documents its EVENTUAL request/response contract via schemas/stub.py + `responses=`
    (so the OpenAPI schema is COMPLETE), and
  - returns 501 Not Implemented ONLY — it NEVER fabricates a plausible result payload
    (T-03-19 / CONTEXT discretion / RESEARCH anti-pattern). The surface is complete AND
    honest: it advertises the shape without faking the behavior.

Each `detail` names the phase that will implement the real behavior. Mirrors admin_llm.py:
a small router with an explicit per-route `status_code=`.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.schemas.stub import (
    CreateDefectRequest,
    CreateDefectResponse,
    DashboardResponse,
    HealRequest,
    HealResponse,
)

router = APIRouter(
    prefix="/api",
    tags=["stubs"],
    # Router-level gate: no stub is reachable unauthenticated (T-03-17).
    dependencies=[Depends(get_current_user)],
)

# Shared 501 OpenAPI doc so every stub advertises that it is not-yet-implemented.
_NOT_IMPLEMENTED = {501: {"description": "Not implemented yet — documented contract only"}}


@router.post(
    "/heal",
    status_code=501,
    summary="Self-heal a broken locator (Phase 8)",
    response_model=HealResponse,
    responses=_NOT_IMPLEMENTED,
)
async def heal(body: HealRequest) -> HealResponse:
    """Locator self-healing — implemented in Phase 8. Returns 501 (never a fake heal)."""
    raise HTTPException(status_code=501, detail="heal: not implemented (Phase 8)")


@router.post(
    "/create-defect",
    status_code=501,
    summary="Auto-file a Jira defect from a classified failure (Phase 9)",
    response_model=CreateDefectResponse,
    responses=_NOT_IMPLEMENTED,
)
async def create_defect(body: CreateDefectRequest) -> CreateDefectResponse:
    """Jira defect creation — implemented in Phase 9. Returns 501 (never a fake issue)."""
    raise HTTPException(
        status_code=501, detail="create-defect: not implemented (Phase 9)"
    )


@router.get(
    "/dashboard",
    status_code=501,
    summary="Top-level dashboard rollup (Phase 10)",
    response_model=DashboardResponse,
    responses=_NOT_IMPLEMENTED,
)
async def dashboard() -> DashboardResponse:
    """Dashboard rollup — implemented in Phase 10. Returns 501 (never a fabricated rollup)."""
    raise HTTPException(status_code=501, detail="dashboard: not implemented (Phase 10)")
