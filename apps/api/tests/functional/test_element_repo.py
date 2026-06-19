"""KG-05 Element Repository read proof (graph-marked, NO live_llm).

Seed a page + an element (with a KNOWN prioritized locator chain + a step-stamped history) via
the single write path (kg/writer), then assert `reader.element_repository()` returns that
element's DESERIALIZED locator chain + history, keyed per element. Also exercises
`element_detail`, `list_pages`, and `graph_summary`. Runs under graph_mode only.
"""

from __future__ import annotations

import json
import os

import pytest
from neo4j import AsyncGraphDatabase

from app.services.kg import reader, schema, writer

pytestmark = [pytest.mark.functional, pytest.mark.graph]

_NOW = "2026-06-19T13:00:00Z"
_PAGE_FP = "fp-inventory-repo"
_ELEM_KEY = "fp-inventory-repo#button:Add to cart"
_CHAIN = [
    {"strategy": "data-testid", "value": "add-to-cart-sauce-labs-backpack"},
    {"strategy": "role", "value": "button", "name": "Add to cart"},
    {"strategy": "xpath", "value": "//button[1]"},
]
_HISTORY = [
    {"step": 1, "chain": [{"strategy": "data-testid", "value": "add-to-cart-sauce-labs-backpack"}]},
    {"step": 4, "chain": _CHAIN},
]


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
        fingerprint=_PAGE_FP, url="http://saucedemo:80/inventory.html",
        title="Swag Labs - Inventory", run_id="repo-run", screenshot_path=None,
        now=_NOW, driver=driver,
    )
    await writer.upsert_element(
        key=_ELEM_KEY, role="button", label="Add to cart",
        chain_json=json.dumps(_CHAIN), history_json=json.dumps(_HISTORY),
        run_id="repo-run", now=_NOW, driver=driver,
    )
    await writer.link_has_element(
        page_fingerprint=_PAGE_FP, element_key=_ELEM_KEY, run_id="repo-run", driver=driver,
    )


async def test_element_repository_returns_chain_and_history_per_element(kg_driver) -> None:
    await _seed(kg_driver)
    repo = await reader.element_repository(driver=kg_driver)
    assert len(repo) == 1
    el = repo[0]
    assert el["key"] == _ELEM_KEY
    assert el["page_fp"] == _PAGE_FP
    # The prioritized locator chain comes back DESERIALIZED (structured list, not a JSON string).
    assert el["chain"] == _CHAIN
    assert el["chain"][0]["strategy"] == "data-testid"  # healing priority preserved
    # The full step-stamped history is returned per element.
    assert el["history"] == _HISTORY
    assert [h["step"] for h in el["history"]] == [1, 4]


async def test_element_detail_returns_single_element(kg_driver) -> None:
    await _seed(kg_driver)
    el = await reader.element_detail(_ELEM_KEY, driver=kg_driver)
    assert el is not None
    assert el["chain"] == _CHAIN
    assert el["history"] == _HISTORY
    missing = await reader.element_detail("nope#nope", driver=kg_driver)
    assert missing is None


async def test_list_pages_and_summary(kg_driver) -> None:
    await _seed(kg_driver)
    pages = await reader.list_pages(driver=kg_driver)
    assert len(pages) == 1
    assert pages[0]["fingerprint"] == _PAGE_FP
    assert pages[0]["element_count"] == 1

    summary = await reader.graph_summary(driver=kg_driver)
    assert summary.get(schema.PAGE) == 1
    assert summary.get(schema.ELEMENT) == 1
