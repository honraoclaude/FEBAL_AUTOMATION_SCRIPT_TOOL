"""Defect pipeline draft-row + traceability + autonomy proof (JIRA-02/04) over FakeJira — keyless.

Drives run_defect_pipeline over SEEDED product-failure TestResult rows (the
test_classifier_evidence seeding/cleanup discipline) + an in-memory FakeJira, asserting:

  (a) a draft Defect row is ALWAYS created for a product-failure classification with the
      fingerprint + the run_id/flow_id test<->flow<->execution traceability links (JIRA-04),
      EVEN when autonomy is OFF (the link persists regardless — Pitfall 5);
  (b) with autonomy OFF the row stays status='draft' and FakeJira saw NO create;
  (c) with autonomy ON + above-threshold + product_defect the row flips to 'applied' with a
      FAKE-key and FakeJira recorded the create + the issue_link (the auto-file path);
  (d) a second identical-fingerprint run UPDATES (comment) — never a duplicate issue.

Marked `integration` (real Postgres, like the evidence proof); neo4j-OFF; keyless (FakeJira +
no provider key -> deterministic describe fallback). Cleans its seeded rows in teardown.

Run: cd apps/api && uv run python -m pytest tests/integration/test_defect_pipeline.py -q
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from app.core.config import settings

pytestmark = [pytest.mark.integration]

_loop_module = pytest.mark.asyncio(loop_scope="module")

# A loaded-page assertion failure -> product_defect (the test_classifier_evidence product case).
_PRODUCT_ERR = "AssertionError: expect(.inventory_list).to_be_visible() failed (status 200)"


def _host_dsn() -> str:
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


async def _delete_run(run_id: str) -> None:
    conn = await asyncpg.connect(_host_dsn())
    try:
        await conn.execute("DELETE FROM test_results WHERE run_id = $1", run_id)
        await conn.execute("DELETE FROM test_artifacts WHERE run_id = $1", run_id)
        await conn.execute("DELETE FROM heal_audit WHERE run_id = $1", run_id)
        await conn.execute("DELETE FROM defects WHERE run_id = $1", run_id)
        await conn.execute("DELETE FROM classifications WHERE run_id = $1", run_id)
    finally:
        await conn.close()


async def _reset_engine_pool() -> None:
    from app.db.session import engine

    await engine.dispose()


async def _seed_product_failure(run_id: str, flow_id: str) -> None:
    from app.db.session import SessionLocal
    from app.models.execution_history import TestArtifact, TestResult

    async with SessionLocal() as db:
        db.add(
            TestResult(
                run_id=run_id,
                flow_id=flow_id,
                verdict="product_failure",
                attempts=3,
                exit_codes=[1, 1, 1],
                error_text=_PRODUCT_ERR,
                duration_ms=1234,
            )
        )
        db.add(
            TestArtifact(
                run_id=run_id, flow_id=flow_id, kind="screenshot", path=f"{flow_id}/t/shot.png"
            )
        )
        await db.commit()


@_loop_module
async def test_draft_row_persists_with_traceability_when_autonomy_off(monkeypatch) -> None:
    """(a)+(b): autonomy OFF -> a draft Defect row with run_id/flow_id links; NO Jira create."""
    from app.db.session import SessionLocal
    from app.services.defects.pipeline import run_defect_pipeline
    from app.services.jira.fake import FakeJira

    monkeypatch.setattr(settings, "jira_autonomous_enabled", False)
    run_id = f"defpipe-off-{uuid.uuid4().hex}"
    flow_id = "flow-0"
    gw = FakeJira()
    try:
        await _seed_product_failure(run_id, flow_id)
        async with SessionLocal() as db:
            defect, counter = await run_defect_pipeline(
                db, run_id, flow_id, gateway=gw, run_counter=0
            )
        # The draft row IS the JIRA-04 traceability link (run_id + flow_id), persisted regardless.
        assert defect.status == "draft"
        assert defect.run_id == run_id
        assert defect.flow_id == flow_id
        assert defect.classification == "product_defect"
        assert defect.jira_key is None
        assert defect.fingerprint and defect.jira_label == f"fp-{defect.fingerprint}"
        # Autonomy OFF -> the cap counter never advanced and FakeJira saw NO create.
        assert counter == 0
        assert gw.issues == {}
    finally:
        await _delete_run(run_id)
        await _reset_engine_pool()


@_loop_module
async def test_autonomy_on_above_threshold_auto_files_with_link(monkeypatch) -> None:
    """(c): autonomy ON + above-threshold + product_defect -> applied with a FAKE-key + link."""
    from app.db.session import SessionLocal
    from app.services.defects.pipeline import run_defect_pipeline
    from app.services.jira.fake import FakeJira

    monkeypatch.setattr(settings, "jira_autonomous_enabled", True)
    monkeypatch.setattr(settings, "jira_confidence_threshold", 50)  # product case scores >= 60
    run_id = f"defpipe-on-{uuid.uuid4().hex}"
    flow_id = "flow-0"
    gw = FakeJira()
    try:
        await _seed_product_failure(run_id, flow_id)
        async with SessionLocal() as db:
            defect, counter = await run_defect_pipeline(
                db, run_id, flow_id, gateway=gw, run_counter=0
            )
        assert defect.status == "applied"
        assert defect.jira_key == "FAKE-1"
        assert counter == 1  # the auto-file consumed one cap slot
        # FakeJira recorded the create (with the fp-<hash> label) + the JIRA-04 issue link.
        assert len(gw.issues) == 1
        (issue,) = gw.issues.values()
        assert f"fp-{defect.fingerprint}" in issue["labels"]
        assert len(gw.links) == 1
    finally:
        await _delete_run(run_id)
        await _reset_engine_pool()


@_loop_module
async def test_second_identical_run_updates_never_duplicates(monkeypatch) -> None:
    """(d): a second identical-fingerprint run UPDATES the existing issue — never a duplicate."""
    from app.db.session import SessionLocal
    from app.services.defects.pipeline import run_defect_pipeline
    from app.services.jira.fake import FakeJira

    monkeypatch.setattr(settings, "jira_autonomous_enabled", True)
    monkeypatch.setattr(settings, "jira_confidence_threshold", 50)
    run_a = f"defpipe-dup-a-{uuid.uuid4().hex}"
    run_b = f"defpipe-dup-b-{uuid.uuid4().hex}"
    flow_id = "flow-0"
    gw = FakeJira()
    try:
        # Same error + same flow + same step -> same fingerprint across two runs (run_id is NOT
        # part of the fingerprint — D-05), so the second run dedups onto the first issue.
        await _seed_product_failure(run_a, flow_id)
        await _seed_product_failure(run_b, flow_id)
        async with SessionLocal() as db:
            d_a, counter = await run_defect_pipeline(db, run_a, flow_id, gateway=gw, run_counter=0)
        async with SessionLocal() as db:
            d_b, counter = await run_defect_pipeline(
                db, run_b, flow_id, gateway=gw, run_counter=counter
            )
        assert d_a.fingerprint == d_b.fingerprint  # identical failures -> identical fp
        assert len(gw.issues) == 1  # the second run UPDATED, never duplicated
        assert d_b.jira_key == d_a.jira_key
        assert counter == 1  # the update consumed NO additional cap slot
        assert len(gw.comments) == 1  # the recurrence comment
    finally:
        await _delete_run(run_a)
        await _delete_run(run_b)
        await _reset_engine_pool()
