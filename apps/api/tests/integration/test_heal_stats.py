"""Per-element heal-stats aggregation proof (HEAL-04) — success-rate + false-heal-rate, keyless.

Seeds heal_audit rows for two elements over the module-level SessionLocal (the same in-process
asyncpg-pool pattern as test_heal_ingest), then asserts per_element_heal_stats computes:

  - heal_success_rate = (auto_heal + applied) / all attempts, per element;
  - false_heal_rate   = rejected-after-a-heal / auto_heal count, per element;
  - an element with zero heal attempts is ABSENT (no divide-by-zero — group_by over existing rows);
  - the optional element_key filter narrows to one element;
  - HealAuditResponse.model_validate parses a HealAudit ORM row (from_attributes).

Element A: 8 auto_heal + 1 applied + 1 rejected (the rejected row was an auto_heal an operator
flipped to reviewed_outcome='rejected') -> success = (8+1)/10 = 0.9; false_heal = 1/9 (9 auto_heal
rows, one later rejected). Element B: 1 quarantine + 1 fail_as_defect -> success = 0/2 = 0.0;
false_heal = 0.0 (no auto_heal denominator). A never-healed element 'never' is seeded with ZERO
rows and must be absent.

Keyless, neo4j-OFF — a pure Postgres read over heal_audit. Cleans its seeded rows in teardown.
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
        await conn.execute("DELETE FROM heal_audit WHERE run_id = $1", run_id)
    finally:
        await conn.close()


async def _reset_engine_pool() -> None:
    from app.db.session import engine

    await engine.dispose()


def _row(element_key: str, run_id: str, *, outcome: str, reviewed: str | None = None):
    from app.models.heal_audit import HealAudit

    return HealAudit(
        element_key=element_key,
        run_id=run_id,
        flow_id="flow-0",
        before_chain=[{"strategy": "data-testid", "value": "old"}],
        after_chain=[{"strategy": "data-testid", "value": "new"}] if outcome != "fail_as_defect" else None,
        confidence=0.9,
        outcome=outcome,
        live_match_count=1,
        reviewed_outcome=reviewed,
    )


@_loop_module
async def test_per_element_stats_success_and_false_heal_rates() -> None:
    """Element A: 8 auto_heal + 1 applied + 1 rejected -> success 0.9, false_heal 1/9; B: 0.0/0.0."""
    from app.db.session import SessionLocal
    from app.services.healing.stats import per_element_heal_stats

    run_id = f"heal-stats-{uuid.uuid4().hex}"
    key_a = f"a-{uuid.uuid4().hex[:8]}"
    key_b = f"b-{uuid.uuid4().hex[:8]}"
    try:
        async with SessionLocal() as db:
            # Element A: 8 plain auto_heal + 1 applied + 1 auto_heal that was later rejected.
            for _ in range(8):
                db.add(_row(key_a, run_id, outcome="auto_heal"))
            db.add(_row(key_a, run_id, outcome="applied"))
            db.add(_row(key_a, run_id, outcome="auto_heal", reviewed="rejected"))
            # Element B: a quarantine + a fail_as_defect (no auto_heal denominator).
            db.add(_row(key_b, run_id, outcome="quarantine"))
            db.add(_row(key_b, run_id, outcome="fail_as_defect"))
            await db.commit()

            stats = await per_element_heal_stats(db)
            by_key = {s["element_key"]: s for s in stats}

            assert key_a in by_key and key_b in by_key
            # 'never' (never seeded) must be absent — no divide-by-zero, no phantom rows.
            assert "never" not in by_key

            a = by_key[key_a]
            assert a["attempts"] == 10
            # (8 auto_heal + 1 applied) / 10 = 0.9
            assert abs(a["heal_success_rate"] - 0.9) < 1e-9
            # 1 rejected / 9 auto_heal = 0.111...
            assert abs(a["false_heal_rate"] - (1 / 9)) < 1e-9

            b = by_key[key_b]
            assert b["attempts"] == 2
            assert abs(b["heal_success_rate"] - 0.0) < 1e-9
            # zero auto_heal -> false_heal_rate guarded to 0.0 (no divide-by-zero)
            assert abs(b["false_heal_rate"] - 0.0) < 1e-9

            # The optional element_key filter narrows to one element.
            only_a = await per_element_heal_stats(db, element_key=key_a)
            assert [s["element_key"] for s in only_a] == [key_a]
    finally:
        await _delete_run(run_id)
        await _reset_engine_pool()


@_loop_module
async def test_heal_audit_response_parses_orm_row() -> None:
    """HealAuditResponse.model_validate reads a HealAudit ORM row (from_attributes diff source)."""
    from app.db.session import SessionLocal
    from app.models.heal_audit import HealAudit
    from app.schemas.heal import HealAuditResponse
    from sqlalchemy import select

    run_id = f"heal-resp-{uuid.uuid4().hex}"
    key = f"r-{uuid.uuid4().hex[:8]}"
    try:
        async with SessionLocal() as db:
            db.add(_row(key, run_id, outcome="quarantine"))
            await db.commit()
            row = await db.scalar(
                select(HealAudit).where(HealAudit.run_id == run_id)
            )
            assert row is not None
            resp = HealAuditResponse.model_validate(row)
            assert resp.element_key == key
            assert resp.outcome == "quarantine"
            assert resp.before_chain == [{"strategy": "data-testid", "value": "old"}]
            assert resp.after_chain == [{"strategy": "data-testid", "value": "new"}]
            assert resp.reviewed_outcome is None
    finally:
        await _delete_run(run_id)
        await _reset_engine_pool()
