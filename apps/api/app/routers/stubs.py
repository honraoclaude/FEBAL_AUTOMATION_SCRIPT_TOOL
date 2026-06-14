"""The 5 honest 501 PLAT-02 stub endpoints — heal, create-defect, flows, coverage, dashboard.

These complete the 10-endpoint PLAT-02 surface (5 real from Plans 02-03 + /execute, plus
these 5). Each endpoint:
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
    CoverageResponse,
    CreateDefectRequest,
    CreateDefectResponse,
    DashboardResponse,
    FlowsResponse,
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
    "/flows",
    status_code=501,
    summary="List learned business flows from the knowledge graph (Phase 5)",
    response_model=FlowsResponse,
    responses=_NOT_IMPLEMENTED,
)
async def flows() -> FlowsResponse:
    """Learned flows — implemented in Phase 5. Returns 501 (never a fabricated flow list)."""
    raise HTTPException(status_code=501, detail="flows: not implemented (Phase 5)")


@router.get(
    "/coverage",
    status_code=501,
    summary="Aggregate coverage metrics (Phase 10)",
    response_model=CoverageResponse,
    responses=_NOT_IMPLEMENTED,
)
async def coverage() -> CoverageResponse:
    """Coverage metrics — implemented in Phase 10. Returns 501 (never fabricated numbers)."""
    raise HTTPException(status_code=501, detail="coverage: not implemented (Phase 10)")


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
