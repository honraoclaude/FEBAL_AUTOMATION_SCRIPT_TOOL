"""Run/Execution status service (PLAT-02, D-04) — mirrors target_service conventions.

The async-job status machine for the tracer slice. A single `run_id` threads
explore→graph and execute→result. Status integrity (T-03-09) is enforced HERE: every
transition goes through `set_status`/`finish_execution`, both guarded against the
four-state VALID set; a failure is captured as `error`, never a silent crash.

FIX 1 — one run_id-keyed status surface for BOTH paths:
  - explore path: status lives on the Run row (set by the explorer BackgroundTask).
  - execute path: status lives on the Execution row, flipped BY run_id by
    `finish_execution`.
  `get_status_by_run_id` resolves the Execution row when one exists for the run_id
  (execute path) else the Run row (explore path) — so `poll_until_terminal` reaches a
  terminal status for either path via the same run_id.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Execution, Run

# The only valid run/execution states — the status machine's whole alphabet (T-03-09).
VALID = {"queued", "running", "passed", "failed"}


class RunNotFoundError(Exception):
    """Raised when no Run (and no Execution) exists for a run_id."""


def _validate_status(status: str) -> str:
    """Guard a status against VALID; return it unchanged or raise ValueError.

    A tiny pure helper (no abstraction) so the guard is unit-testable without a session.
    """
    if status not in VALID:
        raise ValueError(f"invalid status {status!r}; valid: {sorted(VALID)}")
    return status


async def create_run(db: AsyncSession, kind: str, target_id: int | None) -> Run:
    """Create a Run with a fresh hex run_id in status 'queued'."""
    run = Run(run_id=uuid.uuid4().hex, kind=kind, target_id=target_id, status="queued")
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def set_status(
    db: AsyncSession, run_id: str, status: str, error: str | None = None
) -> Run:
    """Transition the Run row's status (guarded by VALID). Raises RunNotFoundError."""
    _validate_status(status)
    run = await db.scalar(select(Run).where(Run.run_id == run_id))
    if run is None:
        raise RunNotFoundError(run_id)
    run.status = status
    if error is not None:
        run.error = error
    await db.commit()
    await db.refresh(run)
    return run


async def create_execution(db: AsyncSession, run_id: str, spec_path: str) -> Execution:
    """Create an Execution carrying the SAME run_id as its run, status 'queued'."""
    execution = Execution(run_id=run_id, spec_path=spec_path, status="queued")
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return execution


async def finish_execution(
    db: AsyncSession,
    run_id: str,
    status: str,
    exit_code: int | None,
    output: str | None,
) -> Execution:
    """Flip the Execution row keyed BY run_id to a terminal status (FIX 1).

    Keyed by run_id (NOT the Execution integer id) so the execute path flips the SAME
    row the poll surface reads. Raises RunNotFoundError if no Execution exists.
    """
    _validate_status(status)
    execution = await db.scalar(select(Execution).where(Execution.run_id == run_id))
    if execution is None:
        raise RunNotFoundError(run_id)
    execution.status = status
    execution.exit_code = exit_code
    execution.output = output
    await db.commit()
    await db.refresh(execution)
    return execution


async def get_run(db: AsyncSession, run_id: str) -> Run | None:
    return await db.scalar(select(Run).where(Run.run_id == run_id))


async def get_execution_by_run_id(db: AsyncSession, run_id: str) -> Execution | None:
    return await db.scalar(select(Execution).where(Execution.run_id == run_id))


async def get_status_by_run_id(db: AsyncSession, run_id: str) -> dict:
    """Resolve a single {run_id, kind, status, error} for the poll surface (FIX 1).

    Prefer the Execution row when one exists for this run_id (execute path); else fall
    back to the Run row (explore path). Raises RunNotFoundError when neither exists.
    """
    execution = await get_execution_by_run_id(db, run_id)
    if execution is not None:
        return {
            "run_id": execution.run_id,
            "kind": "execute",
            "status": execution.status,
            "error": None,
        }
    run = await get_run(db, run_id)
    if run is not None:
        return {
            "run_id": run.run_id,
            "kind": run.kind,
            "status": run.status,
            "error": run.error,
        }
    raise RunNotFoundError(run_id)


async def list_runs(db: AsyncSession) -> list[Run]:
    return list((await db.scalars(select(Run).order_by(Run.id))).all())


async def list_executions(db: AsyncSession) -> list[Execution]:
    return list((await db.scalars(select(Execution).order_by(Execution.id))).all())
