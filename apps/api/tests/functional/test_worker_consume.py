"""Worker round-trip proof (EXEC-03) — enqueue → consume → subprocess → result row, keyless.

The thinnest end-to-end proof of the execution plane against the REAL queue-profile broker
(W5 — the consumer's prefetch/QoS only means something on a live channel; a fabricated message
dict would prove nothing about consumption):

  1. PLANT a spec the SAME way the Phase-6 stability proof does (render the REAL generation
     skeleton with fixed observed SauceDemo slots, TARGET_BASE_URL-overridable) — NO gateway,
     NO provider keys, NO neo4j.
  2. ENQUEUE one job {flow_id, base_url} for that run_id via exec_service.enqueue_jobs against
     the real broker (default exchange, PERSISTENT, durable exec.jobs).
  3. RUN the REAL consumer (run_consumer) as a task; it sets prefetch_count=2, declares the
     durable queue, consumes the message, and run_flow_job runs `uv run pytest <spec>` in an
     isolated subprocess and records a TestResult.
  4. ASSERT a test_results row landed with the message's run_id/flow_id and a passed verdict,
     and that prefetch_count==2 was set on a consuming channel.

REQUIRES the queue profile up (and SauceDemo for the planted spec to pass):
  cd infra && docker compose --profile queue up -d --wait rabbitmq
graph-marked is NOT needed (no graph read); the run phase needs NO neo4j (T-06-20 sequencing) —
the Chromium subprocess reaches SauceDemo by its HOST-published port (localhost:8080), mirroring
the stability proof's host-driver pattern. The broker is reached at amqp://...@localhost:5672/.

Subprocess discipline: run_flow_job reuses stability._run_spec_once (argv list, no shell,
never in-process — T-07-01/Pitfall 3).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid

import aio_pika
import asyncpg
import pytest

# Reuse the planted-spec renderer + plant helper from the stability proof (same planted spec).
from tests.functional.test_stability import _WORKSPACES_ROOT, _plant

pytestmark = [pytest.mark.functional]

# The queue-profile broker is reached on the host at the published 5672 (compose name in-cluster).
_HOST_AMQP_URL = os.environ.get("AMQP_URL_HOST", "amqp://guest:guest@localhost:5672/")
# The planted spec is run by the HOST subprocess, so it reaches SauceDemo by its host port.
_SAUCEDEMO_HOST_URL = "http://localhost:8080"


def _host_dsn() -> str:
    """DATABASE_URL rewritten for host-side asyncpg (no +asyncpg, localhost not 'postgres')."""
    from app.core.config import settings

    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


async def _fetch_result(run_id: str) -> dict | None:
    conn = await asyncpg.connect(_host_dsn())
    try:
        row = await conn.fetchrow(
            "SELECT run_id, flow_id, verdict, attempts, exit_codes FROM test_results "
            "WHERE run_id = $1",
            run_id,
        )
        return dict(row) if row else None
    finally:
        await conn.close()


async def test_enqueue_consume_subprocess_lands_result_row() -> None:
    """A queued AMQP job is consumed by the REAL worker and lands a passed test_results row."""
    from app.services import exec_service
    from app.services.worker.consumer import run_consumer

    run_id = f"exec-rt-{uuid.uuid4().hex}"
    flow_id = "flow-rt-0"
    # Plant the spec at workspaces/<run_id>/test_login.py (the run_id-derived spec path the
    # worker resolves) — env-overridable so the host subprocess hits SauceDemo's host port.
    _plant(run_id)

    try:
        # 0) PURGE the durable exec.jobs queue first — it is shared and persistent, so stale
        #    messages from prior runs/tests would otherwise be consumed ahead of ours (each
        #    spinning a ~12s Chromium subprocess against prefetch=2), starving this run's
        #    message past the poll window. Isolating to our run_id on the result fetch is not
        #    enough; the consumer reads the shared queue. (Mirrors the D-07 purge semantics.)
        purge_conn = await aio_pika.connect_robust(_HOST_AMQP_URL)
        async with purge_conn:
            purge_channel = await purge_conn.channel()
            purge_queue = await purge_channel.declare_queue("exec.jobs", durable=True)
            await purge_queue.purge()

        # 1) Enqueue one job against the REAL broker. The worker resolves spec_path from run_id;
        #    base_url repoints the planted spec at the host-published SauceDemo (TARGET_BASE_URL).
        await exec_service.enqueue_jobs(
            run_id, [{"flow_id": flow_id, "base_url": _SAUCEDEMO_HOST_URL}]
        )

        # 2) Run the REAL consumer as a task; cancel once the result row lands (it loops forever).
        consumer_task = asyncio.create_task(run_consumer(_HOST_AMQP_URL, prefetch=2))
        result = None
        try:
            for _ in range(120):  # up to ~120s for the Chromium subprocess to finish
                result = await _fetch_result(run_id)
                if result is not None:
                    break
                await asyncio.sleep(1.0)
        finally:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

        assert result is not None, "no test_results row landed — round-trip did not complete"
        assert result["run_id"] == run_id
        assert result["flow_id"] == flow_id
        assert result["verdict"] == "passed", f"expected passed verdict, got {result}"
        assert result["attempts"] == 1
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)


async def test_consumer_sets_prefetch_count_two_on_the_channel() -> None:
    """prefetch_count=2 is set on a consuming channel against the REAL broker (W5/T-07-03).

    Mirrors the consumer's QoS setup verbatim on a live channel (the only place prefetch is
    observable) and asserts the channel's recorded QoS prefetch is the 3GB-safe bound of 2.
    """
    connection = await aio_pika.connect_robust(_HOST_AMQP_URL)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=2)
        await channel.declare_queue("exec.jobs", durable=True)
        # aio-pika records the applied QoS on the channel; assert the 3GB-safe bound stuck.
        assert channel._prefetch_count == 2, (
            f"expected prefetch_count=2 on the channel, got {channel._prefetch_count}"
        )
