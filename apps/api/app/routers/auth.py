"""Auth endpoints: login, refresh, logout, me (PLAT-03, D-04)."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    DUMMY_HASH,
    clear_auth_cookies,
    create_token,
    decode_token,
    get_current_user,
    set_access_cookie,
    set_auth_cookies,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, MeResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

# One exception object for BOTH unknown-email and wrong-password so the 401
# bodies are byte-identical — no user enumeration (T-01-07).
_INVALID_CREDENTIALS = "Invalid email or password"


@router.post("/login")
async def login(
    body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> dict[str, bool]:
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None:
        # Burn an argon2 verify so unknown-email timing matches wrong-password
        # timing (T-01-08).
        verify_password(DUMMY_HASH, body.password)
        raise HTTPException(status_code=401, detail=_INVALID_CREDENTIALS)
    if not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail=_INVALID_CREDENTIALS)

    access = create_token(str(user.id), "access", timedelta(minutes=30))
    refresh = create_token(str(user.id), "refresh", timedelta(days=7))
    set_auth_cookies(response, access, refresh)
    return {"ok": True}


@router.post("/refresh")
async def refresh(request: Request, response: Response) -> dict[str, bool]:
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    access = create_token(payload["sub"], "access", timedelta(minutes=30))
    set_access_cookie(response, access)
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    # D-04: client-side invalidation only in Phase 1 (no denylist — T-01-12 accepted)
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(id=user.id, email=user.email, role=user.role)
