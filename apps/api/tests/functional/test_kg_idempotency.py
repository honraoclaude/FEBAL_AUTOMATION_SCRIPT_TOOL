"""KG-03 idempotent fingerprint-MERGE + freshness proof (graph-marked, NO live_llm).

Deterministic re-run proof from RESEARCH lines 432-452: upsert the fixture page set at
now1, count + capture the first_seen map; upsert the SAME set at now2; assert counts
unchanged (~0 duplicates), first_seen immutable, every last_verified bumped to now2. Also
asserts the uniqueness constraint blocks a duplicate-fingerprint create.

Runs under graph_mode only (`python infra/scripts/graph_mode.py up`). Drives the writer
over a fixture node set — no browser, no LLM, no keys. The graph is cleared in setup so the
proof runs fresh (one-time key->fingerprint migration posture, RESEARCH Runtime State
Inventory: any pre-existing live Phase-4 graph is DETACH DELETE'd before the first Phase-5 run).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from neo4j import AsyncGraphDatabase
from neo4j.exceptions import ConstraintError

from app.services.kg import schema, writer

pytestmark = [pytest.mark.functional, pytest.mark.graph]

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "kg" / "pages.json"


def _host_bolt_uri() -> str:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    return uri.replace("://neo4j:", "://localhost:")


@pytest.fixture
async def kg_driver():
    """Short-lived host driver to the neo4j graph profile + a fresh-graph + constraints setup."""
    driver = AsyncGraphDatabase.driver(
        _host_bolt_uri(),
        auth=(
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "please-change"),
        ),
    )
    # Fresh graph: clear any pre-existing (incl. old Phase-4 key-keyed) graph (migration posture).
    async with driver.session() as s:
        await s.run("MATCH (n) DETACH DELETE n")
    await schema.ensure_constraints(driver)
    try:
        yield driver
    finally:
        async with driver.session() as s:
            await s.run("MATCH (n) DETACH DELETE n")
        await driver.close()


def _pages() -> list[dict]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))["pages"]


async def _count_pages(driver) -> int:
    async with driver.session() as s:
        rec = await (await s.run("MATCH (p:Page) RETURN count(p) AS n")).single()
    return int(rec["n"])


async def _freshness_maps(driver) -> tuple[dict, dict]:
    async with driver.session() as s:
        result = await s.run(
            "MATCH (p:Page) RETURN p.fingerprint AS fp, p.first_seen AS fs, p.last_verified AS lv"
        )
        first_seen, last_verified = {}, {}
        async for rec in result:
            first_seen[rec["fp"]] = rec["fs"]
            last_verified[rec["fp"]] = rec["lv"]
    return first_seen, last_verified


async def _upsert_all(driver, pages, now) -> None:
    for p in pages:
        await writer.upsert_page(
            fingerprint=p["fingerprint"],
            url=p["url"],
            title=p["title"],
            run_id=p["run_id"],
            screenshot_path=p.get("screenshot_path"),
            now=now,
            driver=driver,
        )


async def test_reexplore_is_idempotent(kg_driver) -> None:
    pages = _pages()
    now1 = "2026-06-19T10:00:00Z"
    await _upsert_all(kg_driver, pages, now1)
    count1 = await _count_pages(kg_driver)
    first_seen_1, _ = await _freshness_maps(kg_driver)

    now2 = "2026-06-19T11:00:00Z"
    await _upsert_all(kg_driver, pages, now2)  # SAME node set, second run
    count2 = await _count_pages(kg_driver)
    first_seen_2, last_verified_2 = await _freshness_maps(kg_driver)

    assert count2 == count1 == len(pages)          # ~0 duplicates (KG-03)
    assert first_seen_2 == first_seen_1            # first_seen immutable
    assert all(v == now1 for v in first_seen_2.values())  # first_seen frozen at creation
    assert all(v == now2 for v in last_verified_2.values())  # last_verified bumped


async def test_uniqueness_constraint_blocks_duplicate_fingerprint(kg_driver) -> None:
    pages = _pages()
    await _upsert_all(kg_driver, pages, "2026-06-19T10:00:00Z")
    fp = pages[0]["fingerprint"]
    # A raw CREATE (bypassing MERGE) of a second node with the same fingerprint MUST be
    # refused by the REQUIRE p.fingerprint IS UNIQUE constraint created in setup.
    with pytest.raises(ConstraintError):
        async with kg_driver.session() as s:
            await s.run("CREATE (p:Page {fingerprint:$fp})", fp=fp)
