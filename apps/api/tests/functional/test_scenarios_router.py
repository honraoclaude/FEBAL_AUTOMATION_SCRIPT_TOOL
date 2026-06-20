"""Scenario review-queue router proof (GEN-02 / D-01..D-04).

Three layers, mirroring test_kg_endpoints.py's auth/shape split:

1. UNAUTH (functional, NO graph): every scenarios endpoint returns 401 when the caller is
   unauthenticated (T-06-07 — router-level Depends(get_current_user)). Parametrized over every
   route + method; no seeded row needed (the auth gate runs before any handler).

2. NON-GRAPH lifecycle (functional, NO graph): seed a draft row over a host DB session, then
   - reject → status=rejected (rejecting runs NO gates, so no neo4j needed);
   - edit with MALFORMED Gherkin → 422 + the row is UNCHANGED (the lint gate fails BEFORE any
     no-vacuous Cypher, so this path needs no graph);
   - edit a non-existent id → 404.

3. GRAPH lifecycle (functional + graph): under graph_mode, seed a graph (a resolvable page) +
   a draft whose then_refs resolve against it, then prove the honest gate flow end-to-end:
   - GET detail → per-Then then_results carry resolved=True with no fabricated green;
   - edit with valid gherkin + resolvable refs → 200, edited=True, status stays draft;
   - edit introducing a VACUOUS Then → 422 + the row UNCHANGED;
   - approve → status=approved; list_approved (codegen's only source) returns it.

The non-graph lifecycle seeds DIRECTLY over a host SQLAlchemy session (the api container and the
host point at the same Postgres), reads back through the live API as the authed admin, then
cleans up the seeded rows — mirroring test_kg_endpoints' host-driver seed/read-back pattern.
"""

from __future__ import annotations

import json
import os

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.scenario import Scenario
from app.services import scenario_service

# --- Host DB seeding helpers -------------------------------------------------------------


def _host_async_dsn() -> str:
    """DATABASE_URL rewritten for a host-side asyncpg engine (localhost, not 'postgres')."""
    return os.environ["DATABASE_URL"].replace("@postgres:", "@localhost:")


_VALID_GHERKIN = (
    "Feature: Add to cart\n"
    "  Scenario: Add an item\n"
    "    Given the inventory page\n"
    "    When the user adds an item\n"
    "    Then the inventory page is shown\n"
)


async def _seed_scenario(*, then_refs: list, run_id: str, flow_id: str = "flow-0") -> int:
    """Insert a draft scenario row over a short-lived host engine; return its id."""
    engine = create_async_engine(_host_async_dsn())
    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sm() as db:
            row = await scenario_service.create_scenario(
                db,
                run_id=run_id,
                flow_id=flow_id,
                feature_name="Add to cart",
                gherkin_text=_VALID_GHERKIN,
                then_refs=then_refs,
            )
            return row.id
    finally:
        await engine.dispose()


async def _read_scenario(scenario_id: int) -> Scenario | None:
    engine = create_async_engine(_host_async_dsn())
    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sm() as db:
            return await scenario_service.get(db, scenario_id)
    finally:
        await engine.dispose()


async def _delete_scenario(scenario_id: int) -> None:
    engine = create_async_engine(_host_async_dsn())
    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sm() as db:
            row = await scenario_service.get(db, scenario_id)
            if row is not None:
                await db.delete(row)
                await db.commit()
    finally:
        await engine.dispose()


# --- Layer 1: UNAUTH 401 gate (functional, no graph) -------------------------------------

_UNAUTH_ENDPOINTS = [
    ("get", "/api/scenarios"),
    ("get", "/api/scenarios?status=all"),
    ("get", "/api/scenarios/1"),
    ("post", "/api/scenarios/1/edit"),
    ("post", "/api/scenarios/1/approve"),
    ("post", "/api/scenarios/1/reject"),
    ("post", "/api/generate-scenarios"),
]


@pytest.mark.functional
@pytest.mark.parametrize("method,path", _UNAUTH_ENDPOINTS)
async def test_scenarios_endpoint_requires_auth(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    """Every scenarios endpoint is auth-gated — unauthenticated → 401 (T-06-07, V2/V4)."""
    # A valid-shaped body so a 401-vs-422 ordering quirk can never mask the gate.
    body = {"gherkin_text": "x", "then_refs": []} if "edit" in path else {"run_id": "x"}
    if method == "get":
        resp = await client.get(path)
    else:
        resp = await client.post(path, json=body)
    assert resp.status_code == 401, f"{method} {path} should be 401, got {resp.status_code}"


# --- Layer 2: NON-GRAPH lifecycle (functional, no graph) ----------------------------------

_ALL_RESOLVABLE = [
    {
        "then_text": "the inventory page is shown",
        "kind": "page",
        "ref": {"page_fingerprint": "fp-sc-inventory"},
    },
]


@pytest.mark.functional
async def test_reject_sets_status_rejected(authed_client: httpx.AsyncClient) -> None:
    """Reject sets status=rejected (no gates → no graph needed)."""
    sid = await _seed_scenario(then_refs=_ALL_RESOLVABLE, run_id="sc-reject")
    try:
        resp = await authed_client.post(f"/api/scenarios/{sid}/reject")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "rejected"
        row = await _read_scenario(sid)
        assert row is not None and row.status == "rejected"
    finally:
        await _delete_scenario(sid)


@pytest.mark.functional
async def test_edit_malformed_gherkin_422_and_unchanged(
    authed_client: httpx.AsyncClient,
) -> None:
    """Edit with malformed Gherkin → 422 (lint fails before no-vacuous) + the row is unchanged."""
    sid = await _seed_scenario(then_refs=_ALL_RESOLVABLE, run_id="sc-malformed")
    try:
        before = await _read_scenario(sid)
        assert before is not None
        resp = await authed_client.post(
            f"/api/scenarios/{sid}/edit",
            json={"gherkin_text": "not gherkin {{{", "then_refs": _ALL_RESOLVABLE},
        )
        assert resp.status_code == 422, resp.text
        after = await _read_scenario(sid)
        assert after is not None
        assert after.gherkin_text == before.gherkin_text
        assert after.status == "draft"
        assert after.edited is False
    finally:
        await _delete_scenario(sid)


@pytest.mark.functional
async def test_edit_missing_scenario_404(authed_client: httpx.AsyncClient) -> None:
    """Editing a non-existent scenario id → 404."""
    resp = await authed_client.post(
        "/api/scenarios/99999999/edit",
        json={"gherkin_text": _VALID_GHERKIN, "then_refs": _ALL_RESOLVABLE},
    )
    assert resp.status_code == 404, resp.text


# --- Layer 3: GRAPH lifecycle (functional + graph) ----------------------------------------

_GRAPH_FP = "fp-sc-inventory"
_GRAPH_URL = "http://saucedemo:80/inventory.html"
_GRAPH_THEN = [
    {"then_text": "the inventory page is shown", "kind": "page",
     "ref": {"page_fingerprint": _GRAPH_FP}},
]
_VACUOUS_THEN = [
    {"then_text": "a ghost page is shown", "kind": "page",
     "ref": {"page_fingerprint": "fp-does-not-exist"}},
]


def _host_bolt_uri() -> str:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    return uri.replace("://neo4j:", "://localhost:")


@pytest.fixture
async def seeded_page_graph():
    """Seed a single resolvable :Page via the single write path over a host Bolt driver."""
    from neo4j import AsyncGraphDatabase

    from app.services.kg import schema, writer

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
        fingerprint=_GRAPH_FP, url=_GRAPH_URL, title="Inventory",
        run_id="sc-run", screenshot_path=None,
        now="2026-06-20T14:00:00Z", driver=driver,
    )
    try:
        yield driver
    finally:
        async with driver.session() as s:
            await s.run("MATCH (n) DETACH DELETE n")
        await driver.close()


@pytest.mark.functional
@pytest.mark.graph
async def test_detail_then_results_honest(
    authed_client: httpx.AsyncClient, seeded_page_graph
) -> None:
    """GET /scenarios/{id} returns per-Then then_results reflecting the gate (no fabricated green)."""
    sid = await _seed_scenario(then_refs=_GRAPH_THEN, run_id="sc-detail")
    try:
        resp = await authed_client.get(f"/api/scenarios/{sid}")
        assert resp.status_code == 200, resp.text
        results = resp.json()["then_results"]
        assert len(results) == 1
        assert results[0]["resolved"] is True
        assert results[0]["kg_ref"]
    finally:
        await _delete_scenario(sid)


@pytest.mark.functional
@pytest.mark.graph
async def test_edit_valid_resolvable_200_edited_draft(
    authed_client: httpx.AsyncClient, seeded_page_graph
) -> None:
    """Edit with valid gherkin + resolvable refs → 200, edited=True, status stays draft."""
    sid = await _seed_scenario(then_refs=_GRAPH_THEN, run_id="sc-edit-ok")
    try:
        resp = await authed_client.post(
            f"/api/scenarios/{sid}/edit",
            json={"gherkin_text": _VALID_GHERKIN, "then_refs": _GRAPH_THEN},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["edited"] is True
        assert body["status"] == "draft"
        assert all(r["resolved"] for r in body["then_results"])
    finally:
        await _delete_scenario(sid)


@pytest.mark.functional
@pytest.mark.graph
async def test_edit_vacuous_then_422_and_unchanged(
    authed_client: httpx.AsyncClient, seeded_page_graph
) -> None:
    """Edit introducing a vacuous Then → 422 + the row is unchanged (D-04 gate integrity)."""
    sid = await _seed_scenario(then_refs=_GRAPH_THEN, run_id="sc-edit-vacuous")
    try:
        before = await _read_scenario(sid)
        assert before is not None
        resp = await authed_client.post(
            f"/api/scenarios/{sid}/edit",
            json={"gherkin_text": _VALID_GHERKIN, "then_refs": _VACUOUS_THEN},
        )
        assert resp.status_code == 422, resp.text
        after = await _read_scenario(sid)
        assert after is not None
        assert json.dumps(after.then_refs) == json.dumps(before.then_refs)
        assert after.status == "draft"
        assert after.edited is False
    finally:
        await _delete_scenario(sid)


@pytest.mark.functional
@pytest.mark.graph
async def test_approve_gates_pass_and_codegen_sees_only_approved(
    authed_client: httpx.AsyncClient, seeded_page_graph
) -> None:
    """Approve re-runs both gates and sets approved; list_approved returns only approved rows."""
    run_id = "sc-approve"
    approved_id = await _seed_scenario(then_refs=_GRAPH_THEN, run_id=run_id)
    draft_id = await _seed_scenario(then_refs=_GRAPH_THEN, run_id=run_id)
    try:
        resp = await authed_client.post(f"/api/scenarios/{approved_id}/approve")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "approved"

        # list_approved (codegen's ONLY source, D-01) returns the approved row, not the draft.
        engine = create_async_engine(_host_async_dsn())
        sm = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sm() as db:
                approved = await scenario_service.list_approved(db, run_id)
        finally:
            await engine.dispose()
        ids = {r.id for r in approved}
        assert approved_id in ids
        assert draft_id not in ids
    finally:
        await _delete_scenario(approved_id)
        await _delete_scenario(draft_id)
