"""Worker live-progress publish side (EXEC-06, D-06/D-07) — the execution Redis pub/sub seam.

Mirrors app/services/explorer/progress.py (the publish half of the Redis pub/sub → SSE seam),
but for the execution plane: per-test events go to the run-scoped channel `exec:{run_id}`
(the explorer uses `explore:{run_id}`). The SSE endpoint (routers/executions.py) re-emits each
frame to the live Executions view.

Each frame is a `shared.events.ExecutionProgressEvent` (Plan 04): the ABSOLUTE run counters
(completed/total/passed/failed/flaky — the live view reads the latest frame directly, never
deltas) PLUS the per-test delta (flow_id/test id/name/status/attempt/duration_ms). The run
counters are built from the test_runs row + the test_results aggregate (the SAME current-state
the SSE reconnect snapshot reads), so a published live frame and a reconnect snapshot agree.

PITFALLS note (carried from Phase 4): REUSE the SAME lifespan get_redis() client — NEVER
construct a second Redis client. A publish to a zero-subscriber channel is a no-op, not an error.

SC3: this module imports ONLY app.core.redis_client, the DB models, shared.events + stdlib — no
LLM/gateway/explorer.
"""

from __future__ import annotations

from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis
from app.models.execution_history import TestResult, TestRun
from shared.events import ExecutionProgressEvent


async def build_counters(db: AsyncSession, run_id: str) -> dict:
    """Build the ABSOLUTE run counters (completed/total/passed/failed/flaky/status) from the DB.

    Reads the test_runs row (for status + total) and AGGREGATES the per-flow test_results rows
    by verdict (passed/flaky/product_failure/aborted). This is the SINGLE source the live
    publish frame and the SSE reconnect snapshot both use, so they always agree. `total` falls
    back to the count of recorded results when the test_run row's total is still 0 (the row's
    counters are rolled up lazily). Returns plain values; never raises on a missing run.
    """
    run = await db.scalar(select(TestRun).where(TestRun.run_id == run_id))

    def _count(verdict: str) -> object:
        return func.sum(func.cast(TestResult.verdict == verdict, Integer))

    row = (
        await db.execute(
            select(
                func.count(TestResult.id),
                _count("passed"),
                _count("flaky"),
                _count("product_failure"),
            ).where(TestResult.run_id == run_id)
        )
    ).one()
    completed = int(row[0] or 0)
    passed = int(row[1] or 0)
    flaky = int(row[2] or 0)
    failed = int(row[3] or 0)

    total = int(run.total) if (run is not None and run.total) else completed
    status = run.status if run is not None else "running"
    return {
        "completed": completed,
        "total": total,
        "passed": passed,
        "failed": failed,
        "flaky": flaky,
        "status": status,
    }


async def publish_test_event(
    db: AsyncSession,
    run_id: str,
    *,
    flow_id: str,
    test_status: str,
    attempt: int,
    duration_ms: int | None = None,
    elapsed_s: float = 0.0,
    test_id: str | None = None,
    test_name: str | None = None,
) -> None:
    """Build + publish an ExecutionProgressEvent to the run-scoped channel `exec:{run_id}`.

    REUSES the shared lifespan client (get_redis()). The frame carries the ABSOLUTE run
    counters (built from the test_runs row + the test_results aggregate via build_counters) and
    the per-test delta for the single test this event is about. Best-effort: zero subscribers is
    a no-op.
    """
    counters = await build_counters(db, run_id)
    event = ExecutionProgressEvent(
        run_id=run_id,
        completed=counters["completed"],
        total=counters["total"],
        passed=counters["passed"],
        failed=counters["failed"],
        flaky=counters["flaky"],
        elapsed_s=float(elapsed_s),
        status=counters["status"],
        flow_id=flow_id,
        test_id=test_id or flow_id,
        test_name=test_name or flow_id,
        test_status=test_status,
        attempt=attempt,
        duration_ms=duration_ms,
    )
    await get_redis().publish(f"exec:{run_id}", event.model_dump_json())
