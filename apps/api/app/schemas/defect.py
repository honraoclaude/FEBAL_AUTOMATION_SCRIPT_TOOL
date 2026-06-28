"""Defect review API schemas (JIRA-02 review surface + the calibration display).

The /api/defects router (Plan 04) serves the draft-review queue + per-defect detail that Plan
05's UI consumes. Three response shapes, mirroring schemas/heal.py's ORM-readable Pydantic v2
style (model_config = ConfigDict(from_attributes=True) for the row-backed shapes; a plain
BaseModel built from a dict for the calibration numbers):

  - DefectSummaryResponse — one queue row: the class/confidence/status + the optional jira_key +
    the run_id/flow_id source refs (the test<->flow<->execution links). ORM-readable.
  - DefectDetailResponse — the per-defect review surface: the row fields PLUS the proposed-Jira-
    issue fields (summary, the description prose + the enriched flag, steps, expected/actual,
    severity, priority), the cited evidence (error type / DOM diff / heal history / infra health),
    the attachment refs (run_id-derived basenames the UI turns into auth-gated URLs — NEVER raw
    paths), the fingerprint, and the calibrated confidence_threshold (so the UI bands confidence
    off the SERVER value, never a client literal). Built by hand (not from_attributes) because it
    composes the row with the derived proposed-issue/evidence fields.
  - CalibrationResponse — the read-only DEF-03/QUAL-03 numbers: classification_accuracy,
    draft_precision, confidence_threshold, autonomous_enabled. Nullable for the not-measured
    state (the UI renders the honest "not measured yet" copy).

Field names MUST match 09-UI-SPEC so Plan 05's zod client mirrors them.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DefectSummaryResponse(BaseModel):
    """One defect queue row — class/confidence/status + the source refs (ORM-readable)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    flow_id: str
    classification: str
    confidence: int
    fingerprint: str
    # NULL until filed (mirrors heal_audit nullability); the applied row shows the Jira-key link.
    jira_key: str | None
    # draft | applied | rejected
    status: str
    created_at: datetime
    updated_at: datetime


class AttachmentRef(BaseModel):
    """One artifact reference the UI turns into an auth-gated URL (NEVER a raw filesystem path)."""

    kind: str
    # The RUN-RELATIVE path (e.g. "flow-0/test/trace.zip") the UI feeds the artifact route;
    # never an absolute filesystem path (T-09-15).
    path: str


class ProposedIssue(BaseModel):
    """The proposed Jira issue body the reviewer reads before Apply (built via describe/build_adf)."""

    summary: str
    description: str
    # True only when an LLM wrote the prose; False -> the deterministic "written without an LLM".
    enriched: bool
    steps: list[str]
    expected: str
    actual: str
    severity: str
    priority: str


class DefectDetailResponse(BaseModel):
    """The per-defect review surface — the row + the proposed issue + evidence + attachments."""

    id: int
    run_id: str
    flow_id: str
    classification: str
    confidence: int
    fingerprint: str
    jira_key: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    # The proposed Jira issue (summary/description/steps/expected/actual/severity/priority).
    proposed_issue: ProposedIssue
    # The cited-evidence snapshot (error type / DOM diff / heal history / infra health) from the
    # Classification.evidence JSON — exactly what the classifier decided on.
    evidence: dict | None
    # Run-relative artifact refs the UI turns into auth-gated URLs (never raw paths).
    attachments: list[AttachmentRef]
    # The calibrated floor the UI bands confidence against (server value, never a client literal).
    confidence_threshold: int
    # The create-vs-update decision the apply path reports (None on a read; set after apply).
    last_action: str | None = None


class CalibrationResponse(BaseModel):
    """The read-only DEF-03/QUAL-03 calibration numbers (a plain dict-built BaseModel).

    Nullable accuracy/precision for the not-measured state (honest nulls — the UI renders the
    "run the accuracy harness to measure" copy). confidence_threshold + autonomous_enabled are
    always the SHIPPED settings values.
    """

    classification_accuracy: float | None
    draft_precision: float | None
    confidence_threshold: int
    autonomous_enabled: bool
