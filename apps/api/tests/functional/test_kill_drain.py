"""Graceful kill / drain proofs (EXEC-06 / D-07) — against the running stack, keyless.

D-07 is a COOPERATIVE kill: a Redis flag the worker checks between tests + a queue purge — NO
SIGKILL, no orphaned Chromium. This module proves:

  - a flow whose run kill flag is set DRAINS to an `aborted` verdict (NOT product_failure) and
    runs NO subprocess (run_flow_job returns aborted immediately);
  - kill_run PURGES the durable exec.jobs queue of pending jobs (against the REAL queue-profile
    broker — W5: a purge must actually mean something);
  - the worker source contains NO os.kill / SIGKILL path (cooperative cancel only);
  - the MULTI-SEGMENT artifact route serves a trace/screenshot living in a per-test SUBDIR
    (workspaces/<run_id>/<flow_id>/<subdir>/trace.zip) with HTTP 200 (B2), and a `..`-bearing
    name is rejected 400 (T-07-14).

The drain test drives run_flow_job directly (loop-bound shared-client hygiene, mirroring
test_artifact_capture). The purge test uses the REAL broker. The artifact-route assertions use
the running API over live HTTP (authed_client). NO neo4j, no provider keys.
"""

from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path

import aio_pika
import pytest

from app.core.workspaces import run_dir

# The drain/purge tests drive run_flow_job / kill_run, which touch the module-level engine pool +
# Redis client bound to the running loop — they share a MODULE-scoped loop (mirrors
# test_artifact_capture). The artifact-route test uses function-scoped httpx fixtures
# (authed_client/client) and the sigkill grep is sync, so those carry the function-loop default;
# the marks are applied PER TEST below rather than module-wide to avoid mixing loop scopes.
pytestmark = pytest.mark.functional

_module_loop = pytest.mark.asyncio(loop_scope="module")

# The queue-profile broker is reached on the host at the published 5672.
_HOST_AMQP_URL = os.environ.get("AMQP_URL_HOST", "amqp://guest:guest@localhost:5672/")
# A minimal valid 1x1 PNG (a real artifact byte payload the route returns).
_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082"
)


def _host_redis_url() -> str:
    return (
        os.environ["REDIS_URL"]
        .replace("@redis:", "@localhost:")
        .replace("//redis:", "//localhost:")
    )


async def _reset_loop_bound_clients() -> None:
    """Release the loop-bound shared clients run_flow_job touches (engine pool + Redis client)."""
    import app.core.redis_client as redis_client
    from app.db.session import engine

    await engine.dispose()
    redis_client._client = None


@_module_loop
async def test_killed_flow_drains_to_aborted_no_subprocess() -> None:
    """With the kill flag set, run_flow_job returns an `aborted` verdict and runs NO subprocess."""
    import redis.asyncio as aioredis

    run_id = f"kill-{uuid.uuid4().hex}"
    flow_id = "flow-killed-0"

    # Set the cooperative kill flag for this run (the worker checks it BEFORE pulling work).
    r = aioredis.from_url(_host_redis_url(), decode_responses=True)
    try:
        await r.set(f"run:{run_id}:kill", "1")
    finally:
        await r.aclose()

    try:
        from app.services.worker.job import run_flow_job

        # No spec is planted: if the drain did NOT short-circuit, the subprocess would run the
        # (missing) spec and fail product_failure. An `aborted` verdict proves it drained first.
        verdict = await run_flow_job({"run_id": run_id, "flow_id": flow_id})
        assert verdict["verdict"] == "aborted", f"expected aborted, got {verdict}"
        assert verdict["attempts"] == 0, verdict

        # The aborted verdict is recorded as a TestResult (drained tests are kept in history).
        import asyncpg

        from tests.conftest import _host_dsn

        conn = await asyncpg.connect(_host_dsn())
        try:
            row = await conn.fetchrow(
                "SELECT verdict FROM test_results WHERE run_id = $1 AND flow_id = $2",
                run_id,
                flow_id,
            )
        finally:
            await conn.close()
        assert row is not None and row["verdict"] == "aborted", row
    finally:
        rr = aioredis.from_url(_host_redis_url(), decode_responses=True)
        try:
            await rr.delete(f"run:{run_id}:kill")
        finally:
            await rr.aclose()
        import asyncpg

        from tests.conftest import _host_dsn

        conn = await asyncpg.connect(_host_dsn())
        try:
            await conn.execute("DELETE FROM test_results WHERE run_id = $1", run_id)
        finally:
            await conn.close()
        await _reset_loop_bound_clients()


@_module_loop
async def test_kill_run_purges_the_queue() -> None:
    """kill_run purges the durable exec.jobs queue of pending jobs (W5 — REAL broker)."""
    from app.services import exec_service

    run_id = f"kill-purge-{uuid.uuid4().hex}"

    # Start from a clean queue, enqueue 3 pending jobs, then kill_run -> the queue must be empty.
    purge_conn = await aio_pika.connect_robust(_HOST_AMQP_URL)
    async with purge_conn:
        ch = await purge_conn.channel()
        q = await ch.declare_queue("exec.jobs", durable=True)
        await q.purge()

    try:
        await exec_service.enqueue_jobs(
            run_id, [{"flow_id": f"flow-{i}"} for i in range(3)]
        )

        # Confirm the jobs are actually queued before the kill (message count > 0).
        check_conn = await aio_pika.connect_robust(_HOST_AMQP_URL)
        async with check_conn:
            ch = await check_conn.channel()
            q = await ch.declare_queue("exec.jobs", durable=True, passive=True)
            assert q.declaration_result.message_count >= 3, (
                f"expected >=3 queued, got {q.declaration_result.message_count}"
            )

        # The kill purges the WHOLE queue (A6 — one run at a time).
        await exec_service.kill_run(run_id)

        after_conn = await aio_pika.connect_robust(_HOST_AMQP_URL)
        async with after_conn:
            ch = await after_conn.channel()
            q = await ch.declare_queue("exec.jobs", durable=True, passive=True)
            assert q.declaration_result.message_count == 0, (
                f"queue not purged: {q.declaration_result.message_count} messages remain"
            )
    finally:
        import redis.asyncio as aioredis

        rr = aioredis.from_url(_host_redis_url(), decode_responses=True)
        try:
            await rr.delete(f"run:{run_id}:kill")
        finally:
            await rr.aclose()
        await _reset_loop_bound_clients()


def test_no_sigkill_path_in_worker_or_exec_service() -> None:
    """The worker plane + exec_service contain NO os.kill / SIGKILL (cooperative cancel only)."""
    api_root = Path(__file__).resolve().parents[2]  # tests/functional -> tests -> api
    targets = [
        *(api_root / "app" / "services" / "worker").rglob("*.py"),
        api_root / "app" / "services" / "exec_service.py",
    ]
    forbidden = re.compile(r"\bos\.kill\b|\bSIGKILL\b")
    offenders: list[str] = []
    for path in targets:
        text = path.read_text(encoding="utf-8")
        # Strip line comments so a docstring/comment mentioning "no SIGKILL" never trips the gate.
        code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
        if forbidden.search(code):
            offenders.append(str(path))
    assert not offenders, f"forbidden os.kill/SIGKILL found in: {offenders}"


async def test_multisegment_artifact_route_serves_subdir_and_rejects_traversal(
    authed_client, client
) -> None:
    """A trace in a per-test SUBDIR is served 200 via the multi-segment route; `..` -> 400 (B2)."""
    run_id = f"art-{uuid.uuid4().hex[:8]}"
    flow_id = "flow-art-0"
    # Plant an artifact in a per-test subdir: workspaces/<run_id>/<flow_id>/<subdir>/trace.zip.
    subdir = "test-login-success"
    art_dir = run_dir(run_id, create=True) / flow_id / subdir
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "test-failed-1.png").write_bytes(_PNG_1x1)

    try:
        # 200 authed on the real file living in a SUBDIR (the multi-segment route resolves it).
        ok = await authed_client.get(
            f"/api/executions/{run_id}/artifacts/{flow_id}/{subdir}/test-failed-1.png"
        )
        assert ok.status_code == 200, ok.text
        assert ok.headers["content-type"].startswith("image/png")
        assert ok.content == _PNG_1x1

        # 401 unauthenticated (router gate — T-07-13).
        un = await client.get(
            f"/api/executions/{run_id}/artifacts/{flow_id}/{subdir}/test-failed-1.png"
        )
        assert un.status_code == 401

        # A `..`-bearing name is rejected 400 (never serves a file outside the run dir).
        trav = await authed_client.get(
            f"/api/executions/{run_id}/artifacts/{flow_id}/..%2f..%2f.env"
        )
        assert trav.status_code == 400, trav.text

        # A missing file in a valid path is 404.
        missing = await authed_client.get(
            f"/api/executions/{run_id}/artifacts/{flow_id}/{subdir}/nope.zip"
        )
        assert missing.status_code == 404
    finally:
        shutil.rmtree(run_dir(run_id), ignore_errors=True)
