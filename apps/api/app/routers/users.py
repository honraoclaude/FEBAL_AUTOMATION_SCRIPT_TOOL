"""Admin user-management router (PLAT-04 / D-01) — list users + assign roles.

The admin-only RBAC surface that lets the platform Admin see every account and assign one of the
four roles. Server-side enforcement is the security boundary (frontend nav-hiding is UX only).

  GET  /api/users                list all users (id, email, role) — no secrets
  POST /api/users/{id}/role      assign a role to the target user

INVARIANTS (the threat model, 10-01):
  - T-10-01 (privilege escalation): router-level `dependencies=[Depends(require_role("admin"))]`
    — a non-admin cannot REACH any route (403); the body `role` is the value being ASSIGNED, it
    is NEVER read to authorize the caller (authorization is require_role, off the caller's row).
  - T-10-02 (self-demote / lockout): the current admin cannot change THEIR OWN role -> 400, so
    the only admin can never lock themselves (or every admin) out.
  - Invalid role -> 422 at the schema boundary (RoleAssignRequest is a Literal of the four roles).
  - Unknown target id -> 404.

Mirrors the auth-gated router precedent (routers/scenarios.py router-level dependency) and the
select(User) read/write idiom (core/security.get_current_user).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import RoleAssignRequest, UserSummary

router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    # Router-level RBAC gate: every /api/users route is Admin-only (T-10-01). A non-admin gets
    # 403, an unauthenticated request gets 401 (require_role composes on get_current_user).
    dependencies=[Depends(require_role("admin"))],
)


@router.get("", response_model=list[UserSummary])
async def list_users(db: AsyncSession = Depends(get_db)) -> list[UserSummary]:
    """List every user (id, email, role) — Admin only. No password/secret fields are returned."""
    rows = (await db.scalars(select(User).order_by(User.id))).all()
    return [UserSummary(id=u.id, email=u.email, role=u.role) for u in rows]


@router.post("/{user_id}/role", response_model=UserSummary)
async def assign_role(
    user_id: int,
    body: RoleAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserSummary:
    """Assign a role to the target user — Admin only.

    The body role is already validated to the four-role vocabulary by RoleAssignRequest (else 422
    before this runs). The self-demote guard (T-10-02) rejects the admin changing their OWN role.
    """
    # Self-demote / lockout guard: the current admin cannot change their own role (T-10-02).
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't change your own role")

    target = await db.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    target.role = body.role
    await db.commit()
    await db.refresh(target)
    return UserSummary(id=target.id, email=target.email, role=target.role)
