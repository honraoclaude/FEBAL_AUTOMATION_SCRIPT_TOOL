"""Per-flow job runner (EXEC-03) — the thin wrapper over the battle-tested subprocess runner.

A job message is `{run_id, flow_id}` (+ an optional base_url override for the determinism
proof). run_flow_job runs ONE isolated `uv run pytest <spec>` attempt — reusing the Phase-6
stability._run_spec_once subprocess shape VERBATIM (argv LIST, no shell — T-03-15/T-07-01,
cwd=_run_cwd(), output tail-cap, FileNotFoundError → honest failure) — records a TestResult in
a FRESH SessionLocal (Pitfall 2, mirroring execution.run_execution's finish), and publishes a
per-test event over the shared Redis seam.

SCOPE (Plan 01): this is the THIN single-attempt vertical slice. The kill-check + the
per-attempt RETRY loop + the flaky classifier + artifact capture arrive in Plan 03 — this slice
derives the verdict directly from one attempt's exit code (passed if 0 else product_failure) and
records exit_codes as a one-element list. No placeholder/stub for the live kill flag is added.

spec_path is run_id-DERIVED via workspaces.spec_path(run_id) — NEVER taken raw from the message
body (T-07-01 carry-forward of T-03-15): a hostile payload cannot inject a subprocess argument.

SC3: imports ONLY the subprocess primitives (stability._run_spec_once), the DB session, the
execution-history model, workspaces, and the worker progress publish — no LLM/gateway/explorer.
"""

from __future__ import annotations

import time

import structlog

from app.core.workspaces import spec_path
from app.db.session import SessionLocal
from app.models.execution_history import TestResult
from app.services.stability import _run_spec_once
from app.services.worker import progress

log = structlog.get_logger()


async def run_flow_job(job: dict) -> int | None:
    """Run one flow's planted/generated spec as an isolated subprocess; record a result row.

    Reuses stability._run_spec_once VERBATIM (argv list, no shell, cwd=_run_cwd(), output
    tail-cap). The spec is resolved from the message's run_id via the run_id-derived
    workspaces.spec_path convention — never a raw path from the body. Records a TestResult in
    a FRESH SessionLocal and publishes a per-test event. Returns the attempt's exit code.
    """
    run_id = job["run_id"]
    flow_id = job["flow_id"]
    base_url = job.get("base_url")  # optional override (the determinism proof points the spec)

    spec = str(spec_path(run_id))
    started = time.monotonic()
    result = await _run_spec_once(spec, base_url=base_url)
    duration_s = time.monotonic() - started

    exit_code = result["exit_code"]
    passed = result["passed"]
    # Plan-01 thin verdict (the full classifier — flaky/aborted — lands in Plan 03).
    verdict = "passed" if passed else "product_failure"
    status = "passed" if passed else "failed"

    # FRESH session (Pitfall 2): the worker owns its own session, never a request's.
    async with SessionLocal() as db:
        db.add(
            TestResult(
                run_id=run_id,
                flow_id=flow_id,
                verdict=verdict,
                attempts=1,
                exit_codes=[exit_code],
                duration_ms=int(duration_s * 1000),
            )
        )
        await db.commit()

    await progress.publish_test_event(
        run_id, flow_id, status=status, attempt=1, duration_s=duration_s
    )
    log.info(
        "run_flow_job_finished",
        run_id=run_id,
        flow_id=flow_id,
        verdict=verdict,
        exit_code=exit_code,
    )
    return exit_code
