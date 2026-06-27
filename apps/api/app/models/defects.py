"""Defect-intelligence models — the classification ledger + the draft-review defect row (DEF/JIRA).

Phase 9 turns every all-fail failure (post the Phase-7 retry) into a CLASSIFIED, EVIDENCED,
deduplicated draft. Two rows back that:

  - `Classification` — one row per classified failure: the deterministic 3-way class
    (infrastructure | automation | product_defect, String(16) vocab), the 0-100 confidence
    (Integer, clamped by the pure classifier — NEVER an LLM judgment, D-01), and the full cited
    evidence snapshot as JSON (none_as_null so a Python None persists as SQL NULL) the review UI
    renders. Threads by run_id + flow_id (the Phase-3 run_id convention + the kg/flows id).

  - `Defect` — the draft-review row + the JIRA-04 traceability link. status (draft | applied |
    rejected, server_default 'draft' — autonomy is OFF by default so every row starts a draft,
    D-04), the stable `fingerprint` (String(64) index — the `fp-<hash>` dedup key, D-05), the
    `jira_label` (the `fp-<hash>` LABEL applied on filing), and the nullable `jira_key` (the
    created/updated Jira issue key — NULL until a human or the autonomous gate files it, mirroring
    heal_audit.after_chain nullability). run_id/flow_id ARE the test<->flow<->execution link
    (JIRA-04): the Defect row joins to TestRun/TestResult + the kg/flows id; Phase 10 renders the
    chain, Phase 9 persists it.

Mirrors heal_audit.py / execution_history.py model style EXACTLY: Mapped[...] = mapped_column(...),
String(64) run_id + index, String(255) flow_id + index, String(16) status/class vocab, JSON
(none_as_null) evidence, server_default timestamps via func.now(). No LLM/gateway import.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Classification(Base):
    __tablename__ = "classifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Threads to the run + flow (Phase-3 run_id convention + the kg/flows id); both indexed.
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    flow_id: Mapped[str] = mapped_column(String(255), index=True)
    # infrastructure | automation | product_defect — the deterministic 3-way class (DEF-01).
    classification: Mapped[str] = mapped_column(String(16))
    # The 0-100 confidence the pure classifier clamped (Integer, never an LLM judgment — D-01).
    confidence: Mapped[int] = mapped_column(Integer)
    # The full cited-evidence snapshot (error_text/heal-history/infra-health/page-loaded/...) as
    # JSON. none_as_null=True so a Python None persists as SQL NULL (not JSON 'null').
    evidence: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Defect(Base):
    __tablename__ = "defects"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The test<->flow<->execution traceability keys (JIRA-04); both indexed for the joins.
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    flow_id: Mapped[str] = mapped_column(String(255), index=True)
    # infrastructure | automation | product_defect (the class that produced this draft).
    classification: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[int] = mapped_column(Integer)
    # The stable failure fingerprint (the `fp-<hash>` dedup key, D-05); indexed.
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    # The Jira LABEL applied on filing (`fp-<hash>`).
    jira_label: Mapped[str] = mapped_column(String(64))
    # The created/updated Jira issue key — NULL until filed (mirrors heal_audit.after_chain).
    jira_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # draft | applied | rejected — OFF-by-default autonomy keeps every row in draft (D-04).
    status: Mapped[str] = mapped_column(String(16), server_default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
