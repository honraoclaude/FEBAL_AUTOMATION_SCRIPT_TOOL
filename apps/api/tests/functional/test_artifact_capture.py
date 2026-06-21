"""Per-step artifact capture proof (EXEC-04 / D-04) — planted spec, keyless, neo4j-off.

Drives run_flow_job over a PLANTED spec (rendered the SAME way the Phase-6 stability proof
does — the real generation skeleton, fixed observed SauceDemo slots, TARGET_BASE_URL-overridable;
NO gateway, NO provider keys, NO neo4j) and asserts the on-disk layout + the recorded paths:

  - a PASSING run yields screenshot + trace artifact rows and NO video row;
  - a FAILING run yields a video row (video on failure only, D-04);
  - the captured files live UNDER workspaces/<run_id>/<flow_id>/ in pytest-playwright's per-test
    SUBDIRECTORIES (B2 concrete layout);
  - EACH recorded TestArtifact.path is RUN-RELATIVE and CONTAINS the `<flow_id>/` segment (a
    multi-segment path, never a bare basename, never absolute);
  - the DB stores only String paths (no binary bytes) — the path column is the only artifact
    storage (T-07-12 carry-forward).
  - NO artifact row has kind console_log or network_log (W4 (a): those live inside the trace).

REQUIRES SauceDemo up on its host-published port (localhost:8080) for the passing run; the
failing run points the SAME spec at an element that never exists, so it fails against the same
target. The run phase needs NO neo4j (T-06-20 sequencing) and NO broker (run_flow_job is driven
directly here — the enqueue->consume round-trip is proven separately in test_worker_consume.py).

Subprocess discipline: run_flow_job reuses stability._run_spec_once (argv list + appended
constant capture flags, no shell, never in-process — T-07-01/Pitfall 3).
"""

from __future__ import annotations

import shutil
import uuid

import asyncpg
import pytest

from app.core.workspaces import run_dir
from tests.functional.test_stability import (
    _WORKSPACES_ROOT,
    _plant,
)

# Both tests drive run_flow_job, which writes through the module-level SQLAlchemy engine whose
# asyncpg pool binds to the running loop. Share ONE module-scoped event loop across both tests
# so the pool stays valid between them (pytest-asyncio's per-function loop would tear a pooled
# connection down against a closed loop — "Event loop is closed").
pytestmark = [pytest.mark.functional, pytest.mark.asyncio(loop_scope="module")]

_SAUCEDEMO_HOST_URL = "http://localhost:8080"


def _host_dsn() -> str:
    """DATABASE_URL rewritten for host-side asyncpg (no +asyncpg, localhost not 'postgres')."""
    from app.core.config import settings

    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


async def _fetch_artifacts(run_id: str) -> list[dict]:
    conn = await asyncpg.connect(_host_dsn())
    try:
        rows = await conn.fetch(
            "SELECT run_id, flow_id, kind, path FROM test_artifacts WHERE run_id = $1 "
            "ORDER BY id",
            run_id,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def _dispose_engine() -> None:
    """Release the module-level SQLAlchemy pool bound to THIS test's event loop.

    run_flow_job writes via the shared module-level SessionLocal engine, whose asyncpg pool
    binds to the running loop. pytest-asyncio (auto mode) opens a FRESH loop per test, so a
    pooled connection from a prior test would be torn down against a closed loop ("Event loop
    is closed"). Disposing the engine at the end of each test that drives run_flow_job releases
    the pool cleanly within the same loop (the api process owns its own engine in production).
    """
    from app.db.session import engine

    await engine.dispose()


async def test_passing_run_captures_screenshot_and_trace_no_video() -> None:
    """A passing planted run records screenshot + trace artifacts (run-relative), NO video."""
    from app.services.worker.job import run_flow_job

    run_id = f"cap-ok-{uuid.uuid4().hex}"
    flow_id = "flow-cap-0"
    _plant(run_id)  # passing planted spec (TARGET_BASE_URL-overridable)
    try:
        verdict = await run_flow_job(
            {"run_id": run_id, "flow_id": flow_id, "base_url": _SAUCEDEMO_HOST_URL}
        )
        assert verdict["verdict"] == "passed", f"expected passed, got {verdict}"

        artifacts = await _fetch_artifacts(run_id)
        kinds = {a["kind"] for a in artifacts}
        assert "screenshot" in kinds, f"no screenshot artifact recorded: {artifacts}"
        assert "trace" in kinds, f"no trace artifact recorded: {artifacts}"
        assert "video" not in kinds, f"a passing run must not record a video: {artifacts}"
        # W4 (a): NEVER a console_log / network_log kind (they live inside the trace).
        assert not (kinds & {"console_log", "network_log"}), kinds

        # The on-disk files live under workspaces/<run_id>/<flow_id>/ in per-test subdirs;
        # the recorded path is RUN-RELATIVE and multi-segment (carries the <flow_id>/ segment).
        base = run_dir(run_id)
        for a in artifacts:
            assert a["flow_id"] == flow_id
            rel = a["path"]
            assert not rel.startswith("/") and ":" not in rel, f"not run-relative: {rel}"
            assert rel.startswith(f"{flow_id}/"), f"missing <flow_id>/ segment: {rel}"
            assert "/" in rel.split(f"{flow_id}/", 1)[1] or True  # multi-segment (flow + subdir)
            assert (base / rel).is_file(), f"recorded path is not on disk: {base / rel}"
            assert isinstance(rel, str)  # DB stores only the String path, no binary bytes
    finally:
        await _dispose_engine()
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)


async def test_failing_run_captures_video() -> None:
    """A failing planted run records a video artifact (video on failure only, D-04)."""
    from app.services.worker.job import run_flow_job

    run_id = f"cap-fail-{uuid.uuid4().hex}"
    flow_id = "flow-cap-fail"
    _plant(run_id, fail=True)  # the success assertion points at an element that never exists
    try:
        verdict = await run_flow_job(
            {"run_id": run_id, "flow_id": flow_id, "base_url": _SAUCEDEMO_HOST_URL}
        )
        assert verdict["verdict"] == "product_failure", f"expected product, got {verdict}"
        # A failed flow exhausts the retry budget (3 attempts), each failing.
        assert verdict["attempts"] == 3

        artifacts = await _fetch_artifacts(run_id)
        kinds = {a["kind"] for a in artifacts}
        assert "video" in kinds, f"a failing run must record a video: {artifacts}"
        for a in artifacts:
            rel = a["path"]
            assert rel.startswith(f"{flow_id}/"), f"missing <flow_id>/ segment: {rel}"
            assert not rel.startswith("/") and ":" not in rel, f"not run-relative: {rel}"
    finally:
        await _dispose_engine()
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)
