"""Heal-audit model — the auditable per-heal ledger (HEAL-03).

Every heal the in-spec layer journals (Plan 02) becomes ONE `HealAudit` row when the worker
ingests the per-flow heal-journal after the subprocess exits (Plan 03). The row is the
auditable record from which the before/after diff renders: the element key, the BEFORE chain
(the broken repo chain), the AFTER chain (the healed locator chain — nullable: a
`fail_as_defect` has no after), the blended confidence, the locator-resolution outcome, the
live match count (the hard-uniqueness-gate input), and the run/flow traceability keys.

`outcome` vocabulary (the journal's three locator verdicts + the Plan-05 apply states):
  auto_heal | quarantine | fail_as_defect | applied | rejected.
`reviewed_outcome` (nullable) is set by the Plan-05 reject/apply API for false-heal tracking
(HEAL-04) — left NULL by the Plan-03 ingest.

Chains are stored as JSON, NEVER binary blobs (carries the execution-history rule: artifacts
and structured data are JSON/scalars only, never bytes in Postgres — T-08-13).

Mirrors execution_history.py's model style: Mapped[...] = mapped_column(...), String widths,
indexed run_id/flow_id, server_default timestamp via func.now().
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HealAudit(Base):
    __tablename__ = "heal_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The page-object attribute key the heal targeted (e.g. "button_add_to_cart"); indexed for
    # per-element history lookups.
    element_key: Mapped[str] = mapped_column(String(255), index=True)
    # Threads to the run + flow (Phase-3 run_id convention + the kg/flows id); both indexed.
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    flow_id: Mapped[str] = mapped_column(String(255), index=True)
    # The BROKEN repo chain before the heal, as a JSON list of {strategy, value} entries.
    before_chain: Mapped[list] = mapped_column(JSON)
    # The HEALED locator chain (JSON list) — nullable: a fail_as_defect produced no after.
    # none_as_null=True so a Python None persists as SQL NULL (not JSON 'null'), keeping the
    # "no after chain" state cleanly distinguishable when the diff renders from the record.
    after_chain: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    # The blended heal confidence [0,1] (healing/confidence.confidence output).
    confidence: Mapped[float] = mapped_column(Float)
    # auto_heal | quarantine | fail_as_defect | applied | rejected.
    outcome: Mapped[str] = mapped_column(String(16))
    # The HARD-uniqueness-gate input: how many live elements the healed selector matched.
    live_match_count: Mapped[int] = mapped_column(Integer)
    # Set by the Plan-05 reject/apply API for false-heal tracking (HEAL-04); NULL on ingest.
    reviewed_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
