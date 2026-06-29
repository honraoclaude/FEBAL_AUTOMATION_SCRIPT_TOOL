"""DASH-06 search ROUTER — role gate + ES-down honest-503 graceful-degrade (Task 3).

In-process over the real FastAPI app via httpx ASGITransport (the test_traceability router
discipline) with the get_current_user dependency stubbed per role and the search query's ES client
monkeypatched to a FakeAsyncElasticsearch. NO running HTTP stack, NO `search` profile, NO keys.

Asserts:
  - the rbac.py matrix: admin/qa_lead/qa_engineer/developer → 200 with hits; unauthenticated → 401.
  - GRACEFUL-DEGRADE (T-10-20): when the ES client raises a ConnectionError, GET /api/search returns
    503 with the honest "Search is unavailable…" body (the main.py ESConnectionError handler) —
    NEVER an empty list pretending zero hits, NEVER an unhandled 500.

Run: cd apps/api && uv run python -m pytest tests/integration/test_search_degrade.py -x -q
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

from tests.fixtures.fake_es import FakeAsyncElasticsearch

pytestmark = [pytest.mark.integration]

_loop_module = pytest.mark.asyncio(loop_scope="module")


def _stub_user(role: str):
    def _dep():
        class _U:
            id = 1
            email = "u@example.com"

        u = _U()
        u.role = role
        return u

    return _dep


def _make_app(role: str | None):
    from app.core.security import get_current_user
    from app.main import app

    app.dependency_overrides.clear()
    if role is not None:
        app.dependency_overrides[get_current_user] = _stub_user(role)
    return app


def _patch_es(monkeypatch, es) -> None:
    """Point the search query seam at the injected fake (the lifespan get_es is not opened in-test)."""
    from app.services.search import query as search_query

    monkeypatch.setattr(search_query, "get_es", lambda: es)


@_loop_module
async def test_router_role_matrix_returns_hits(monkeypatch) -> None:
    """All four authenticated roles → 200 with hits; unauthenticated → 401 (rbac.py matrix)."""
    es = FakeAsyncElasticsearch()
    # seed one matching doc so a permitted search returns a hit (not just an empty 200)
    await es.index(
        index="executions",
        id="run-x:login",
        document={"run_id": "run-x", "flow_id": "login", "error_text": "login failed"},
    )
    _patch_es(monkeypatch, es)

    path = "/api/search?q=login"
    try:
        for role in ("admin", "qa_lead", "qa_engineer", "developer"):
            app = _make_app(role)
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(path)
            assert resp.status_code == 200, f"{role}: {resp.status_code} {resp.text}"
            body = resp.json()
            assert body["query"] == "login"
            assert body["count"] == 1
            assert body["hits"][0]["id"] == "run-x:login"
            assert "error_text" in body["hits"][0]["highlight"]

        app = _make_app(None)
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(path)
        assert resp.status_code == 401, resp.text
    finally:
        _make_app(None).dependency_overrides.clear()


@_loop_module
async def test_es_down_returns_honest_503(monkeypatch) -> None:
    """ES-down → 503 'Search is unavailable…' (the handler) — NEVER a fake empty list / a 500."""
    es = FakeAsyncElasticsearch(raising=True)  # every op raises elasticsearch ConnectionError
    _patch_es(monkeypatch, es)

    app = _make_app("admin")
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/search?q=anything")
        assert resp.status_code == 503, resp.text
        assert "unavailable" in resp.json()["detail"].lower()
    finally:
        _make_app(None).dependency_overrides.clear()
