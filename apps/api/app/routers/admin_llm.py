"""Admin kill-switch endpoints (PLAT-06, D-05/D-06) — the manual panic button.

Every route is behind auth at the router level (T-02-08). The kill-switch is a
global halt: while set, every gateway complete() call across all runs raises
KillSwitchActive (the gateway checks the flag first on the hot path).

V4 GAP (documented, RESEARCH Security Domain): any AUTHENTICATED user can trip or
clear the switch today. Role-based restriction to Admin lands in Phase 10 (RBAC);
until then the auth gate is the only control. The handlers write the Redis flag via
the gateway's set/clear/get_killswitch helpers (Redis, not Postgres).
"""

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.schemas.llm import KillSwitchRequest
from app.services import llm_gateway

router = APIRouter(
    prefix="/api/admin/llm",
    tags=["admin-llm"],
    # Router-level gate: no route here is reachable unauthenticated.
    dependencies=[Depends(get_current_user)],
)


@router.post("/killswitch", status_code=200)
async def trip_killswitch(body: KillSwitchRequest) -> dict:
    """Set the global kill-switch — halts all LLM traffic immediately."""
    try:
        await llm_gateway.set_killswitch(body.reason)
    except Exception as exc:  # noqa: BLE001 — surface Redis failures as 503
        raise HTTPException(status_code=503, detail="Could not set kill-switch") from exc
    return {"active": True, "reason": body.reason}


@router.delete("/killswitch", status_code=200)
async def clear_killswitch() -> dict:
    """Clear the global kill-switch — resumes LLM traffic."""
    try:
        await llm_gateway.clear_killswitch()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="Could not clear kill-switch") from exc
    return {"active": False}


@router.get("/killswitch", status_code=200)
async def read_killswitch() -> dict:
    """Report current kill-switch state."""
    try:
        reason = await llm_gateway.get_killswitch()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="Could not read kill-switch") from exc
    return {"active": reason is not None, "reason": reason}
