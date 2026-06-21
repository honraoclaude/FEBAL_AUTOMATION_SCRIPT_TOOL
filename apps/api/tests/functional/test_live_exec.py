"""Live execution view proofs (EXEC-06 / D-06, W3) — against the running stack, keyless.

D-02: these hit the RUNNING API over live HTTP with the real Redis + Postgres (the SSE stream +
the current-counter reconnect snapshot). No neo4j, no broker, no provider keys.

Covers:
  - GET /api/executions/{run_id}/events re-emits per-test events published to `exec:{run_id}`
    IN ORDER (auth-gated; an unauthenticated subscribe is 401 — T-07-13).
  - A MID-RUN (re)subscribe FIRST yields a SNAPSHOT carrying the CURRENT counters built from the
    test_run row + the test_results aggregate (total/passed/failed/flaky + status running), NOT
    a terminal/empty snapshot (W3).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import asyncpg
import httpx
import pytest
import redis.asyncio as aioredis

pytestmark = pytest.mark.functional


def _host_dsn() -> str:
    """DATABASE_URL rewritten for host-side asyncpg (no +asyncpg, localhost not 'postgres')."""
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


def _host_redis_url() -> str:
    """REDIS_URL rewritten for host-side use (in-cluster 'redis' host -> localhost)."""
    return (
        os.environ["REDIS_URL"]
        .replace("@redis:", "@localhost:")
        .replace("//redis:", "//localhost:")
    )


async def _seed_run(
    *, run_id: str, total: int, passed: int, failed: int, flaky: int, status: str
) -> None:
    """Insert a test_run row + matching per-flow test_results so the snapshot has CURRENT state."""
    conn = await asyncpg.connect(_host_dsn())
    try:
        await conn.execute(
            "INSERT INTO test_runs (run_id, tier, status, total, passed, failed, flaky) "
            "VALUES ($1, 'smoke', $2, $3, $4, $5, $6)",
            run_id,
            status,
            total,
            passed,
            failed,
            flaky,
        )
        # Seed the per-flow results that the snapshot AGGREGATES (build_counters reads these).
        verdicts = (
            ["passed"] * passed
            + ["product_failure"] * failed
            + ["flaky"] * flaky
        )
        for i, verdict in enumerate(verdicts):
            await conn.execute(
                "INSERT INTO test_results (run_id, flow_id, verdict, attempts, exit_codes) "
                "VALUES ($1, $2, $3, 1, '[]'::json)",
                run_id,
                f"flow-{i}",
                verdict,
            )
    finally:
        await conn.close()


async def _cleanup_run(run_id: str) -> None:
    conn = await asyncpg.connect(_host_dsn())
    try:
        await conn.execute("DELETE FROM test_results WHERE run_id = $1", run_id)
        await conn.execute("DELETE FROM test_runs WHERE run_id = $1", run_id)
    finally:
        await conn.close()


async def test_events_stream_forwards_published_test_events_in_order(authed_client):
    """Subscribing to the exec SSE endpoint yields per-test events published to exec:{run_id}."""
    run_id = f"exec-sse-{uuid.uuid4().hex[:8]}"
    # No seeded run row -> no snapshot frame; we assert ONLY the forwarded live frames here.
    payloads = [
        {
            "run_id": run_id,
            "completed": i,
            "total": 3,
            "passed": i,
            "failed": 0,
            "flaky": 0,
            "elapsed_s": float(i),
            "status": "running" if i < 2 else "passed",
            "flow_id": f"flow-{i}",
            "test_id": f"flow-{i}",
            "test_name": f"flow-{i}",
            "test_status": "passed",
            "attempt": 1,
            "duration_ms": 1000 + i,
        }
        for i in range(3)
    ]

    received: list[dict] = []

    async def _consume(stream_ready: asyncio.Event) -> None:
        async with authed_client.stream(
            "GET", f"/api/executions/{run_id}/events", timeout=httpx.Timeout(30.0)
        ) as resp:
            assert resp.status_code == 200
            stream_ready.set()
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    data = line[len("data:") :].strip()
                    if not data:
                        continue
                    received.append(json.loads(data))
                    if len(received) >= len(payloads):
                        break

    stream_ready = asyncio.Event()
    consumer = asyncio.create_task(_consume(stream_ready))
    await asyncio.wait_for(stream_ready.wait(), timeout=10.0)
    await asyncio.sleep(0.3)  # let pubsub.subscribe complete inside the generator

    r = aioredis.from_url(_host_redis_url(), decode_responses=True)
    try:
        for p in payloads:
            await r.publish(f"exec:{run_id}", json.dumps(p))
            await asyncio.sleep(0.05)
    finally:
        await r.aclose()

    await asyncio.wait_for(consumer, timeout=15.0)

    assert len(received) == len(payloads)
    assert [ev["completed"] for ev in received] == [0, 1, 2]
    assert received[-1]["status"] == "passed"


async def test_mid_run_reconnect_snapshot_carries_current_counters(authed_client):
    """A mid-run (re)subscribe FIRST yields a snapshot with the CURRENT counters (W3, not terminal).

    Seeds a running run (total=4, passed=1, failed=0, flaky=1) and asserts the FIRST SSE frame
    is a snapshot carrying those CURRENT counters + status 'running' — built from the test_run
    row + the test_results aggregate, never an empty/terminal-only snapshot.
    """
    run_id = f"exec-snap-{uuid.uuid4().hex[:8]}"
    await _seed_run(
        run_id=run_id, total=4, passed=1, failed=0, flaky=1, status="running"
    )

    first: dict | None = None
    try:
        async with authed_client.stream(
            "GET", f"/api/executions/{run_id}/events", timeout=httpx.Timeout(15.0)
        ) as resp:
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    data = line[len("data:") :].strip()
                    if not data:
                        continue
                    first = json.loads(data)
                    break
    finally:
        await _cleanup_run(run_id)

    assert first is not None, "no snapshot frame received on reconnect"
    # The snapshot reflects the CURRENT counters from the row + aggregate (W3 — not terminal).
    assert first["status"] == "running", first
    assert first["total"] == 4, first
    assert first["passed"] == 1, first
    assert first["flaky"] == 1, first
    assert first["failed"] == 0, first
    # completed = passed + flaky + failed product results = 2 (1 passed + 1 flaky).
    assert first["completed"] == 2, first


async def test_events_stream_requires_auth(client):
    """An unauthenticated exec SSE subscribe is 401 (T-07-13 — EventSource rides the cookie only)."""
    r = await client.get(f"/api/executions/{uuid.uuid4().hex}/events")
    assert r.status_code == 401
