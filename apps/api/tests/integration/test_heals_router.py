"""Quarantine review API proof (D-05 / HEAL-04) — auth gate + list/apply/reject/stats, keyless.

In-process over the real app via httpx ASGITransport (no running stack needed — deterministic):

  - UNAUTH: every endpoint (GET / apply / reject / stats) refuses an unauthenticated request ->
    401 (the router-level Depends(get_current_user) gate, T-08-18). No dependency override, so the
    real get_current_user runs and 401s on the absent cookie.
  - AUTHED (get_current_user overridden to a stub user): seed heal_audit rows over the module
    SessionLocal, then
      * GET ?status=quarantined -> the quarantined rows with before/after diff + confidence;
      * POST /{id}/apply -> outcome='applied' AND the deferred page-object rewrite happened
        (ast-valid: the page object's locator literal is the healed selector);
      * POST /{id}/reject -> reviewed_outcome='rejected' (the false-heal signal);
      * GET /stats -> the per-element aggregation;
      * an unknown heal_id -> 404.

get_db is NOT overridden — the handlers use the real SessionLocal against Postgres (always-on),
mirroring test_heal_ingest. Only get_current_user is overridden for the authed paths so the test
needs no live login round-trip. KG write-back is off (driver=None inside the router, best-effort).
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import asyncpg
import httpx
import pytest
from httpx import ASGITransport

from app.core.workspaces import run_dir, workspaces_root

pytestmark = [pytest.mark.integration]

_loop_module = pytest.mark.asyncio(loop_scope="module")

_PAGE_OBJECT_TMPL = '''\
"""Page Object: InventoryPage (AUTO-GENERATED)."""

from playwright.sync_api import Page, expect


class InventoryPage:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.{key} = page.locator("add-to-cart-sauce-labs-backpack")
'''


def _host_dsn() -> str:
    from app.core.config import settings

    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


async def _delete_run(run_id: str) -> None:
    conn = await asyncpg.connect(_host_dsn())
    try:
        await conn.execute("DELETE FROM heal_audit WHERE run_id = $1", run_id)
    finally:
        await conn.close()


async def _reset_engine_pool() -> None:
    from app.db.session import engine

    await engine.dispose()


def _stub_user():
    """A minimal stand-in for get_current_user (the gate only needs SOME user, not a DB row)."""

    class _U:
        id = 1
        email = "admin@example.com"

    return _U()


def _make_app_authed():
    """The real app with get_current_user overridden to a stub user (authed paths)."""
    from app.core.security import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = _stub_user
    return app


def _make_app_unauthed():
    """The real app with NO override — the real get_current_user runs and 401s without a cookie."""
    from app.main import app

    app.dependency_overrides.clear()
    return app


async def _seed_quarantine(run_id: str, element_key: str) -> int:
    """Seed one quarantined heal_audit row (staged after_chain) over the module engine; return id."""
    from app.db.session import SessionLocal
    from app.models.heal_audit import HealAudit
    from sqlalchemy import select

    async with SessionLocal() as db:
        db.add(
            HealAudit(
                element_key=element_key,
                run_id=run_id,
                flow_id="flow-0",
                before_chain=[{"strategy": "data-testid", "value": "add-to-cart-sauce-labs-backpack"}],
                after_chain=[{"strategy": "data-testid", "value": "add-to-cart-healed"}],
                confidence=0.72,
                outcome="quarantine",
                live_match_count=1,
            )
        )
        await db.commit()
        row = await db.scalar(select(HealAudit).where(HealAudit.run_id == run_id))
        return row.id


def _plant_pages(run_id: str, element_key: str) -> Path:
    """Plant pages/inventory_page.py under run_dir(run_id)/target/pages (the ingest layout)."""
    pages_dir = run_dir(run_id, create=True) / "target" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    (pages_dir / "inventory_page.py").write_text(
        _PAGE_OBJECT_TMPL.format(key=element_key), encoding="utf-8"
    )
    return pages_dir


# --- UNAUTH gate: every endpoint 401s (T-08-18, V4) --------------------------------------------

_UNAUTH = [
    ("get", "/api/heals"),
    ("get", "/api/heals?status=quarantine"),
    ("get", "/api/heals/stats"),
    ("post", "/api/heals/1/apply"),
    ("post", "/api/heals/1/reject"),
]


@_loop_module
@pytest.mark.parametrize("method,path", _UNAUTH)
async def test_every_endpoint_requires_auth(method: str, path: str) -> None:
    """Every /api/heals endpoint refuses an unauthenticated request -> 401 (router-level gate)."""
    app = _make_app_unauthed()
    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(path) if method == "get" else await c.post(path)
        assert resp.status_code == 401, f"{method} {path} should be 401, got {resp.status_code}"
    finally:
        app.dependency_overrides.clear()


# --- AUTHED lifecycle: list / apply / reject / stats / 404 ------------------------------------


@_loop_module
async def test_authed_list_apply_reject_stats() -> None:
    """Authed: list quarantined, apply (rewrite+outcome), reject (false-heal), stats, 404."""
    run_id = f"heals-router-{uuid.uuid4().hex}"
    key = f"button_add_to_cart_{uuid.uuid4().hex[:6]}"
    app = _make_app_authed()
    transport = ASGITransport(app=app)
    try:
        heal_id = await _seed_quarantine(run_id, key)
        _plant_pages(run_id, key)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            # list quarantine -> our row with the before/after diff + confidence (default status).
            resp = await c.get("/api/heals?status=quarantine")
            assert resp.status_code == 200, resp.text
            rows = resp.json()
            mine = [r for r in rows if r["id"] == heal_id]
            assert len(mine) == 1
            row = mine[0]
            assert row["outcome"] == "quarantine"
            assert row["confidence"] == 0.72
            assert row["before_chain"][0]["value"] == "add-to-cart-sauce-labs-backpack"
            assert row["after_chain"][0]["value"] == "add-to-cart-healed"
            assert row["reviewed_outcome"] is None

            # unknown id -> 404 (apply + reject).
            assert (await c.post("/api/heals/999999999/apply")).status_code == 404
            assert (await c.post("/api/heals/999999999/reject")).status_code == 404

            # apply -> outcome='applied' AND the page object was rewritten (ast-valid literal).
            resp = await c.post(f"/api/heals/{heal_id}/apply")
            assert resp.status_code == 200, resp.text
            assert resp.json()["outcome"] == "applied"
            rewritten = (
                run_dir(run_id) / "target" / "pages" / "inventory_page.py"
            ).read_text(encoding="utf-8")
            # The healed selector replaced the broken literal (deferred rewrite performed).
            assert "add-to-cart-healed" in rewritten
            assert "add-to-cart-sauce-labs-backpack" not in rewritten

            # reject -> reviewed_outcome='rejected' (false-heal signal). Seed a fresh quarantine row.
            reject_run = f"heals-reject-{uuid.uuid4().hex}"
            reject_id = await _seed_quarantine(reject_run, key)
            try:
                resp = await c.post(f"/api/heals/{reject_id}/reject")
                assert resp.status_code == 200, resp.text
                assert resp.json()["reviewed_outcome"] == "rejected"
            finally:
                await _delete_run(reject_run)

            # stats -> the per-element aggregation includes our applied element.
            resp = await c.get(f"/api/heals/stats?element={key}")
            assert resp.status_code == 200, resp.text
            stats = resp.json()
            assert all(s["element_key"] == key for s in stats)
    finally:
        app.dependency_overrides.clear()
        await _delete_run(run_id)
        shutil.rmtree(workspaces_root() / run_id, ignore_errors=True)
        await _reset_engine_pool()
