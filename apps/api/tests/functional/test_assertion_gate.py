"""Functional (graph): the no-vacuous gate resolves against a SEEDED live Neo4j (GEN-03).

Seed a page + an element + a Form-[Updates]->BusinessEntity(Cart) via the single write path,
then assert resolve_then_refs: a resolvable ref passes and a non-existent ref is reported
unresolved. Runs under graph_mode only.
"""

from __future__ import annotations

import json
import os

import pytest
from neo4j import AsyncGraphDatabase

from app.services.gates.assertion_gate import resolve_then_refs
from app.services.kg import schema, writer

pytestmark = [pytest.mark.functional, pytest.mark.graph]

_NOW = "2026-06-20T13:00:00Z"
_PAGE_FP = "fp-inventory-gate"
_PAGE_URL = "http://saucedemo:80/inventory.html"
_ELEM_KEY = "fp-inventory-gate#button:Add to cart"
_FORM_KEY = "fp-inventory-gate#form:cart"
_ENTITY = "Cart"


def _host_bolt_uri() -> str:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    return uri.replace("://neo4j:", "://localhost:")


@pytest.fixture
async def kg_driver():
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
    try:
        yield driver
    finally:
        async with driver.session() as s:
            await s.run("MATCH (n) DETACH DELETE n")
        await driver.close()


async def _seed(driver) -> None:
    await writer.upsert_page(
        fingerprint=_PAGE_FP, url=_PAGE_URL, title="Products",
        run_id="gate-run", screenshot_path=None, now=_NOW, driver=driver,
    )
    await writer.upsert_element(
        key=_ELEM_KEY, role="button", label="Add to cart",
        chain_json=json.dumps([{"strategy": "role", "value": "button"}]),
        history_json="[]", run_id="gate-run", now=_NOW, driver=driver,
    )
    await writer.link_has_element(
        page_fingerprint=_PAGE_FP, element_key=_ELEM_KEY, run_id="gate-run", driver=driver,
    )
    await writer.upsert_form(key=_FORM_KEY, run_id="gate-run", now=_NOW, driver=driver)
    await writer.link_has_form(
        page_fingerprint=_PAGE_FP, form_key=_FORM_KEY, run_id="gate-run", driver=driver,
    )
    await writer.upsert_business_entity(
        name=_ENTITY, kind="collection", now=_NOW, driver=driver,
    )
    await writer.link_updates(
        form_key=_FORM_KEY, entity_name=_ENTITY, run_id="gate-run", driver=driver,
    )


async def test_resolvable_refs_pass_against_live_graph(kg_driver) -> None:
    await _seed(kg_driver)
    then_refs = [
        {"then_text": "cart updated", "kind": "edge",
         "ref": {"edge_type": schema.UPDATES, "entity": _ENTITY}},
        {"then_text": "button exists", "kind": "element",
         "ref": {"element_key": _ELEM_KEY}},
        {"then_text": "inventory shown", "kind": "page",
         "ref": {"page_fingerprint": _PAGE_FP}},
    ]
    assert await resolve_then_refs(then_refs, driver=kg_driver) == []


async def test_nonexistent_refs_are_unresolved(kg_driver) -> None:
    await _seed(kg_driver)
    then_refs = [
        {"then_text": "ghost page", "kind": "page",
         "ref": {"page_fingerprint": "fp-nope"}},
        {"then_text": "ghost element", "kind": "element",
         "ref": {"element_key": "fp-nope#x"}},
        {"then_text": "wrong entity", "kind": "edge",
         "ref": {"edge_type": schema.CREATES, "entity": _ENTITY}},
    ]
    unresolved = await resolve_then_refs(then_refs, driver=kg_driver)
    assert set(unresolved) == {"ghost page", "ghost element", "wrong entity"}
