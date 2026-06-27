"""Evidence gather + classify-over-evidence proof (DEF-02) — seeded rows, keyless.

Drives gather_evidence + classify_failure over SEEDED TestResult / HealAudit / TestArtifact rows
(the in-process module-level SessionLocal asyncpg-pool pattern from test_heal_stats/test_heal_ingest)
and asserts the join assembles the cited evidence AND the resulting class/confidence/fingerprint for:

  - a seeded PRODUCT failure (assertion on a loaded page, no un-healed heal) -> product_defect;
  - a seeded un-healed-locator case (a fail_as_defect heal + a locator-miss error) -> automation.

It also asserts gather_evidence stitches the heal history + the artifact paths into the cited
snapshot (the classifications.evidence JSON the review UI renders), and that classify_failure
returns a stable 16-char fingerprint.

Marked `integration` (needs a real Postgres, like the heal-stats/ingest proofs); it rides the
default keyless gate (-m "not live_llm and not e2e and not graph and not functional" INCLUDES
integration). neo4j-OFF — a pure Postgres read. Cleans its seeded rows in teardown.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

pytestmark = [pytest.mark.integration]

_loop_module = pytest.mark.asyncio(loop_scope="module")


def _host_dsn() -> str:
    from app.core.config import settings

    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


async def _delete_run(run_id: str) -> None:
    conn = await asyncpg.connect(_host_dsn())
    try:
        await conn.execute("DELETE FROM test_results WHERE run_id = $1", run_id)
        await conn.execute("DELETE FROM test_artifacts WHERE run_id = $1", run_id)
        await conn.execute("DELETE FROM heal_audit WHERE run_id = $1", run_id)
    finally:
        await conn.close()


async def _reset_engine_pool() -> None:
    from app.db.session import engine

    await engine.dispose()


@_loop_module
async def test_gather_evidence_and_classify_product_failure() -> None:
    """A loaded-page assertion failure (no un-healed heal) classifies product_defect + cites it."""
    import re

    from app.db.session import SessionLocal
    from app.models.execution_history import TestArtifact, TestResult
    from app.services.defects.evidence import classify_failure, gather_evidence

    run_id = f"defect-prod-{uuid.uuid4().hex}"
    flow_id = "flow-0"
    try:
        async with SessionLocal() as db:
            db.add(
                TestResult(
                    run_id=run_id,
                    flow_id=flow_id,
                    verdict="product_failure",
                    attempts=3,
                    exit_codes=[1, 1, 1],
                    error_text="AssertionError: expect(.inventory_list).to_be_visible() failed (status 200)",
                    duration_ms=1234,
                )
            )
            db.add(
                TestArtifact(run_id=run_id, flow_id=flow_id, kind="screenshot", path=f"{flow_id}/t/shot.png")
            )
            await db.commit()

            ev = await gather_evidence(db, run_id, flow_id)
            assert ev["error_text"].startswith("AssertionError")
            assert ev["page_loaded"] is True
            assert ev["heal_outcome"] is None
            # the cited snapshot carries the artifact path + the verdict for the UI.
            assert ev["cited"]["verdict"] == "product_failure"
            assert ev["cited"]["artifacts"] == [{"kind": "screenshot", "path": f"{flow_id}/t/shot.png"}]

            decision = await classify_failure(db, run_id, flow_id)
            assert decision["classification"] == "product_defect"
            assert 0 <= decision["confidence"] <= 100
            assert decision["confidence"] >= 60
            assert re.fullmatch(r"[0-9a-f]{16}", decision["fingerprint"])
            assert decision["evidence"]["artifacts"][0]["kind"] == "screenshot"
    finally:
        await _delete_run(run_id)
        await _reset_engine_pool()


@_loop_module
async def test_gather_evidence_and_classify_unhealed_locator() -> None:
    """A fail_as_defect heal + a locator-miss error on a loaded page classifies automation."""
    from app.db.session import SessionLocal
    from app.models.execution_history import TestResult
    from app.models.heal_audit import HealAudit
    from app.services.defects.evidence import classify_failure, gather_evidence

    run_id = f"defect-auto-{uuid.uuid4().hex}"
    flow_id = "flow-1"
    try:
        async with SessionLocal() as db:
            db.add(
                TestResult(
                    run_id=run_id,
                    flow_id=flow_id,
                    verdict="product_failure",
                    attempts=3,
                    exit_codes=[1, 1, 1],
                    error_text="locator.click: element not found: add-to-cart-backpack",
                    duration_ms=900,
                )
            )
            db.add(
                HealAudit(
                    element_key="button_add_to_cart",
                    run_id=run_id,
                    flow_id=flow_id,
                    before_chain=[{"strategy": "data-testid", "value": "add-to-cart-backpack"}],
                    after_chain=None,  # fail_as_defect -> no healed chain
                    confidence=0.06,
                    outcome="fail_as_defect",
                    live_match_count=0,
                )
            )
            await db.commit()

            ev = await gather_evidence(db, run_id, flow_id)
            assert ev["heal_outcome"] == "fail_as_defect"
            assert ev["step"] == "button_add_to_cart"
            assert len(ev["cited"]["heal_history"]) == 1
            assert ev["cited"]["heal_history"][0]["outcome"] == "fail_as_defect"

            decision = await classify_failure(db, run_id, flow_id)
            assert decision["classification"] == "automation"
            assert decision["confidence"] >= 60
            assert decision["evidence"]["heal_history"][0]["element_key"] == "button_add_to_cart"
    finally:
        await _delete_run(run_id)
        await _reset_engine_pool()
