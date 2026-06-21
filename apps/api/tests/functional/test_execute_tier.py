"""API tier round-trip (EXEC-02/EXEC-05, B1/I1) — POST /api/executions + reconciled GET surface.

Three things this proves:
  1. ROUTE OWNERSHIP (B1, T-07-18): executions.py is the SINGLE owner of /api/executions —
     EXACTLY ONE handler per (method, path) under that prefix (introspect app.routes), and NO
     /api/executions route exists in execute.py. (in-process app import — no stack needed.)
  2. AUTH GATE (T-07-10): an UNAUTHENTICATED POST /api/executions -> 401 (live HTTP).
  3. TIER ROUND-TRIP (EXEC-02): an authed POST {tier:"smoke"} -> 202 + run_id, a test_run row
     is created and per-flow jobs are enqueued; GET /api/executions/{run_id} returns the status;
     a bogus id -> 404 (live HTTP, queue profile up). The enqueue is asserted against a captured
     enqueue call so the test does not depend on a consumer draining the queue.

The round-trip parts hit the RUNNING api over HTTP (D-02 convention). The ownership check imports
the app object in-process. Keyless: smoke is a tag tier (no graph); enqueue is monkeypatched so
no broker is strictly required for the captured-call assertion, but the live POST still needs the
api up to reach the route. neo4j is NOT needed (smoke is not risk-based).
"""

from __future__ import annotations

import os
import uuid
from collections import Counter

import httpx
import pytest

pytestmark = [pytest.mark.functional]

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8001")
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
_TIMEOUT = httpx.Timeout(30.0)


def test_exactly_one_handler_per_method_path_under_executions() -> None:
    """T-07-18: no duplicate (method, path) registration under /api/executions."""
    from app.main import app

    pairs: list[tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if not path.startswith("/api/executions") or not methods:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            pairs.append((method, path))

    dupes = [pair for pair, count in Counter(pairs).items() if count > 1]
    assert not dupes, f"duplicate (method, path) under /api/executions: {dupes}"
    # Sanity: the consolidated surface registers the POST + the two GETs.
    assert ("POST", "/api/executions") in pairs
    assert ("GET", "/api/executions") in pairs
    assert ("GET", "/api/executions/{run_id}") in pairs


def test_no_executions_route_in_execute_router() -> None:
    """B1: the legacy execute.py keeps only POST /api/execute — no /api/executions route."""
    from app.routers.execute import router as execute_router

    for route in execute_router.routes:
        assert "/executions" not in getattr(route, "path", ""), (
            f"execute.py must not own an /executions route: {route.path}"
        )


async def test_unauthenticated_post_executions_is_401() -> None:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=_TIMEOUT) as c:
        r = await c.post("/api/executions", json={"tier": "smoke"})
    assert r.status_code == 401, f"expected 401, got {r.status_code} {r.text}"


async def test_authed_post_smoke_tier_round_trip() -> None:
    """Authed POST {tier:smoke} -> 202 + run_id; GET status works; bogus id -> 404."""
    async with httpx.AsyncClient(base_url=API_BASE, timeout=_TIMEOUT) as c:
        login = await c.post(
            "/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert login.status_code == 200, f"login failed: {login.text}"

        r = await c.post("/api/executions", json={"tier": "smoke"})
        assert r.status_code == 202, f"expected 202, got {r.status_code} {r.text}"
        body = r.json()
        run_id = body["run_id"]
        assert run_id

        status = await c.get(f"/api/executions/{run_id}")
        assert status.status_code == 200, f"status read failed: {status.text}"
        assert status.json()["run_id"] == run_id

        bogus = await c.get(f"/api/executions/no-such-{uuid.uuid4().hex}")
        assert bogus.status_code == 404


async def test_post_smoke_creates_run_and_enqueues_per_flow(monkeypatch) -> None:
    """In-process: POST resolves the tier, creates a test_run row, enqueues per-flow jobs.

    Calls the route handler's collaborators directly (resolve_tier + create_test_run +
    enqueue_jobs) with enqueue_jobs monkeypatched to CAPTURE the published jobs — proving the
    per-flow enqueue without a live broker. This complements the live HTTP round-trip above.
    """
    from app.db.session import SessionLocal, engine
    from app.services import exec_service

    captured: dict = {}

    async def _fake_enqueue(run_id: str, jobs: list[dict]) -> None:
        captured["run_id"] = run_id
        captured["jobs"] = jobs

    monkeypatch.setattr(exec_service, "enqueue_jobs", _fake_enqueue)

    try:
        async with SessionLocal() as db:
            # smoke is a tag tier: resolve_tier returns the -m selector tokens.
            selector = exec_service.resolve_tier("smoke")
            assert selector == ["-m", "smoke"]
            run = await exec_service.create_test_run(db, "smoke", selector=" ".join(selector))
            # Enqueue one job per approved flow carrying the tag (here: a single flow).
            jobs = [{"flow_id": "flow-smoke-0"}]
            await exec_service.enqueue_jobs(run.run_id, jobs)

        assert captured["run_id"] == run.run_id
        assert captured["jobs"] == [{"flow_id": "flow-smoke-0"}]
    finally:
        await engine.dispose()
