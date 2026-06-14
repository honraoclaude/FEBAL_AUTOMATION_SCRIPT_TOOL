"""Execution service (PLAT-02, D-04) — the /execute subprocess pytest runner.

Slice C of the tracer: run a run's generated pytest-playwright spec and land a result row
keyed BY run_id (FIX 1), retrievable via GET /executions/{run_id}.

CRITICAL invariants:
  - Pitfall 3 / T-03-16: the generated spec uses the SYNC Playwright API and MUST run only
    in an ISOLATED subprocess (`uv run pytest <spec_path>`) — NEVER an in-process pytest
    invocation (a sync Playwright call inside the running asyncio API process would deadlock
    /crash, and an in-process run is not isolated).
  - T-03-15 / T-01-26: the subprocess argv is a LIST with no `shell=True`; `spec_path` is
    run_id-derived (`workspaces/<run_id>/test_login.py`), never raw user input — so a
    hostile value cannot inject a command.
  - Pitfall 2: the BackgroundTask opens its OWN `SessionLocal` — never the request's db.

The run_id threads explore -> generate -> execute -> result: `finish_execution(db, run_id,
...)` flips the SAME Execution row the poll surface (GET /executions/{run_id}) reads (FIX 1).
"""

import asyncio
from pathlib import Path

import structlog

from app.core.config import settings
from app.db.session import SessionLocal
from app.services import run_service

log = structlog.get_logger()

# Cap captured output so a noisy spec cannot bloat the executions row / Postgres.
_OUTPUT_TAIL_CHARS = 8000


def _run_cwd() -> str:
    """The cwd for `uv run pytest` — the dir holding the uv project (pyproject.toml).

    settings.execution_cwd when set (container WORKDIR /app), else apps/api relative to
    this file (host/hybrid layout: app/services/execution.py -> app -> api). `uv run`
    resolves THIS project's env + pytest config from there; spec_path is absolute
    (run_id-derived) so cwd never affects spec resolution.
    """
    if settings.execution_cwd:
        return settings.execution_cwd
    # app/services/execution.py -> parents: services(0) app(1) api(2) -> apps/api.
    return str(Path(__file__).resolve().parents[2])


async def run_execution(run_id: str, spec_path: str) -> None:
    """BackgroundTask: run the run's generated spec in a subprocess; finish the row (FIX 1).

    Runs `uv run pytest <spec_path> -q` as an ISOLATED child process (argv list, no
    shell — T-03-15), capturing combined stdout/stderr. status = "passed" if returncode==0
    else "failed". Opens a FRESH SessionLocal (Pitfall 2) and calls
    `run_service.finish_execution(db, run_id, ...)` keyed BY run_id so the poll surface
    observes the terminal status. NEVER runs the spec inside this process (Pitfall 3).
    """
    status = "failed"
    exit_code: int | None = None
    output = ""
    try:
        proc = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            "pytest",
            spec_path,
            "-q",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=_run_cwd(),
        )
        out, _ = await proc.communicate()
        exit_code = proc.returncode
        output = (out.decode(errors="replace") if out else "")[-_OUTPUT_TAIL_CHARS:]
        status = "passed" if proc.returncode == 0 else "failed"
    except FileNotFoundError as exc:
        # `uv` (the runner binary) is missing — record an honest failure, never crash the
        # BackgroundTask silently (the run must still reach a terminal state for the poll).
        output = f"execution runner unavailable: {exc}"
        log.error("run_execution_runner_missing", run_id=run_id, error=str(exc))
    except Exception as exc:  # noqa: BLE001 -- any failure must finish the row, not vanish
        output = f"execution error: {exc}"
        log.error("run_execution_failed", run_id=run_id, error=str(exc))

    # FRESH session (Pitfall 2): flip the SAME run_id-keyed Execution row the poll reads.
    async with SessionLocal() as db:
        await run_service.finish_execution(
            db, run_id, status, exit_code=exit_code, output=output
        )
    log.info(
        "run_execution_finished", run_id=run_id, status=status, exit_code=exit_code
    )
