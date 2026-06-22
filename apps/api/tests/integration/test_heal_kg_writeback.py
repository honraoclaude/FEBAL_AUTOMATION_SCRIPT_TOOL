"""KG Element-history write-back proof (HEAL-03, graph-marked) — the single-writer append.

Proves kg/writer.append_element_history appends the healed {history_json, chain_json} to an
EXISTING :Element via the single write path with a read-back assertion, using a short-lived
host-injected driver (the Phase-5 fixture-KG pattern). neo4j must be UP (run under graph_mode:
web stopped, neo4j started — given the 3GB cap). Off the default suite (graph marker).

  - seed an :Element with a stale chain;
  - append_element_history with a fresh merged history (explorer/locators.merge_locator_history);
  - read it back: history_json carries the {step, chain} snapshot; chain_json is the new top;
  - an UNKNOWN element key MATCHes nothing -> the read-back guard RAISES (a heal must target a
    known element — a 0-count write is never silent).
"""

from __future__ import annotations

import json
import os

import pytest
from neo4j import AsyncGraphDatabase

from app.services.explorer.locators import merge_locator_history
from app.services.kg import schema, writer

pytestmark = [pytest.mark.integration, pytest.mark.graph]


def _host_bolt_uri() -> str:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    return uri.replace("://neo4j:", "://localhost:")


@pytest.fixture
async def kg_driver():
    """Short-lived host driver against the neo4j graph profile + a fresh graph + constraints."""
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


async def test_append_element_history_appends_snapshot_via_single_writer(kg_driver) -> None:
    """A heal appends the new {step, chain} history + top chain to an existing :Element."""
    key = "button_add_to_cart"
    now = "2026-06-22T00:00:00Z"
    # Seed the element via the single writer (the crawl already knew it).
    stale_chain = [{"strategy": "data-testid", "value": "add-to-cart-sauce-labs-backpack"}]
    await writer.upsert_element(
        key=key,
        role="button",
        label="Add to cart",
        chain_json=json.dumps(stale_chain),
        history_json=json.dumps([{"step": 0, "chain": stale_chain}]),
        run_id="seed-run",
        now=now,
        driver=kg_driver,
    )

    # The heal: the healed top chain + the merged history.
    healed_chain = [{"strategy": "data-testid", "value": "add-to-cart-btn-healed"}]
    history = merge_locator_history(
        [{"step": 0, "chain": stale_chain}], healed_chain, step=1
    )
    rec = await writer.append_element_history(
        key=key,
        history_json=json.dumps(history),
        chain_json=json.dumps(healed_chain),
        now="2026-06-22T01:00:00Z",
        driver=kg_driver,
    )
    assert int(rec["n"]) == 1  # the read-back guard saw exactly one write

    # Read it back directly: the new top chain + the appended history snapshot.
    async with kg_driver.session() as s:
        result = await s.run(
            "MATCH (e:Element {key:$key}) "
            "RETURN e.chain_json AS chain_json, e.history_json AS history_json, "
            "e.last_verified AS last_verified",
            key=key,
        )
        row = await result.single()
    assert json.loads(row["chain_json"]) == healed_chain
    read_history = json.loads(row["history_json"])
    assert any(snap.get("step") == 1 and snap.get("chain") == healed_chain for snap in read_history)
    assert {snap.get("step") for snap in read_history} == {0, 1}  # prior snapshot retained
    assert row["last_verified"] == "2026-06-22T01:00:00Z"


async def test_append_unknown_element_key_raises_via_read_back_guard(kg_driver) -> None:
    """An append against an unknown element key MATCHes nothing -> the read-back guard RAISES."""
    with pytest.raises(RuntimeError):
        await writer.append_element_history(
            key="element_that_does_not_exist",
            history_json=json.dumps([]),
            chain_json=json.dumps([]),
            now="2026-06-22T01:00:00Z",
            driver=kg_driver,
        )
