"""Worker live-progress publish side (EXEC-03/04, D-07) — the execution Redis pub/sub seam.

Mirrors app/services/explorer/progress.py EXACTLY (the publish half of the Redis pub/sub → SSE
seam), but for the execution plane: per-test events go to the run-scoped channel `exec:{run_id}`
(the explorer uses `explore:{run_id}`). The SSE endpoint (Plan 04) re-emits each frame to the
live Executions view.

PITFALLS note (carried from Phase 4): REUSE the SAME lifespan get_redis() client — NEVER
construct a second Redis client. A publish to a zero-subscriber channel is a no-op, not an error.

SC3: this module imports ONLY app.core.redis_client + stdlib json — no LLM/gateway/explorer.
"""

from __future__ import annotations

import json

from app.core.redis_client import get_redis


async def publish_test_event(
    run_id: str,
    flow_id: str,
    *,
    status: str,
    attempt: int,
    duration_s: float = 0.0,
) -> None:
    """Publish a per-test event to the run-scoped channel `exec:{run_id}` (D-07).

    REUSES the shared lifespan client (get_redis()). The event carries ABSOLUTE per-test
    values (the live view reads the latest frame directly — never deltas), mirroring the
    explorer's progress contract. Best-effort: zero subscribers is a no-op.
    """
    event = {
        "run_id": run_id,
        "flow_id": flow_id,
        "status": status,
        "attempt": attempt,
        "duration_s": float(duration_s),
    }
    await get_redis().publish(f"exec:{run_id}", json.dumps(event))
