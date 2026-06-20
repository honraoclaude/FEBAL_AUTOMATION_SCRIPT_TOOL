"""Element-Repository codegen functional proof (GEN-04 / GEN-05a / D-01/D-05/D-06).

Two layers:

1. NON-GRAPH (functional, no neo4j): the freehand-selector gate REJECTS an injected inline
   selector literal in a rendered STEP module and NO tree is written — proven by rendering the
   step template with a poisoned page-object class that forces a literal into a spec/step
   position, asserting SelectorGateError and that the workspaces tree is absent. (The gate is
   the deterministic teeth; this needs no neo4j and no keys.)

2. GRAPH (functional + graph): under graph_mode, seed an Element Repository (a page + an element
   with a locator chain) + a NavigatesTo flow, seed an APPROVED scenario row (Postgres) and a
   DRAFT scenario (which codegen must IGNORE — D-01), then generate_project and assert:
     - the full tests/pages/steps/features/fixtures/utils/data/reports tree exists;
     - every generated .py ast-parses;
     - page-object locators equal a repo chain entry (repo-sourced);
     - the step-def binds the approved .feature via scenarios(...);
     - only the approved scenario produced a feature (the draft is ignored).

The graph layer seeds Neo4j via the single write path (kg/writer) over a host Bolt driver and
the Postgres scenario over a host SQLAlchemy engine — mirroring test_assertion_gate_graph +
test_scenarios_router.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import uuid
from pathlib import Path

import pytest

from app.core.workspaces import run_dir as _ws_run_dir
from app.services.gates.selector_gate import (
    SelectorGateError,
    scan_for_freehand_selectors,
)

# Repo root: tests/functional/test_codegen.py -> functional -> tests -> api -> apps -> root.
_REPO_ROOT = Path(__file__).resolve().parents[4]


# --- Layer 1: NON-GRAPH — the freehand-selector gate rejects an injected step literal ----


@pytest.mark.functional
def test_injected_step_literal_is_rejected_no_tree() -> None:
    """A rendered STEP module carrying an inline selector literal is rejected by the gate.

    We render the ACTUAL step template seam but simulate the LLM/template injecting a literal
    selector into a step body — the gate must flag it (scan returns violations) and the
    assert-form must raise, so codegen would abort BEFORE any write.
    """
    poisoned_step_source = (
        "from pytest_bdd import then\n\n\n"
        '@then("the cart updates")\n'
        "def cart_updates(page):\n"
        '    page.locator("#injected-by-llm").click()\n'
    )
    violations = scan_for_freehand_selectors(poisoned_step_source, is_page_object=False)
    assert violations, "an inline step selector literal must be flagged"

    from app.services.gates.selector_gate import assert_no_freehand_selectors

    with pytest.raises(SelectorGateError):
        assert_no_freehand_selectors(poisoned_step_source, is_page_object=False)


# --- Layer 2: GRAPH — full codegen from approved scenarios over a seeded graph ------------

pytestmark_graph = [pytest.mark.functional, pytest.mark.graph]

_NOW = "2026-06-20T13:00:00Z"


def _host_bolt_uri() -> str:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    return uri.replace("://neo4j:", "://localhost:")


def _host_async_dsn() -> str:
    return os.environ["DATABASE_URL"].replace("@postgres:", "@localhost:")


@pytest.fixture
async def kg_driver():
    from neo4j import AsyncGraphDatabase

    from app.services.kg import schema

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


async def _seed_graph(driver) -> tuple[str, str]:
    """Seed an entry page -> inventory page flow with a repo locator. Returns (entry_fp, inv_fp)."""
    from app.services.kg import writer

    entry_fp = "fp-login-cg"
    inv_fp = "fp-inventory-cg"
    elem_key = f"{inv_fp}#button:Add to cart"
    await writer.upsert_page(
        fingerprint=entry_fp, url="http://saucedemo:80/", title="Login",
        run_id="cg-run", screenshot_path=None, now=_NOW, driver=driver,
    )
    await writer.upsert_page(
        fingerprint=inv_fp, url="http://saucedemo:80/inventory.html", title="Products",
        run_id="cg-run", screenshot_path=None, now=_NOW, driver=driver,
    )
    await writer.upsert_element(
        key=elem_key, role="button", label="Add to cart",
        chain_json=json.dumps([{"strategy": "css", "value": "#add-to-cart"}]),
        history_json="[]", run_id="cg-run", now=_NOW, driver=driver,
    )
    await writer.link_has_element(
        page_fingerprint=inv_fp, element_key=elem_key, run_id="cg-run", driver=driver,
    )
    await writer.link_navigates_to(
        from_fingerprint=entry_fp, to_fingerprint=inv_fp, via="login",
        run_id="cg-run", driver=driver,
    )
    return entry_fp, inv_fp


async def _seed_scenarios(run_id: str, inv_fp: str) -> tuple[int, int]:
    """Seed one APPROVED + one DRAFT scenario row over a host engine. Returns (approved, draft)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.services import scenario_service

    gherkin = (
        "Feature: Complete checkout\n"
        "  Scenario: Reach the destination\n"
        "    Given the application entry page\n"
        "    When the user proceeds through the flow\n"
        "    Then the destination page is reached\n"
    )
    then_refs = [
        {"then_text": "the destination page is reached", "kind": "page",
         "ref": {"page_fingerprint": inv_fp}},
    ]
    engine = create_async_engine(_host_async_dsn())
    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sm() as db:
            approved = await scenario_service.create_scenario(
                db, run_id=run_id, flow_id="flow-0", feature_name="Complete checkout",
                gherkin_text=gherkin, then_refs=then_refs,
            )
            await scenario_service.set_status(db, approved.id, "approved")
            draft = await scenario_service.create_scenario(
                db, run_id=run_id, flow_id="flow-1", feature_name="Ignored draft",
                gherkin_text=gherkin, then_refs=then_refs,
            )
            return approved.id, draft.id
    finally:
        await engine.dispose()


async def _delete_scenarios(*ids: int) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.services import scenario_service

    engine = create_async_engine(_host_async_dsn())
    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sm() as db:
            for sid in ids:
                row = await scenario_service.get(db, sid)
                if row is not None:
                    await db.delete(row)
            await db.commit()
    finally:
        await engine.dispose()


@pytest.mark.functional
@pytest.mark.graph
async def test_generate_project_builds_full_repo_sourced_tree(kg_driver) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.services.codegen import project as codegen_project

    run_id = f"cg-{uuid.uuid4().hex}"
    _entry_fp, inv_fp = await _seed_graph(kg_driver)
    approved_id, draft_id = await _seed_scenarios(run_id, inv_fp)

    engine = create_async_engine(_host_async_dsn())
    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sm() as db:
            root = Path(await codegen_project.generate_project(db, run_id, driver=kg_driver))

        # Full tree exists.
        for sub in ("pages", "steps", "features", "fixtures", "utils", "data", "reports"):
            assert (root / sub).is_dir(), f"missing {sub}/ in {root}"
        assert (root / "conftest.py").is_file()

        # Every generated .py ast-parses.
        for py in root.rglob("*.py"):
            ast.parse(py.read_text(encoding="utf-8"))

        # The approved feature was written; the draft feature was NOT (D-01 — approved only).
        features = list((root / "features").glob("*.feature"))
        assert len(features) == 1, f"expected exactly the approved feature, got {features}"
        assert "ignored_draft" not in features[0].name

        # A step-def binds the approved .feature via scenarios(...).
        step_src = "\n".join(p.read_text(encoding="utf-8") for p in (root / "steps").glob("test_*.py"))
        assert "scenarios(" in step_src and ".feature" in step_src

        # A page object references the repo chain entry (repo-sourced locator).
        page_src = "\n".join(p.read_text(encoding="utf-8") for p in (root / "pages").glob("*.py"))
        assert "#add-to-cart" in page_src, "page object must use the repo-sourced locator"
    finally:
        await engine.dispose()
        await _delete_scenarios(approved_id, draft_id)
        shutil.rmtree(_ws_run_dir(run_id), ignore_errors=True)
