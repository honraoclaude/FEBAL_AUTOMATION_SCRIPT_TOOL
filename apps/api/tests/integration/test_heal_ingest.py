"""Heal-journal ingest integration proof (HEAL-03) — audit rows + page-object rewrite, keyless.

Drives ingest_heal_journal over a FIXTURE journal (auto_heal / quarantine / fail_as_defect) +
a planted page object under a run-scoped workspace, asserting the three side-effects:

  - one heal_audit row PER entry (before/after chain, confidence, outcome, live_match_count);
  - a page-object locator rewrite for the auto_heal entry ONLY (quarantine/fail stage in the
    audit row, no file rewrite — Open Q3);
  - the element_key -> owning page module resolution (MED-3 strategy (a): scan pages/*.py for the
    `self.<attr> = page.locator(` line);
  - parse_heal_journal tolerates a malformed/oversized journal (skips bad entries, never raises);
  - the KG write-back is best-effort: a driver that RAISES does not crash the ingest (the audit
    row + rewrite still persist) — T-08-14.

Keyless, neo4j-OFF (driver=None -> the write-back's lazy kg/writer call hits get_neo4j() which is
caught best-effort; an explicit raising driver proves the catch). Uses the module-level
SessionLocal engine (asyncpg pool, loop-bound — disposed in teardown, mirroring
test_artifact_capture).
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import asyncpg
import pytest

from app.core.workspaces import run_dir, workspaces_root
from app.services.healing.ingest import parse_heal_journal

# ingest_heal_journal writes through the module-level SQLAlchemy engine (asyncpg pool bound to the
# running loop). The async DB tests share ONE module-scoped loop so the pool stays valid across
# them (the asyncio mark is applied per-async-test below; the pure parse tests stay sync).
pytestmark = [pytest.mark.integration]

_loop_module = pytest.mark.asyncio(loop_scope="module")

_PAGE_OBJECT = '''\
"""Page Object: InventoryPage (AUTO-GENERATED)."""

from playwright.sync_api import Page, expect


class InventoryPage:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.button_add_to_cart = page.locator("add-to-cart-sauce-labs-backpack")
        self.input_username = page.locator("user-name")
'''


def _host_dsn() -> str:
    from app.core.config import settings

    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


async def _fetch_audits(run_id: str) -> list[dict]:
    conn = await asyncpg.connect(_host_dsn())
    try:
        rows = await conn.fetch(
            "SELECT element_key, run_id, flow_id, before_chain, after_chain, confidence, "
            "outcome, live_match_count FROM heal_audit WHERE run_id = $1 ORDER BY id",
            run_id,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def _reset_engine_pool() -> None:
    from app.db.session import engine

    await engine.dispose()


def _plant(run_id: str, flow_id: str, *, journal: list) -> tuple[Path, Path]:
    """Plant pages/<module>.py + a per-flow heal-journal.json under run-scoped workspaces."""
    root = run_dir(run_id, create=True)
    project_root = root / "target"
    pages_dir = project_root / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    (pages_dir / "inventory_page.py").write_text(_PAGE_OBJECT, encoding="utf-8")

    journal_dir = root / flow_id
    journal_dir.mkdir(parents=True, exist_ok=True)
    (journal_dir / "heal-journal.json").write_text(json.dumps(journal), encoding="utf-8")
    return project_root, journal_dir


@_loop_module
async def test_ingest_writes_audit_rows_and_rewrites_auto_heal_only() -> None:
    """auto_heal/quarantine/fail -> 3 audit rows; only the auto_heal rewrites its page object."""
    from app.services.healing.ingest import ingest_heal_journal
    from app.db.session import SessionLocal

    run_id = f"heal-ingest-{uuid.uuid4().hex}"
    flow_id = "flow-0"
    journal = [
        {
            "element_key": "button_add_to_cart",
            "before_chain": [{"strategy": "data-testid", "value": "add-to-cart-sauce-labs-backpack"}],
            "after_chain": [{"strategy": "data-testid", "value": "add-to-cart-btn-healed"}],
            "confidence": 0.91,
            "outcome": "auto_heal",
            "flow_id": flow_id,
            "live_match_count": 1,
            "ts": "2026-06-22T00:00:00Z",
        },
        {
            "element_key": "input_username",
            "before_chain": [{"strategy": "data-testid", "value": "user-name"}],
            "after_chain": [{"strategy": "data-testid", "value": "username-maybe"}],
            "confidence": 0.70,
            "outcome": "quarantine",
            "flow_id": flow_id,
            "live_match_count": 1,
            "ts": "2026-06-22T00:00:01Z",
        },
        {
            "element_key": "button_checkout",
            "before_chain": [{"strategy": "data-testid", "value": "checkout"}],
            "after_chain": [],
            "confidence": 0.10,
            "outcome": "fail_as_defect",
            "flow_id": flow_id,
            "live_match_count": 0,
            "ts": "2026-06-22T00:00:02Z",
        },
    ]
    project_root, journal_dir = _plant(run_id, flow_id, journal=journal)
    try:
        async with SessionLocal() as db:
            outcomes = await ingest_heal_journal(
                db,
                run_id,
                flow_id,
                project_root=project_root,
                journal_dir=journal_dir,
                driver=None,  # neo4j off -> KG write-back is best-effort caught (T-08-14)
            )
            await db.commit()

        assert outcomes == ["auto_heal", "quarantine", "fail_as_defect"]

        audits = await _fetch_audits(run_id)
        assert len(audits) == 3, f"expected one audit row per entry: {audits}"
        by_key = {a["element_key"]: a for a in audits}
        # before/after chains round-trip as JSON; fail_as_defect has a NULL after_chain.
        assert by_key["button_add_to_cart"]["outcome"] == "auto_heal"
        assert by_key["button_add_to_cart"]["after_chain"] is not None
        assert by_key["button_checkout"]["outcome"] == "fail_as_defect"
        assert by_key["button_checkout"]["after_chain"] is None
        assert abs(by_key["button_add_to_cart"]["confidence"] - 0.91) < 1e-6
        assert by_key["button_checkout"]["live_match_count"] == 0

        # The page object was rewritten for the auto_heal entry ONLY.
        rewritten = (project_root / "pages" / "inventory_page.py").read_text(encoding="utf-8")
        assert 'self.button_add_to_cart = page.locator("add-to-cart-btn-healed")' in rewritten
        # quarantine entry's element is UNTOUCHED (no rewrite for quarantine).
        assert 'self.input_username = page.locator("user-name")' in rewritten
        # the old auto_heal literal is gone.
        assert "add-to-cart-sauce-labs-backpack" not in rewritten
    finally:
        await _reset_engine_pool()
        shutil.rmtree(workspaces_root() / run_id, ignore_errors=True)


@_loop_module
async def test_ingest_best_effort_kg_writeback_with_raising_driver() -> None:
    """A driver that RAISES on write does not crash ingest — the audit row + rewrite still persist."""
    from app.services.healing.ingest import ingest_heal_journal
    from app.db.session import SessionLocal

    class _RaisingDriver:
        def session(self, *a, **k):  # noqa: ANN001, ANN002, ANN003
            raise RuntimeError("neo4j down")

    run_id = f"heal-kgfail-{uuid.uuid4().hex}"
    flow_id = "flow-0"
    journal = [
        {
            "element_key": "button_add_to_cart",
            "before_chain": [{"strategy": "data-testid", "value": "add-to-cart-sauce-labs-backpack"}],
            "after_chain": [{"strategy": "data-testid", "value": "healed-1"}],
            "confidence": 0.95,
            "outcome": "auto_heal",
            "flow_id": flow_id,
            "live_match_count": 1,
            "ts": "2026-06-22T00:00:00Z",
        }
    ]
    project_root, journal_dir = _plant(run_id, flow_id, journal=journal)
    try:
        async with SessionLocal() as db:
            outcomes = await ingest_heal_journal(
                db,
                run_id,
                flow_id,
                project_root=project_root,
                journal_dir=journal_dir,
                driver=_RaisingDriver(),  # raises -> must be caught best-effort
            )
            await db.commit()
        assert outcomes == ["auto_heal"]  # ingest completed despite the KG failure
        audits = await _fetch_audits(run_id)
        assert len(audits) == 1  # the audit row persisted
        rewritten = (project_root / "pages" / "inventory_page.py").read_text(encoding="utf-8")
        assert 'page.locator("healed-1")' in rewritten  # the rewrite persisted
    finally:
        await _reset_engine_pool()
        shutil.rmtree(workspaces_root() / run_id, ignore_errors=True)


def test_parse_tolerates_garbage_and_oversized_entries(tmp_path: Path) -> None:
    """A malformed/oversized/partly-garbage journal yields only the VALID entries (never raises)."""
    # Mixed payload: one valid, several garbage shapes.
    journal = [
        {"element_key": "ok", "outcome": "auto_heal", "confidence": 0.9, "live_match_count": 1},
        "not-a-dict",
        {"outcome": "auto_heal", "confidence": 0.9},  # missing element_key
        {"element_key": "x", "outcome": "not-a-real-outcome", "confidence": 0.9},  # bad outcome
        {"element_key": "y", "outcome": "auto_heal", "confidence": "high"},  # non-numeric conf
        {"element_key": "z" * 9999, "outcome": "auto_heal", "confidence": 0.9},  # oversized key
    ]
    (tmp_path / "heal-journal.json").write_text(json.dumps(journal), encoding="utf-8")
    valid = parse_heal_journal(tmp_path)
    assert [e["element_key"] for e in valid] == ["ok"]


def test_parse_missing_file_is_empty(tmp_path: Path) -> None:
    """No heal-journal.json -> empty list (a flow that never healed)."""
    assert parse_heal_journal(tmp_path) == []


def test_parse_non_list_payload_is_empty(tmp_path: Path) -> None:
    """A journal that isn't a JSON list -> empty (tolerant, never raises)."""
    (tmp_path / "heal-journal.json").write_text('{"not": "a list"}', encoding="utf-8")
    assert parse_heal_journal(tmp_path) == []
