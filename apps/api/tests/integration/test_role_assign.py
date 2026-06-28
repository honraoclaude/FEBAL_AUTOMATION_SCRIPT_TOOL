"""/api/users admin role-assignment proof (PLAT-04 / T-10-01/02) — auth gate + list/assign.

In-process over the real app via httpx ASGITransport (no running stack — deterministic), the
test_defects_router discipline. The router is gated `require_role("admin")`, which composes on
get_current_user; we override get_current_user to a stub user with a chosen role so the REAL
require_role logic decides allow vs 403 (we never stub require_role itself).

  - UNAUTH: every endpoint refuses an unauthenticated request -> 401 (get_current_user).
  - NON-ADMIN (developer): GET /api/users and POST /api/users/{id}/role both 403 (require_role).
  - ADMIN:
      * GET /api/users -> the user list with id/email/role;
      * POST /api/users/{id}/role {"role":"qa_lead"} -> sets the target's role; the list reflects it;
      * POST to change the ADMIN's OWN role -> 400 (self-demote/lockout guard, T-10-02); unchanged;
      * POST an invalid role string -> 422 (vocabulary validation);
      * POST to an unknown id -> 404.

get_db is NOT overridden — handlers use the real SessionLocal against Postgres (always-on),
mirroring test_defects_router. Seeded user rows are cleaned up by email after each test.

Run: cd apps/api && uv run python -m pytest tests/integration/test_role_assign.py -q
"""

from __future__ import annotations

import uuid

import asyncpg
import httpx
import pytest
from httpx import ASGITransport

pytestmark = [pytest.mark.integration]

_loop_module = pytest.mark.asyncio(loop_scope="module")


def _host_dsn() -> str:
    from app.core.config import settings

    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


async def _delete_users(emails: list[str]) -> None:
    conn = await asyncpg.connect(_host_dsn())
    try:
        await conn.execute("DELETE FROM users WHERE email = ANY($1::text[])", emails)
    finally:
        await conn.close()


async def _seed_user(email: str, role: str = "developer") -> int:
    """Seed one users row over the module engine; return its id."""
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.user import User

    async with SessionLocal() as db:
        db.add(User(email=email, password_hash=hash_password("x"), role=role))
        await db.commit()
        row = await db.scalar(select(User).where(User.email == email))
        return row.id


async def _role_of(user_id: int) -> str | None:
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.user import User

    async with SessionLocal() as db:
        return await db.scalar(select(User.role).where(User.id == user_id))


def _stub_user(uid: int, email: str, role: str):
    def _dep():
        class _U:
            id = uid
            email = ""
            role = ""

        u = _U()
        u.email = email
        u.role = role
        return u

    return _dep


def _make_app(*, override_user=None):
    from app.core.security import get_current_user
    from app.main import app

    app.dependency_overrides.clear()
    if override_user is not None:
        app.dependency_overrides[get_current_user] = override_user
    return app


# --- UNAUTH gate: every endpoint 401s ---------------------------------------------------------

_UNAUTH = [
    ("get", "/api/users"),
    ("post", "/api/users/1/role"),
]


@_loop_module
@pytest.mark.parametrize("method,path", _UNAUTH)
async def test_every_endpoint_requires_auth(method: str, path: str) -> None:
    """No /api/users endpoint is reachable unauthenticated -> 401 (router-level gate)."""
    app = _make_app(override_user=None)
    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(path) if method == "get" else await c.post(path, json={"role": "developer"})
        assert resp.status_code == 401, f"{method} {path} should be 401, got {resp.status_code}"
    finally:
        app.dependency_overrides.clear()


# --- NON-ADMIN: 403 on both list and assign (T-10-01) -----------------------------------------


@_loop_module
@pytest.mark.parametrize("method,path", _UNAUTH)
async def test_non_admin_gets_403(method: str, path: str) -> None:
    """A developer (non-admin) cannot reach any /api/users route -> 403 (require_role('admin'))."""
    app = _make_app(override_user=_stub_user(999, "dev@example.com", "developer"))
    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(path) if method == "get" else await c.post(path, json={"role": "developer"})
        assert resp.status_code == 403, f"{method} {path} should be 403, got {resp.status_code}"
    finally:
        app.dependency_overrides.clear()


# --- ADMIN lifecycle: list / assign / self-demote / invalid / 404 -----------------------------


@_loop_module
async def test_admin_list_and_assign_role() -> None:
    """Admin: GET /api/users lists rows; POST {id}/role sets the target's role; list reflects it."""
    target_email = f"rbac-target-{uuid.uuid4().hex}@example.com"
    admin_email = f"rbac-admin-{uuid.uuid4().hex}@example.com"
    try:
        admin_id = await _seed_user(admin_email, role="admin")
        target_id = await _seed_user(target_email, role="developer")
        app = _make_app(override_user=_stub_user(admin_id, admin_email, "admin"))
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            # list -> contains our seeded rows with id/email/role
            resp = await c.get("/api/users")
            assert resp.status_code == 200, resp.text
            by_id = {r["id"]: r for r in resp.json()}
            assert by_id[target_id]["email"] == target_email
            assert by_id[target_id]["role"] == "developer"

            # assign qa_lead to the target
            resp = await c.post(f"/api/users/{target_id}/role", json={"role": "qa_lead"})
            assert resp.status_code == 200, resp.text
            assert resp.json()["role"] == "qa_lead"

            # the change is persisted + reflected in the list
            assert await _role_of(target_id) == "qa_lead"
            resp = await c.get("/api/users")
            by_id = {r["id"]: r for r in resp.json()}
            assert by_id[target_id]["role"] == "qa_lead"
    finally:
        _make_app(override_user=None).dependency_overrides.clear()
        await _delete_users([admin_email, target_email])


@_loop_module
async def test_admin_self_demote_blocked_400() -> None:
    """An admin changing THEIR OWN role -> 400 (self-demote/lockout guard); role unchanged (T-10-02)."""
    admin_email = f"rbac-self-{uuid.uuid4().hex}@example.com"
    try:
        admin_id = await _seed_user(admin_email, role="admin")
        app = _make_app(override_user=_stub_user(admin_id, admin_email, "admin"))
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(f"/api/users/{admin_id}/role", json={"role": "developer"})
        assert resp.status_code == 400, resp.text
        assert await _role_of(admin_id) == "admin", "self-demote must NOT change the admin's role"
    finally:
        _make_app(override_user=None).dependency_overrides.clear()
        await _delete_users([admin_email])


@_loop_module
async def test_invalid_role_422() -> None:
    """POST with a role outside the four-role vocabulary -> 422; target role unchanged."""
    admin_email = f"rbac-admin2-{uuid.uuid4().hex}@example.com"
    target_email = f"rbac-target2-{uuid.uuid4().hex}@example.com"
    try:
        admin_id = await _seed_user(admin_email, role="admin")
        target_id = await _seed_user(target_email, role="developer")
        app = _make_app(override_user=_stub_user(admin_id, admin_email, "admin"))
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(f"/api/users/{target_id}/role", json={"role": "superuser"})
        assert resp.status_code == 422, resp.text
        assert await _role_of(target_id) == "developer"
    finally:
        _make_app(override_user=None).dependency_overrides.clear()
        await _delete_users([admin_email, target_email])


@_loop_module
async def test_unknown_target_404() -> None:
    """POST to an id that does not exist -> 404."""
    admin_email = f"rbac-admin3-{uuid.uuid4().hex}@example.com"
    try:
        admin_id = await _seed_user(admin_email, role="admin")
        app = _make_app(override_user=_stub_user(admin_id, admin_email, "admin"))
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/api/users/2147483000/role", json={"role": "qa_lead"})
        assert resp.status_code == 404, resp.text
    finally:
        _make_app(override_user=None).dependency_overrides.clear()
        await _delete_users([admin_email])
