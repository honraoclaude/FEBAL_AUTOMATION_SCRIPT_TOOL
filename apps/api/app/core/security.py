"""Auth security core (PLAT-03, D-04).

argon2id password hashing, HS256 JWT mint/decode with a `type` claim
separating access from refresh tokens (T-01-09), httpOnly cookie helpers
(Pitfall 6: secure flag is a setting, false on plain-http localhost), and the
get_current_user dependency.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User

ph = PasswordHasher()  # argon2id defaults — OWASP-recommended posture

# Verified on the unknown-user login path so its cost matches a real verify
# (timing-based user-enumeration mitigation, T-01-08).
DUMMY_HASH = ph.hash("dummy-timing-pad")

ACCESS_TOKEN_MAX_AGE = 1800  # 30 min
REFRESH_TOKEN_MAX_AGE = 604800  # 7 days
REFRESH_COOKIE_PATH = "/api/auth"

_CREDENTIALS_401 = "Invalid or expired token"


def hash_password(plain: str) -> str:
    return ph.hash(plain)


def verify_password(hashed: str, plain: str) -> bool:
    """Constant-time argon2 verify; False on mismatch or malformed hash."""
    try:
        return ph.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_token(sub: str, token_type: str, expires: timedelta) -> str:
    """Mint an HS256 JWT with claims {sub, type, iat, exp, jti}.

    jti guarantees uniqueness even when two tokens for the same subject are
    minted within the same second (iat has 1s resolution) — required for the
    refresh-rotation behavior to be observable.
    """
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": sub,
            "type": token_type,
            "iat": now,
            "exp": now + expires,
            "jti": uuid.uuid4().hex,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode+verify an HS256 JWT; HTTPException(401) on any PyJWT error."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail=_CREDENTIALS_401)


def set_access_cookie(response: Response, access: str) -> None:
    response.set_cookie(
        "access_token",
        access,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=ACCESS_TOKEN_MAX_AGE,
        path="/",
    )


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    set_access_cookie(response, access)
    response.set_cookie(
        "refresh_token",
        refresh,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=REFRESH_TOKEN_MAX_AGE,
        path=REFRESH_COOKIE_PATH,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        "access_token",
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    response.delete_cookie(
        "refresh_token",
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> User:
    """Resolve the authenticated user from the access_token cookie or 401.

    Enforces type == "access" so a refresh token can never authenticate a
    request (T-01-09).
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail=_CREDENTIALS_401)
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail=_CREDENTIALS_401)
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=401, detail=_CREDENTIALS_401)
    return user


def require_role(*allowed: str):
    """RBAC dependency factory (PLAT-04 / D-01) — gate a route/router to a set of roles.

    Composes on `get_current_user` (which already resolves the User row from the access cookie)
    and reads `user.role` OFF THE ROW — never from the JWT (the token carries only
    {sub, type, iat, exp, jti}). Reading the role per request means an admin role change takes
    effect on the very next request: no token reissue, no stale-role window (T-10-03/04).

    Deny-by-default: a role not in `allowed` gets 403; the boundary is server-side (frontend
    nav-hiding is UX only). Use at the router level
    (`dependencies=[Depends(require_role("admin"))]`, mirroring routers/scenarios.py) so EVERY
    route on the router is gated, or per-route as a `Depends`.
    """

    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return _dep
