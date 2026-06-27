"""Execution-history models — the regression-run ledger for the worker plane (EXEC-03/04/05).

A `TestRun` is one tier run (smoke/sanity/regression/full): the parent row the worker counters
roll up into. Each flow it executes lands a `TestResult` (the per-flow verdict + attempts +
exit codes), and any captured evidence lands a `TestArtifact` (a RUN-RELATIVE path to a file in
MinIO/workspaces — NEVER a binary blob in Postgres). All three thread by `run_id` (the Phase-3
run_id convention) and per-flow rows also carry `flow_id` (the kg/flows id).

Status lifecycle (TestRun): queued → running → passed | failed | killed (the live kill flag,
Plan 03). Verdict vocabulary (TestResult): passed | flaky | product_failure | aborted — the
flaky classifier (Plan 03) derives flaky/product_failure from the retry attempts; this slice
(Plan 01) records the thin passed/product_failure shape from a single attempt's exit code.

W4 decision (a): artifact `kind` is screenshot | trace | video ONLY. Console + network logs are
captured INSIDE the Playwright trace (--tracing=on) — there are NO separate console_log /
network_log files, so no such kinds exist.

Mirrors the Run/Execution/Scenario model style: Mapped[...] = mapped_column(...), String widths
matching run.py/scenario.py, server_default timestamps via func.now().
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TestRun(Base):
    __tablename__ = "test_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The tier-run traceability key (Phase-3 run_id convention); unique per run, indexed.
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # The requested tier: smoke | sanity | regression | full.
    tier: Mapped[str] = mapped_column(String(16))
    # The resolved pytest-bdd marker selector (Plan 02); nullable for `full` (no filter).
    selector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # queued | running | passed | failed | killed (killed = the live kill flag, Plan 03).
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    # Counters the worker rolls up as flows complete — absolute values, default 0.
    total: Mapped[int] = mapped_column(Integer, server_default="0")
    passed: Mapped[int] = mapped_column(Integer, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, server_default="0")
    flaky: Mapped[int] = mapped_column(Integer, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TestResult(Base):
    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Threads to the parent TestRun by run_id; indexed for per-run listing.
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    # The source flow (the kg/flows id, e.g. "flow-0"); indexed for per-flow lookups.
    flow_id: Mapped[str] = mapped_column(String(255), index=True)
    # passed | flaky | product_failure | aborted (the flaky classifier sets flaky/aborted in
    # Plan 03; this slice records passed/product_failure from one attempt's exit code).
    verdict: Mapped[str] = mapped_column(String(16))
    # How many subprocess attempts the worker made (1 in this slice; retry loop in Plan 03).
    attempts: Mapped[int] = mapped_column(Integer)
    # The exit code of every attempt, as a JSON list (no binary column).
    exit_codes: Mapped[list] = mapped_column(JSON)
    # The LAST attempt's tail-capped subprocess output (stdout/stderr) — the error TEXT the
    # Phase-9 classifier reads to classify by error type (Pitfall 1, plan 09-01). Nullable: the
    # aborted/kill-drained path never ran a subprocess so it has no output. Text, never a blob.
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TestArtifact(Base):
    __tablename__ = "test_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    flow_id: Mapped[str] = mapped_column(String(255), index=True)
    # screenshot | trace | video ONLY (W4 (a): console/network live inside the trace).
    kind: Mapped[str] = mapped_column(String(16))
    # A RUN-RELATIVE path that may contain subdir segments (e.g.
    # "<flow_id>/<test-slug>/trace.zip") — Plan 03 records it, Plan 04 resolves it. String
    # path only, NEVER a binary column (artifacts live in MinIO/workspaces).
    path: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
