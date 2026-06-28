"""DASH-04 lifecycle-coverage proof (distinct from kg/coverage.py) — graph-derived join.

`coverage_dash.coverage(db, *, driver=None)` mines the CURRENT graph (mocked here — keyless),
intersects discovered flow ids with the set of flows that have BOTH an approved Scenario AND a
passing TestResult, and returns the honest definition + the percentage + the per-flow drill-down.

These tests are fixture-testable WITHOUT neo4j: `mine_flows_from_neo4j` is monkeypatched to return
a fixed flow set, and the Postgres side is seeded over the real SessionLocal (Postgres is always-on,
the integration discipline). The graph-marked variant (live mining) runs under graph_mode.

Run: cd apps/api && uv run python -m pytest tests/unit/test_coverage_dash.py -x -q
"""

from __future__ import annotations

import inspect
import uuid

import asyncpg
import pytest
import pytest_asyncio

pytestmark = [pytest.mark.integration]

# All tests share ONE module-scoped event loop so the SQLAlchemy engine pool + asyncpg
# connections never cross a closed loop (the test_role_assign / test_defects_router discipline
# on Windows where each function-scoped loop otherwise tears connections down on a dead loop).
_loop_module = pytest.mark.asyncio(loop_scope="module")


def _host_dsn() -> str:
    from app.core.config import settings

    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def _reset_engine_pool():
    """Dispose the shared SQLAlchemy engine pool around this module so its asyncpg connections
    bind to THIS module's event loop, not a prior module's (closed) loop."""
    from app.db.session import engine

    await engine.dispose()
    yield
    await engine.dispose()


async def _delete_run(run_id: str) -> None:
    conn = await asyncpg.connect(_host_dsn())
    try:
        await conn.execute("DELETE FROM scenarios WHERE run_id = $1", run_id)
        await conn.execute("DELETE FROM test_results WHERE run_id = $1", run_id)
    finally:
        await conn.close()


async def _seed_scenario(run_id: str, flow_id: str, status: str) -> None:
    from app.db.session import SessionLocal
    from app.models.scenario import Scenario

    async with SessionLocal() as db:
        db.add(
            Scenario(
                run_id=run_id,
                flow_id=flow_id,
                feature_name=f"feat-{flow_id}",
                gherkin_text="Feature: x\n  Scenario: y\n    Then z",
                then_refs=[],
                status=status,
            )
        )
        await db.commit()


async def _seed_result(run_id: str, flow_id: str, verdict: str) -> None:
    from app.db.session import SessionLocal
    from app.models.execution_history import TestResult

    async with SessionLocal() as db:
        db.add(
            TestResult(
                run_id=run_id,
                flow_id=flow_id,
                verdict=verdict,
                attempts=1,
                exit_codes=[0 if verdict == "passed" else 1],
                duration_ms=10,
            )
        )
        await db.commit()


def _patch_mine(monkeypatch, n_flows: int) -> None:
    """Patch coverage_dash's mine_flows_from_neo4j to yield n positional flows (keyless)."""
    from app.services import coverage_dash

    async def _fake_mine(driver=None):  # noqa: ANN001, ARG001
        return {"flows": [{"id": f"flow-{i}"} for i in range(n_flows)], "bounded": True}

    monkeypatch.setattr(coverage_dash, "mine_flows_from_neo4j", _fake_mine)


# --- the core join: discovered ∩ approved ∩ passing -------------------------------------------


@_loop_module
async def test_coverage_intersection_and_percent(monkeypatch) -> None:
    """3 discovered, approved {0,1}, passing {0} -> covered {flow-0}, 33.3%."""
    from app.services import coverage_dash

    from app.db.session import SessionLocal

    run_id = f"covdash-{uuid.uuid4().hex}"
    try:
        _patch_mine(monkeypatch, 3)  # flow-0, flow-1, flow-2
        await _seed_scenario(run_id, "flow-0", "approved")
        await _seed_scenario(run_id, "flow-1", "approved")
        await _seed_result(run_id, "flow-0", "passed")

        async with SessionLocal() as db:
            result = await coverage_dash.coverage(db)

        assert result["total_discovered"] == 3
        assert result["covered"] == 1
        assert result["coverage_percent"] == 33.3
        assert result["covered_flow_ids"] == ["flow-0"]
    finally:
        await _delete_run(run_id)


@_loop_module
async def test_failing_only_flow_is_not_covered(monkeypatch) -> None:
    """A flow with an approved scenario but only a FAILING execution is NOT covered."""
    from app.services import coverage_dash

    from app.db.session import SessionLocal

    run_id = f"covdash-{uuid.uuid4().hex}"
    try:
        _patch_mine(monkeypatch, 1)  # flow-0 only
        await _seed_scenario(run_id, "flow-0", "approved")
        await _seed_result(run_id, "flow-0", "product_failure")  # not 'passed'

        async with SessionLocal() as db:
            result = await coverage_dash.coverage(db)

        assert result["covered"] == 0
        assert result["coverage_percent"] == 0.0
        assert result["covered_flow_ids"] == []
        # drill-down marks it approved-but-not-passing
        row = {r["flow_id"]: r for r in result["flows"]}["flow-0"]
        assert row["has_approved"] is True
        assert row["has_passing"] is False
        assert row["covered"] is False
    finally:
        await _delete_run(run_id)


@_loop_module
async def test_zero_discovered_is_zero_not_division_error(monkeypatch) -> None:
    """total_discovered=0 -> coverage_percent=0.0 (no division by zero)."""
    from app.services import coverage_dash

    from app.db.session import SessionLocal

    _patch_mine(monkeypatch, 0)
    async with SessionLocal() as db:
        result = await coverage_dash.coverage(db)
    assert result["total_discovered"] == 0
    assert result["coverage_percent"] == 0.0
    assert result["covered_flow_ids"] == []
    assert result["flows"] == []


# --- honesty: the definition ships in the payload; distinct from kg/coverage.py ----------------


@_loop_module
async def test_payload_carries_honest_definition(monkeypatch) -> None:
    """The 'definition' string is in the payload (never fabricated)."""
    from app.services import coverage_dash

    from app.db.session import SessionLocal

    _patch_mine(monkeypatch, 0)
    async with SessionLocal() as db:
        result = await coverage_dash.coverage(db)
    assert "definition" in result
    d = result["definition"].lower()
    assert "approved scenario" in d
    assert "passing execution" in d


def test_module_shares_no_code_path_with_kg_coverage() -> None:
    """DASH-04 is a SEPARATE metric — it imports NOTHING from kg/coverage.py (Pitfall 5)."""
    from app.services import coverage_dash

    src = inspect.getsource(coverage_dash)
    assert "kg.coverage" not in src
    assert "kg import coverage" not in src
    # distinct result shape: kg/coverage returns screens_total/screens_covered; DASH-04 does not.
    assert "screens_total" not in src
