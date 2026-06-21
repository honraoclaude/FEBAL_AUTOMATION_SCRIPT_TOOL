"""Execution-history queries (EXEC-05) — trends, durations, flaky leaderboard + run reads.

The read surface over the Phase-7 history tables (test_runs / test_results, migration 0007).
All queries use the SQLAlchemy 2.0 select/scalars style of run_service.list_runs — no raw SQL,
no ORM lazy loads. None of these touch the graph, the broker, or the LLM.

  - pass_rate_trend(db): per-day sum(passed)/sum(total) over test_runs (the pass-rate trend).
  - durations_by_flow(db): avg/max duration_ms per flow over test_results.
  - flaky_leaderboard(db): flow_id count where verdict='flaky', ordered desc (the leaderboard).
  - list_runs(db): the test_runs history, newest-first (the GET /api/executions surface).
  - get_run_status(db, run_id): a test_run row + its test_results summary; None -> 404.

These power the consolidated GET history/status routes in routers/executions.py and the
dashboard history UI (Phase 10).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_history import TestResult, TestRun


async def pass_rate_trend(db: AsyncSession) -> list[dict]:
    """Per-day pass-rate over test_runs: sum(passed)/sum(total), oldest day first.

    Buckets test_runs by the day of created_at (date_trunc), summing the run counters. A day
    with zero total contributes a 0.0 pass_rate (no division by zero). Returns a list of
    {day (ISO date str), pass_rate (0..1), total, passed}.
    """
    day = func.date_trunc("day", TestRun.created_at).label("day")
    total = func.sum(TestRun.total).label("total")
    passed = func.sum(TestRun.passed).label("passed")
    rows = (
        await db.execute(select(day, total, passed).group_by(day).order_by(day))
    ).all()
    trend: list[dict] = []
    for d, tot, pas in rows:
        tot_i = int(tot or 0)
        pas_i = int(pas or 0)
        trend.append(
            {
                "day": d.date().isoformat() if d is not None else None,
                "pass_rate": (pas_i / tot_i) if tot_i else 0.0,
                "total": tot_i,
                "passed": pas_i,
            }
        )
    return trend


async def durations_by_flow(db: AsyncSession) -> list[dict]:
    """Per-flow avg/max duration_ms over test_results (durations surface).

    Returns a list of {flow_id, avg_duration_ms (float|None), max_duration_ms (int|None)},
    ordered by flow_id. NULL durations are ignored by the SQL aggregates.
    """
    avg_d = func.avg(TestResult.duration_ms).label("avg_duration_ms")
    max_d = func.max(TestResult.duration_ms).label("max_duration_ms")
    rows = (
        await db.execute(
            select(TestResult.flow_id, avg_d, max_d)
            .group_by(TestResult.flow_id)
            .order_by(TestResult.flow_id)
        )
    ).all()
    return [
        {
            "flow_id": fid,
            "avg_duration_ms": float(avg) if avg is not None else None,
            "max_duration_ms": int(mx) if mx is not None else None,
        }
        for fid, avg, mx in rows
    ]


async def flaky_leaderboard(db: AsyncSession) -> list[dict]:
    """Flow ids ranked by flaky-verdict count, highest first (the flaky leaderboard).

    Counts test_results rows with verdict='flaky' per flow_id, ordered by that count desc
    (flow_id as a stable tiebreak). Returns {flow_id, flaky_count}. Flows with no flaky
    results do not appear.
    """
    flaky_count = func.count(TestResult.id).label("flaky_count")
    rows = (
        await db.execute(
            select(TestResult.flow_id, flaky_count)
            .where(TestResult.verdict == "flaky")
            .group_by(TestResult.flow_id)
            .order_by(flaky_count.desc(), TestResult.flow_id)
        )
    ).all()
    return [{"flow_id": fid, "flaky_count": int(cnt)} for fid, cnt in rows]


async def list_runs(db: AsyncSession) -> list[TestRun]:
    """The test_runs history, newest-first (the GET /api/executions list surface)."""
    return list(
        (await db.scalars(select(TestRun).order_by(TestRun.created_at.desc(), TestRun.id.desc()))).all()
    )


async def get_run_status(db: AsyncSession, run_id: str) -> dict | None:
    """A single run's status + its per-flow results summary; None when the run is unknown (404).

    Returns {run_id, tier, status, total, passed, failed, flaky, results: [...]} where each
    result is {flow_id, verdict, attempts, duration_ms}. The summary counters come straight off
    the TestRun row; the results list is the per-flow TestResult rows for the run.
    """
    run = await db.scalar(select(TestRun).where(TestRun.run_id == run_id))
    if run is None:
        return None

    # Per-flow results for this run — expose the rows verbatim (the run counters live on TestRun).
    result_rows = (
        await db.scalars(
            select(TestResult).where(TestResult.run_id == run_id).order_by(TestResult.id)
        )
    ).all()
    return {
        "run_id": run.run_id,
        "tier": run.tier,
        "status": run.status,
        "total": run.total,
        "passed": run.passed,
        "failed": run.failed,
        "flaky": run.flaky,
        "results": [
            {
                "flow_id": r.flow_id,
                "verdict": r.verdict,
                "attempts": r.attempts,
                "duration_ms": r.duration_ms,
            }
            for r in result_rows
        ],
    }
