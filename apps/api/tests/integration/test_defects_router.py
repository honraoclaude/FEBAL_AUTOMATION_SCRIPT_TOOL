"""/api/defects review API proof (JIRA-02 / T-09-16) — auth gate + list/detail/calibration/apply/reject.

In-process over the real app via httpx ASGITransport (no running stack — deterministic), the
test_heals_router discipline:

  - UNAUTH: every endpoint (list / detail / calibration / apply / reject) refuses an
    unauthenticated request -> 401 (the router-level Depends(get_current_user) gate, T-09-16).
  - AUTHED (get_current_user overridden to a stub user): seed Classification + Defect rows over
    the module SessionLocal, then
      * GET ?status=draft (+ ?class=) -> the drafts (status + class filters work, sort holds);
      * GET /{id} -> the detail incl. confidence_threshold + run_id-derived attachment refs;
      * GET /calibration -> the read-only numbers + the autonomy flag;
      * POST /{id}/apply with a FakeJira gateway -> applied + a FAKE-key + reports "create";
        a second apply on the same fingerprint reports "update" (dedup, no duplicate);
      * POST /{id}/reject -> rejected;
      * an unknown id -> 404;
      * apply with NO token configured -> the honest not-configured 400 (defect stays draft).

get_db is NOT overridden — the handlers use the real SessionLocal against Postgres (always-on),
mirroring test_heals_router. The Jira gateway is monkeypatched to a shared FakeJira (keyless).

Run: cd apps/api && uv run python -m pytest tests/integration/test_defects_router.py -q
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


async def _delete_run(run_id: str) -> None:
    conn = await asyncpg.connect(_host_dsn())
    try:
        await conn.execute("DELETE FROM defects WHERE run_id = $1", run_id)
        await conn.execute("DELETE FROM classifications WHERE run_id = $1", run_id)
    finally:
        await conn.close()


async def _reset_engine_pool() -> None:
    from app.db.session import engine

    await engine.dispose()


def _stub_user():
    class _U:
        id = 1
        email = "admin@example.com"

    return _U()


def _make_app_authed():
    from app.core.security import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = _stub_user
    return app


def _make_app_unauthed():
    from app.main import app

    app.dependency_overrides.clear()
    return app


async def _seed_defect(
    run_id: str, *, classification: str = "product_defect", confidence: int = 90, fp: str | None = None
) -> int:
    """Seed one draft Defect + its Classification (with a cited artifact) over the module engine."""
    from app.db.session import SessionLocal
    from app.models.defects import Classification, Defect
    from sqlalchemy import select

    fp = fp or uuid.uuid4().hex[:16]
    flow_id = "flow-0"
    async with SessionLocal() as db:
        db.add(
            Classification(
                run_id=run_id,
                flow_id=flow_id,
                classification=classification,
                confidence=confidence,
                evidence={
                    "error_text": "AssertionError: inventory not visible",
                    "infra_health": "up",
                    "artifacts": [{"kind": "screenshot", "path": f"{flow_id}/t/shot.png"}],
                    "heal_history": [],
                },
            )
        )
        db.add(
            Defect(
                run_id=run_id,
                flow_id=flow_id,
                classification=classification,
                confidence=confidence,
                fingerprint=fp,
                jira_label=f"fp-{fp}",
                jira_key=None,
                status="draft",
            )
        )
        await db.commit()
        # Look up by the unique fingerprint (multiple defects can share a run_id in one test).
        row = await db.scalar(select(Defect).where(Defect.fingerprint == fp))
        return row.id


# --- UNAUTH gate: every endpoint 401s (T-09-16, V4) -------------------------------------------

_UNAUTH = [
    ("get", "/api/defects"),
    ("get", "/api/defects?status=draft"),
    ("get", "/api/defects/calibration"),
    ("get", "/api/defects/1"),
    ("post", "/api/defects/1/apply"),
    ("post", "/api/defects/1/reject"),
]


@_loop_module
@pytest.mark.parametrize("method,path", _UNAUTH)
async def test_every_endpoint_requires_auth(method: str, path: str) -> None:
    """Every /api/defects endpoint refuses an unauthenticated request -> 401 (router-level gate)."""
    app = _make_app_unauthed()
    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get(path) if method == "get" else await c.post(path)
        assert resp.status_code == 401, f"{method} {path} should be 401, got {resp.status_code}"
    finally:
        app.dependency_overrides.clear()


# --- AUTHED lifecycle: list / detail / calibration / apply / reject / 404 ----------------------


@_loop_module
async def test_authed_list_detail_calibration(monkeypatch) -> None:
    """Authed: list (status+class filter+sort), detail (threshold+attachment refs), calibration."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "jira_confidence_threshold", 70)
    monkeypatch.setattr(settings, "jira_autonomous_enabled", False)

    run_id = f"defrouter-{uuid.uuid4().hex}"
    app = _make_app_authed()
    transport = ASGITransport(app=app)
    try:
        # A high-confidence product defect + a lower-confidence automation defect (same run).
        hi = await _seed_defect(run_id, classification="product_defect", confidence=95)
        lo = await _seed_defect(run_id, classification="automation", confidence=60)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            # list drafts -> both rows, sorted confidence-desc (hi before lo).
            resp = await c.get("/api/defects?status=draft")
            assert resp.status_code == 200, resp.text
            ids = [r["id"] for r in resp.json() if r["id"] in (hi, lo)]
            assert ids == [hi, lo]  # confidence-desc within drafts

            # class filter narrows to the automation row only.
            resp = await c.get("/api/defects?status=draft&class=automation")
            mine = [r for r in resp.json() if r["id"] in (hi, lo)]
            assert [r["id"] for r in mine] == [lo]
            assert mine[0]["classification"] == "automation"

            # detail -> the calibrated threshold + run-relative attachment refs (no raw paths).
            resp = await c.get(f"/api/defects/{hi}")
            assert resp.status_code == 200, resp.text
            detail = resp.json()
            assert detail["confidence_threshold"] == 70
            assert detail["attachments"] == [{"kind": "screenshot", "path": "flow-0/t/shot.png"}]
            assert detail["proposed_issue"]["enriched"] is False  # keyless -> deterministic prose
            assert detail["fingerprint"]

            # calibration -> the read-only numbers + the autonomy flag (honest nulls).
            resp = await c.get("/api/defects/calibration")
            assert resp.status_code == 200, resp.text
            cal = resp.json()
            assert cal["confidence_threshold"] == 70
            assert cal["autonomous_enabled"] is False
            assert cal["classification_accuracy"] is None  # not measured yet

            # unknown id -> 404.
            assert (await c.get("/api/defects/999999999")).status_code == 404
    finally:
        app.dependency_overrides.clear()
        await _delete_run(run_id)
        await _reset_engine_pool()


@_loop_module
async def test_authed_apply_reports_create_then_update(monkeypatch) -> None:
    """Apply files via FakeJira -> applied + FAKE-key + 'create'; a re-apply reports 'update'."""
    import app.routers.defects as defects_router
    from app.services.jira.fake import FakeJira

    fake = FakeJira()
    monkeypatch.setattr(defects_router, "_gateway", lambda: fake)

    run_id = f"defapply-{uuid.uuid4().hex}"
    app = _make_app_authed()
    transport = ASGITransport(app=app)
    try:
        did = await _seed_defect(run_id, fp="aaaa1111bbbb2222")
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            # apply -> CREATE.
            resp = await c.post(f"/api/defects/{did}/apply")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["status"] == "applied"
            assert body["jira_key"] == "FAKE-1"
            assert body["last_action"] == "create"
            assert len(fake.issues) == 1

            # re-apply (same fingerprint) -> UPDATE, never a duplicate.
            resp = await c.post(f"/api/defects/{did}/apply")
            assert resp.status_code == 200, resp.text
            assert resp.json()["last_action"] == "update"
            assert len(fake.issues) == 1
            assert len(fake.comments) == 1

            # unknown id -> 404.
            assert (await c.post("/api/defects/999999999/apply")).status_code == 404
    finally:
        app.dependency_overrides.clear()
        await _delete_run(run_id)
        await _reset_engine_pool()


@_loop_module
async def test_authed_reject_flips_status() -> None:
    """Reject -> status='rejected' (a flag flip; nothing was filed)."""
    run_id = f"defreject-{uuid.uuid4().hex}"
    app = _make_app_authed()
    transport = ASGITransport(app=app)
    try:
        did = await _seed_defect(run_id)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(f"/api/defects/{did}/reject")
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "rejected"
            assert (await c.post("/api/defects/999999999/reject")).status_code == 404
    finally:
        app.dependency_overrides.clear()
        await _delete_run(run_id)
        await _reset_engine_pool()


@_loop_module
async def test_apply_without_token_is_honest_not_configured(monkeypatch) -> None:
    """Apply with NO Jira token -> the honest not-configured 400; the defect stays a draft."""
    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.models.defects import Defect
    from sqlalchemy import select

    # Force the live gateway path (the default AtlassianJira) with no token configured.
    monkeypatch.setattr(settings, "jira_url", None)
    monkeypatch.setattr(settings, "jira_email", None)
    monkeypatch.setattr(settings, "jira_api_token", None)

    run_id = f"defnotok-{uuid.uuid4().hex}"
    app = _make_app_authed()
    transport = ASGITransport(app=app)
    try:
        did = await _seed_defect(run_id)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(f"/api/defects/{did}/apply")
            assert resp.status_code == 400, resp.text
            assert "not configured" in resp.json()["detail"].lower()
        # The defect stayed a draft (never a fabricated "applied").
        async with SessionLocal() as db:
            row = await db.scalar(select(Defect).where(Defect.id == did))
            assert row.status == "draft"
            assert row.jira_key is None
    finally:
        app.dependency_overrides.clear()
        await _delete_run(run_id)
        await _reset_engine_pool()
