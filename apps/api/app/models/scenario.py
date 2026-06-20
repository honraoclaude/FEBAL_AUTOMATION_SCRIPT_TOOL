"""Scenario model — the review-queue row for generated BDD scenarios (GEN-02 / D-01).

A `Scenario` is a generated Gherkin Feature persisted in Postgres (NOT Neo4j — Neo4j is the
discovered-structure graph; review state is relational, D-01). It threads explore→generate via
`run_id` and links the source flow via `flow_id` (the kg/flows id). Each row carries the
(possibly edited) Gherkin text PLUS the sidecar Then→kg_ref mapping (`then_refs`, the
no-vacuous-assertion gate's structured input — Mechanism 1) so the gate is a pure Neo4j
existence check independent of Gherkin text parsing and survives edit-in-place (D-02).

Status lifecycle: draft → approved | rejected. The review queue lists drafts; codegen reads
ONLY status=approved (D-01, enforced at the service layer by `list_approved`). `edited` flips
true on an edit-in-place save (which re-runs both gates). `stale` is the MINIMAL
regenerate-vs-approved reconciliation hook (mark stale when the underlying flow/graph changes;
deep re-derivation is deferred per CONTEXT).

Mirrors the Run/Execution model style: Mapped[...] = mapped_column(...), timestamps with
server_default=func.now().
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Threads explore→generate (Phase-3 run_id convention); indexed for per-run listing.
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    # The source flow (the kg/flows id, e.g. "flow-0"); indexed for per-flow lookups.
    flow_id: Mapped[str] = mapped_column(String(255), index=True)
    feature_name: Mapped[str] = mapped_column(String(255))
    # The (possibly edited) Feature text.
    gherkin_text: Mapped[str] = mapped_column(Text)
    # The sidecar Then→kg_ref mapping the no-vacuous gate consumes (Mechanism 1). JSON so it
    # survives edit-in-place as a structured object the gate re-validates.
    then_refs: Mapped[list] = mapped_column(JSON)
    # draft | approved | rejected — guarded at the service layer (scenario_service.VALID).
    status: Mapped[str] = mapped_column(String(16), server_default="draft")
    # True once a reviewer edits the Gherkin in place (the edit re-runs both gates, D-02).
    edited: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # Minimal regenerate-vs-approved reconciliation: mark stale when the flow/graph changes.
    stale: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
