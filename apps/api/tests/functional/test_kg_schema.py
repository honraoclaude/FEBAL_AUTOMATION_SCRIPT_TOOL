"""KG-01 canonical schema proof (graph-marked, NO live_llm).

After upserting fixture pages + an element + a button + a business entity + a form and
linking them, assert the canonical labels (:Page/:Button/:Form/:Element/:BusinessEntity)
and edges (NavigatesTo/HAS_ELEMENT/HAS_BUTTON/HAS_FORM/Submits/Creates) all exist. Drives
the writer over the fixture — no browser, no LLM. Runs under graph_mode only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from neo4j import AsyncGraphDatabase

from app.services.kg import schema, writer

pytestmark = [pytest.mark.functional, pytest.mark.graph]

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "kg" / "pages.json"
_NOW = "2026-06-19T12:00:00Z"


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


def _data() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


async def _label_count(driver, label: str) -> int:
    async with driver.session() as s:
        rec = await (await s.run(f"MATCH (n:{label}) RETURN count(n) AS n")).single()
    return int(rec["n"])


async def _edge_count(driver, edge: str) -> int:
    async with driver.session() as s:
        rec = await (await s.run(f"MATCH ()-[r:{edge}]->() RETURN count(r) AS n")).single()
    return int(rec["n"])


async def _build_graph(driver) -> None:
    data = _data()
    for p in data["pages"]:
        await writer.upsert_page(
            fingerprint=p["fingerprint"], url=p["url"], title=p["title"],
            run_id=p["run_id"], screenshot_path=p.get("screenshot_path"), now=_NOW, driver=driver,
        )
    for nav in data["navigates_to"]:
        await writer.link_navigates_to(
            from_fingerprint=nav["from_fp"], to_fingerprint=nav["to_fp"],
            via=nav["via"], run_id=nav["run_id"], driver=driver,
        )
    for e in data["elements"]:
        await writer.upsert_element(
            key=e["key"], role=e["role"], label=e["label"], chain_json=e["chain_json"],
            history_json=e["history_json"], run_id=e["run_id"], now=_NOW, driver=driver,
        )
        await writer.link_has_element(
            page_fingerprint=e["page_fp"], element_key=e["key"], run_id=e["run_id"], driver=driver,
        )
    for b in data["buttons"]:
        await writer.upsert_button(
            key=b["key"], label=b["label"], role=b["role"], page_fingerprint=b["page_fp"],
            run_id=b["run_id"], now=_NOW, driver=driver,
        )
        await writer.link_has_button(
            page_fingerprint=b["page_fp"], button_key=b["key"], run_id=b["run_id"], driver=driver,
        )
    for f in data["forms"]:
        await writer.upsert_form(
            key=f["key"], validation_rules=f["validation_rules"], run_id=f["run_id"],
            now=_NOW, driver=driver,
        )
        await writer.link_has_form(
            page_fingerprint=f["page_fp"], form_key=f["key"], run_id=f["run_id"], driver=driver,
        )
    for be in data["business_entities"]:
        await writer.upsert_business_entity(
            name=be["name"], kind=be["kind"], now=_NOW, driver=driver,
        )
    for sub in data["submits"]:
        await writer.link_submits(
            page_fingerprint=sub["page_fp"], form_key=sub["form_key"],
            run_id=sub["run_id"], driver=driver,
        )
    for cr in data["creates"]:
        await writer.link_creates(
            form_key=cr["form_key"], entity_name=cr["entity_name"],
            run_id=cr["run_id"], driver=driver,
        )


async def test_canonical_labels_present(kg_driver) -> None:
    await _build_graph(kg_driver)
    assert await _label_count(kg_driver, schema.PAGE) >= 4
    assert await _label_count(kg_driver, schema.ELEMENT) >= 1
    assert await _label_count(kg_driver, schema.BUTTON) >= 1
    assert await _label_count(kg_driver, schema.FORM) >= 1
    assert await _label_count(kg_driver, schema.BUSINESS_ENTITY) >= 2


async def test_canonical_edges_present(kg_driver) -> None:
    await _build_graph(kg_driver)
    assert await _edge_count(kg_driver, schema.NAVIGATES_TO) >= 3
    assert await _edge_count(kg_driver, schema.HAS_ELEMENT) >= 1
    assert await _edge_count(kg_driver, schema.HAS_BUTTON) >= 1
    assert await _edge_count(kg_driver, schema.HAS_FORM) >= 1
    assert await _edge_count(kg_driver, schema.SUBMITS) >= 1
    assert await _edge_count(kg_driver, schema.CREATES) >= 1
