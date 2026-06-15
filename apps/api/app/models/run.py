"""Run + Execution models — the async-job ledger for the tracer slice (PLAT-02, D-04).

A `Run` is the unit of work a single `run_id` threads through the slice:
  - kind="explore" rows are written by POST /explore; their status is flipped on the
    RUN row by the explorer BackgroundTask (queued→running→passed/failed).
  - kind="execute" rows are the parent of an `Execution`.

An `Execution` carries the SAME `run_id` as its run (the join key) plus the spec it
ran and the terminal result. FIX 1: the executions.run_id column is the poll key the
execute path reads BY run_id — `get_status_by_run_id` reads the Execution row when one
exists for a run_id (execute path), else the Run row (explore path), so a single
run_id-keyed status surface serves BOTH paths.

BackgroundTasks are NOT durable (RESEARCH): a run left `running` after an api crash is
an accepted tracer limitation — Phase 7's RabbitMQ workers add durability.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The traceability key threaded explore→graph (and execute→result). Unique per run.
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # "explore" | "execute"
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    error: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Phase 4 (EXPL-05): the terminal exploration stop_reason from the STOP_REASONS
    # vocabulary (max_steps/max_depth/wall_clock/budget/saturation/converged/failed/stopped).
    # Nullable — only explore runs set it; the 04-04 UI consumes it.
    stop_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # FIX 1: the join/poll key. The execute path flips THIS row BY run_id and the poll
    # surface (get_status_by_run_id) reads THIS row BY run_id — same row, both ends.
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    spec_path: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
