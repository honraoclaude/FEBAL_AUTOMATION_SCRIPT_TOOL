"""Functional proofs for the EXPL-01 live-progress seam (04-04) — against the running stack.

D-02: these hit the RUNNING API over live HTTP with the real Redis (the SSE stream + the
screenshot route + auth gates). No neo4j needed (no `graph` marker) — the SSE test publishes
to Redis directly and asserts the stream forwards events in order.

Covers:
  - GET /api/explore/{run_id}/events streams events published to `explore:{run_id}` IN ORDER
    (auth-gated; an unauthenticated request is 401 — T-04-16).
  - GET /api/explore/{run_id}/screenshot/{name}: authed 200 on a real PNG; 401 unauth; a
    `..`/separator name is rejected 400/404 (T-04-17 path traversal — no file outside the
    workspace is served).
"""

import asyncio
import json
import os
import uuid
from pathlib import Path

import httpx
import pytest
import redis.asyncio as aioredis

pytestmark = pytest.mark.functional


def _host_redis_url() -> str:
    """REDIS_URL rewritten for host-side use (in-cluster 'redis' host -> localhost)."""
    return (
        os.environ["REDIS_URL"]
        .replace("@redis:", "@localhost:")
        .replace("//redis:", "//localhost:")
    )


def _workspaces_root() -> Path:
    """The host-side workspaces/ root (repo-root layout) the api also reads via a bind mount."""
    # tests/functional/ -> tests -> api -> apps -> repo root.
    return Path(__file__).resolve().parents[4] / "workspaces"


# ---- SSE stream -------------------------------------------------------------------------


async def test_events_stream_forwards_published_events_in_order(authed_client):
    """Subscribing to the SSE endpoint yields events published to explore:{run_id} in order."""
    run_id = f"sse-{uuid.uuid4().hex[:8]}"
    payloads = [
        {
            "run_id": run_id,
            "step": i,
            "pages_found": i,
            "actions_taken": i,
            "current_url": f"https://example.test/{i}",
            "current_title": f"P{i}",
            "screenshot_path": f"state-{i}.png",
            "feed_line": f"step {i}: chose [0] link",
            "cost_usd": 0.001 * i,
            "elapsed_s": float(i),
            "stop_reason": None if i < 3 else "saturation",
        }
        for i in range(4)
    ]

    received: list[dict] = []

    async def _consume(stream_ready: asyncio.Event) -> None:
        async with authed_client.stream(
            "GET", f"/api/explore/{run_id}/events", timeout=httpx.Timeout(30.0)
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
    # Wait until the SSE response is open (and thus subscribed) before publishing.
    await asyncio.wait_for(stream_ready.wait(), timeout=10.0)
    await asyncio.sleep(0.3)  # let pubsub.subscribe complete inside the generator

    r = aioredis.from_url(_host_redis_url(), decode_responses=True)
    try:
        for p in payloads:
            await r.publish(f"explore:{run_id}", json.dumps(p))
            await asyncio.sleep(0.05)
    finally:
        await r.aclose()

    await asyncio.wait_for(consumer, timeout=15.0)

    assert len(received) == len(payloads)
    assert [ev["step"] for ev in received] == [0, 1, 2, 3]
    assert received[-1]["stop_reason"] == "saturation"


async def test_events_stream_requires_auth(client):
    """An unauthenticated SSE subscribe is 401 (T-04-16 — EventSource rides the cookie only)."""
    r = await client.get(f"/api/explore/{uuid.uuid4().hex}/events")
    assert r.status_code == 401


# ---- Screenshot route (M-1) -------------------------------------------------------------

# A minimal valid 1x1 PNG (the bytes a screenshot route must return with image/png).
_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082"
)


async def test_screenshot_served_authed_and_traversal_rejected(authed_client, client):
    """Authed GET returns the PNG (200); unauth -> 401; a `..` name is rejected (400/404)."""
    run_id = f"shot-{uuid.uuid4().hex[:8]}"
    d = _workspaces_root() / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "state-0.png").write_bytes(_PNG_1x1)

    try:
        # 200 authed on the real file.
        ok = await authed_client.get(f"/api/explore/{run_id}/screenshot/state-0.png")
        assert ok.status_code == 200, ok.text
        assert ok.headers["content-type"].startswith("image/png")
        assert ok.content == _PNG_1x1

        # 401 unauthenticated (router gate — T-04-16).
        un = await client.get(f"/api/explore/{run_id}/screenshot/state-0.png")
        assert un.status_code == 401

        # Path traversal rejected (400 or 404 — never serves a file outside the workspace).
        trav = await authed_client.get(
            f"/api/explore/{run_id}/screenshot/..%2f..%2f.env"
        )
        assert trav.status_code in (400, 404)

        # A bare missing file is 404.
        missing = await authed_client.get(f"/api/explore/{run_id}/screenshot/nope.png")
        assert missing.status_code == 404
    finally:
        # Best-effort cleanup of the test workspace.
        try:
            (d / "state-0.png").unlink(missing_ok=True)
            d.rmdir()
        except OSError:
            pass
