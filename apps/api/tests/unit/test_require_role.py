"""require_role DI factory proof (PLAT-04 / D-01) — pure, keyless, no DB, no HTTP.

`require_role(*allowed)` returns an async dependency `_dep(user=Depends(get_current_user))`
that reads `user.role` OFF THE ROW and:
  - returns the user when their role is in `allowed`;
  - raises HTTPException(403, "Insufficient role") otherwise.

These tests call the inner `_dep` directly with a stub user (the seam is `get_current_user`,
which is overridden via Depends in the routers — here we exercise the role check in isolation).

Run: cd apps/api && uv run python -m pytest tests/unit/test_require_role.py -x -q
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from app.core.security import require_role


@dataclass
class _StubUser:
    """Minimal stand-in for the User row require_role reads `.role` off of."""

    id: int = 1
    email: str = "u@example.com"
    role: str = "developer"


def _dep_of(*allowed: str):
    """require_role returns a dependency callable; pull it out to call directly."""
    return require_role(*allowed)


async def test_allowed_role_returns_user() -> None:
    """An allowed role -> the dependency returns the same user (no raise)."""
    dep = _dep_of("admin")
    user = _StubUser(role="admin")
    result = await dep(user=user)
    assert result is user


async def test_disallowed_role_raises_403() -> None:
    """A role not in the allow-list -> HTTPException(403, 'Insufficient role')."""
    dep = _dep_of("admin")
    user = _StubUser(role="developer")
    with pytest.raises(HTTPException) as exc:
        await dep(user=user)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Insufficient role"


async def test_multi_role_allow_list_passes_member() -> None:
    """require_role with several roles passes a user whose role is any one of them."""
    dep = _dep_of("admin", "qa_lead", "developer")
    user = _StubUser(role="qa_lead")
    assert await dep(user=user) is user


async def test_multi_role_allow_list_rejects_non_member() -> None:
    """require_role(admin, qa_lead, developer) rejects qa_engineer -> 403."""
    dep = _dep_of("admin", "qa_lead", "developer")
    user = _StubUser(role="qa_engineer")
    with pytest.raises(HTTPException) as exc:
        await dep(user=user)
    assert exc.value.status_code == 403


async def test_role_read_off_the_row_not_the_token() -> None:
    """Changing user.role flips the decision with NO token involvement (role-off-row, T-10-03/04)."""
    dep = _dep_of("admin")
    user = _StubUser(role="developer")
    with pytest.raises(HTTPException):
        await dep(user=user)
    # Simulate an admin role change taking effect on the next request — same dependency, new role.
    user.role = "admin"
    assert await dep(user=user) is user
