"""Target registry CRUD (PLAT-01) — every route behind auth (T-01-20).

Routes return TargetResponse only: leak prevention is structural (the schema
has no credential fields), not filtered here.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.schemas.target import TargetCreate, TargetResponse, TargetUpdate
from app.services import target_service
from app.services.target_service import DuplicateTargetNameError

router = APIRouter(
    prefix="/api/targets",
    tags=["targets"],
    # Router-level gate: no route in this file is reachable unauthenticated.
    dependencies=[Depends(get_current_user)],
)

_NOT_FOUND = "Target not found"
_DUPLICATE = "A target with this name already exists"


@router.post("", status_code=201, response_model=TargetResponse)
async def register_target(body: TargetCreate, db: AsyncSession = Depends(get_db)) -> TargetResponse:
    try:
        target = await target_service.create_target(db, body)
    except DuplicateTargetNameError:
        raise HTTPException(status_code=409, detail=_DUPLICATE)
    return TargetResponse.model_validate(target)


@router.get("", response_model=list[TargetResponse])
async def list_targets(
    include_inactive: bool = False, db: AsyncSession = Depends(get_db)
) -> list[TargetResponse]:
    targets = await target_service.list_targets(db, include_inactive=include_inactive)
    return [TargetResponse.model_validate(t) for t in targets]


@router.get("/{target_id}", response_model=TargetResponse)
async def get_target(target_id: int, db: AsyncSession = Depends(get_db)) -> TargetResponse:
    target = await target_service.get_target(db, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return TargetResponse.model_validate(target)


@router.patch("/{target_id}", response_model=TargetResponse)
async def update_target(
    target_id: int, body: TargetUpdate, db: AsyncSession = Depends(get_db)
) -> TargetResponse:
    target = await target_service.get_target(db, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    try:
        target = await target_service.update_target(db, target, body)
    except DuplicateTargetNameError:
        raise HTTPException(status_code=409, detail=_DUPLICATE)
    return TargetResponse.model_validate(target)


@router.delete("/{target_id}", status_code=204)
async def soft_delete_target(target_id: int, db: AsyncSession = Depends(get_db)) -> Response:
    target = await target_service.get_target(db, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    await target_service.soft_delete(db, target)
    return Response(status_code=204)
