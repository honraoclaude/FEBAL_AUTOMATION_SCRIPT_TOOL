"""Execution-history query proofs (EXEC-05) — seeded rows, keyless, neo4j-off, no broker.

Seeds test_runs / test_results rows directly and asserts the three EXEC-05 aggregate queries:
  - pass_rate_trend(db): per-day sum(passed)/sum(total) over test_runs
  - durations_by_flow(db): avg/max duration_ms per flow over test_results
  - flaky_leaderboard(db): flow_ids ordered by flaky-verdict count desc

Plus the two run-surface reads the consolidated router uses:
  - list_runs(db): test_runs newest-first
  - get_run_status(db, run_id): the test_run row + its results summary; None for unknown.

Uses the module-level SQLAlchemy SessionLocal directly (a host-side session against the running
Postgres). No graph, no broker, no provider keys.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = [pytest.mark.functional, pytest.mark.asyncio(loop_scope="module")]


async def _dispose_engine() -> None:
    from app.db.session import engine

    await engine.dispose()


async def test_history_queries_over_seeded_rows() -> None:
    from app.db.session import SessionLocal
    from app.models.execution_history import TestResult, TestRun
    from app.services import exec_history

    tag = uuid.uuid4().hex[:8]
    run_a = f"hist-a-{tag}"
    run_b = f"hist-b-{tag}"
    flow_x = f"flow-x-{tag}"
    flow_y = f"flow-y-{tag}"

    try:
        async with SessionLocal() as db:
            db.add_all(
                [
                    TestRun(run_id=run_a, tier="smoke", status="passed", total=2, passed=2),
                    TestRun(run_id=run_b, tier="smoke", status="failed", total=2, passed=1),
                    # flow_x: one flaky + one passed -> flaky count 1
                    TestResult(run_id=run_a, flow_id=flow_x, verdict="passed",
                               attempts=1, exit_codes=[0], duration_ms=1000),
                    TestResult(run_id=run_b, flow_id=flow_x, verdict="flaky",
                               attempts=2, exit_codes=[1, 0], duration_ms=3000),
                    # flow_y: two flaky -> flaky count 2 (tops the leaderboard)
                    TestResult(run_id=run_a, flow_id=flow_y, verdict="flaky",
                               attempts=2, exit_codes=[1, 0], duration_ms=2000),
                    TestResult(run_id=run_b, flow_id=flow_y, verdict="flaky",
                               attempts=3, exit_codes=[1, 1, 0], duration_ms=4000),
                ]
            )
            await db.commit()

        async with SessionLocal() as db:
            # Durations: flow_y avg (2000+4000)/2 = 3000, max 4000; flow_x avg 2000, max 3000.
            durations = await exec_history.durations_by_flow(db)
            dmap = {d["flow_id"]: d for d in durations}
            assert dmap[flow_y]["avg_duration_ms"] == pytest.approx(3000, abs=1)
            assert dmap[flow_y]["max_duration_ms"] == 4000
            assert dmap[flow_x]["max_duration_ms"] == 3000

            # Flaky leaderboard: flow_y (2) ranks above flow_x (1).
            board = await exec_history.flaky_leaderboard(db)
            bmap = {b["flow_id"]: b["flaky_count"] for b in board}
            assert bmap[flow_y] == 2
            assert bmap[flow_x] == 1
            # flow_y must appear before flow_x (desc by count).
            order = [b["flow_id"] for b in board]
            assert order.index(flow_y) < order.index(flow_x)

            # Pass-rate trend: at least one day bucket, ratios within [0,1].
            trend = await exec_history.pass_rate_trend(db)
            assert trend, "pass_rate_trend returned no buckets"
            for point in trend:
                assert 0.0 <= point["pass_rate"] <= 1.0
    finally:
        await _dispose_engine()


async def test_list_runs_and_get_run_status() -> None:
    from app.db.session import SessionLocal
    from app.models.execution_history import TestResult, TestRun
    from app.services import exec_history

    tag = uuid.uuid4().hex[:8]
    run_id = f"status-{tag}"
    flow_id = f"flow-s-{tag}"
    try:
        async with SessionLocal() as db:
            db.add(TestRun(run_id=run_id, tier="smoke", status="running", total=1))
            db.add(
                TestResult(run_id=run_id, flow_id=flow_id, verdict="passed",
                           attempts=1, exit_codes=[0], duration_ms=500)
            )
            await db.commit()

        async with SessionLocal() as db:
            runs = await exec_history.list_runs(db)
            assert any(r.run_id == run_id for r in runs)

            status = await exec_history.get_run_status(db, run_id)
            assert status is not None
            assert status["run_id"] == run_id
            assert status["status"] == "running"
            assert any(res["flow_id"] == flow_id for res in status["results"])

            assert await exec_history.get_run_status(db, "no-such-run") is None
    finally:
        await _dispose_engine()
