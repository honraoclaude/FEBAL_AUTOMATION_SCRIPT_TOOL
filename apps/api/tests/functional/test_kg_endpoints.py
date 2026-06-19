"""KG read-API proof (KG-02 / D-06) — auth gate (V4) + documented response shapes.

Two layers:

1. UNAUTH (functional, NO graph): every KG endpoint returns 401 when the caller is not
   authenticated (T-05-09 — router-level Depends(get_current_user); RBAC roles arrive
   Phase 10). These run against the live API without a seeded graph.

2. SHAPE (functional + graph): under graph_mode, seed a page + element + a 2-page flow via
   the single write path (kg/writer) over a host Bolt driver, then drive the LIVE API as the
   authed admin and assert the documented shapes — flows carry risk_score + risk_tier;
   coverage carries the honest `measured` flag; the element repository carries the locator
   chain + history; pages list the seeded page; the graph summary reports labels.

The graph tests seed neo4j directly (host driver) and read back through the API container
(both point at the same neo4j) — mirrors test_element_repo's host-driver seeding.
"""

from __future__ import annotations

import json
import os
from urllib.parse import quote

import httpx
import pytest
from neo4j import AsyncGraphDatabase

from app.services.kg import schema, writer

# Endpoints under the router-level auth gate — the 401 checks cover every one.
_UNAUTH_ENDPOINTS = [
    "/api/flows",
    "/api/flows/flow-0",
    "/api/coverage",
    "/api/graph",
    "/api/pages",
    "/api/pages/some-fingerprint",
    "/api/elements",
    "/api/elements/some-key",
]


# --- Layer 1: UNAUTH 401 gate (functional, no graph) -------------------------------------


@pytest.mark.functional
@pytest.mark.parametrize("path", _UNAUTH_ENDPOINTS)
async def test_kg_endpoint_requires_auth(client: httpx.AsyncClient, path: str) -> None:
    """Every KG read endpoint is auth-gated — unauthenticated → 401 (V4 / T-05-09)."""
    resp = await client.get(path)
    assert resp.status_code == 401, f"{path} should be 401 unauth, got {resp.status_code}"


@pytest.mark.functional
@pytest.mark.graph
async def test_flows_stub_removed_no_501(
    authed_client: httpx.AsyncClient, seeded_graph
) -> None:
    """The Phase-3 /flows + /coverage 501 stubs are gone — an authed GET is never 501.

    Graph-marked: /flows opens a Bolt read, so it needs neo4j reachable (graph_mode). The
    unauth 401 checks above already prove the stubs were removed (they were 501 before),
    so the surface-removal is also covered without a graph.
    """
    for path in ("/api/flows", "/api/coverage"):
        resp = await authed_client.get(path)
        assert resp.status_code != 501, f"{path} still returns 501 (stub not removed)"


# --- Layer 2: SHAPE under a seeded graph (functional + graph) -----------------------------

_NOW = "2026-06-19T14:00:00Z"
_LOGIN_FP = "fp-ep-login"
_INV_FP = "fp-ep-inventory"
_ELEM_KEY = "fp-ep-inventory#button:Add to cart"
_CHAIN = [
    {"strategy": "data-testid", "value": "add-to-cart"},
    {"strategy": "role", "value": "button", "name": "Add to cart"},
]
_HISTORY = [{"step": 1, "chain": _CHAIN}]


def _host_bolt_uri() -> str:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    return uri.replace("://neo4j:", "://localhost:")


@pytest.fixture
async def seeded_graph():
    """Seed a 2-page flow + an element via the single write path over a host Bolt driver."""
    driver = AsyncGraphDatabase.driver(
        _host_bolt_uri(),
        auth=(
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "please-change"),
        ),
    )
    async with driver.session() as s:
        await s.run("MATCH (n) DETACH DELETE n")
    await schema.ensure_constraints(driver)
    await writer.upsert_page(
        fingerprint=_LOGIN_FP, url="http://saucedemo:80/", title="Login",
        run_id="ep-run", screenshot_path=None, now=_NOW, driver=driver,
    )
    await writer.upsert_page(
        fingerprint=_INV_FP, url="http://saucedemo:80/inventory.html", title="Inventory",
        run_id="ep-run", screenshot_path=None, now=_NOW, driver=driver,
    )
    await writer.link_navigates_to(
        from_fingerprint=_LOGIN_FP, to_fingerprint=_INV_FP, via="Login",
        run_id="ep-run", driver=driver,
    )
    await writer.upsert_element(
        key=_ELEM_KEY, role="button", label="Add to cart",
        chain_json=json.dumps(_CHAIN), history_json=json.dumps(_HISTORY),
        run_id="ep-run", now=_NOW, driver=driver,
    )
    await writer.link_has_element(
        page_fingerprint=_INV_FP, element_key=_ELEM_KEY, run_id="ep-run", driver=driver,
    )
    try:
        yield driver
    finally:
        async with driver.session() as s:
            await s.run("MATCH (n) DETACH DELETE n")
        await driver.close()


@pytest.mark.functional
@pytest.mark.graph
async def test_flows_shape_carries_risk(
    authed_client: httpx.AsyncClient, seeded_graph
) -> None:
    """GET /flows returns flows each carrying risk_score (0-100) + risk_tier."""
    resp = await authed_client.get("/api/flows")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "flows" in body
    assert len(body["flows"]) >= 1
    flow = body["flows"][0]
    assert 0 <= flow["risk_score"] <= 100
    assert flow["risk_tier"] in {"high", "medium", "low"}
    assert flow["step_count"] >= 1
    # Default sort is risk descending.
    scores = [f["risk_score"] for f in body["flows"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.functional
@pytest.mark.graph
async def test_coverage_shape_carries_measured_flag(
    authed_client: httpx.AsyncClient, seeded_graph
) -> None:
    """GET /coverage carries the honest `measured` flag (never a fabricated percent)."""
    resp = await authed_client.get("/api/coverage")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "measured" in body
    assert isinstance(body["measured"], bool)
    assert 0.0 <= body["coverage_percent"] <= 100.0


@pytest.mark.functional
@pytest.mark.graph
async def test_pages_and_graph_shape(
    authed_client: httpx.AsyncClient, seeded_graph
) -> None:
    """GET /pages lists the seeded pages; GET /graph reports label counts."""
    resp = await authed_client.get("/api/pages")
    assert resp.status_code == 200, resp.text
    pages = resp.json()["pages"]
    fps = {p["fingerprint"] for p in pages}
    assert {_LOGIN_FP, _INV_FP} <= fps

    detail = await authed_client.get(f"/api/pages/{_INV_FP}")
    assert detail.status_code == 200, detail.text
    pd = detail.json()
    assert any(e["key"] == _ELEM_KEY for e in pd["elements"])

    g = await authed_client.get("/api/graph")
    assert g.status_code == 200, g.text
    gbody = g.json()
    assert gbody["discovered"] is True
    assert gbody["counts"].get("Page", 0) >= 2


@pytest.mark.functional
@pytest.mark.graph
async def test_elements_shape_carries_chain_and_history(
    authed_client: httpx.AsyncClient, seeded_graph
) -> None:
    """GET /elements returns the locator chain + history per element (KG-05)."""
    resp = await authed_client.get("/api/elements")
    assert resp.status_code == 200, resp.text
    elements = resp.json()["elements"]
    el = next(e for e in elements if e["key"] == _ELEM_KEY)
    assert el["locator_chain"][0]["strategy"] == "data-testid"
    assert el["page_fingerprint"] == _INV_FP
    assert len(el["locator_history"]) == 1
    assert el["locator_history"][0]["step"] == 1

    # The element key contains '#' (a URL fragment char) — it MUST be percent-encoded so the
    # whole key reaches the {key:path} route (the web client uses encodeURIComponent likewise).
    one = await authed_client.get(f"/api/elements/{quote(_ELEM_KEY, safe='')}")
    assert one.status_code == 200, one.text
    assert one.json()["key"] == _ELEM_KEY
