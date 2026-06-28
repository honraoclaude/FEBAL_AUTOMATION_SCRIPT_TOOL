"""/api/defects — the auth-gated defect draft-review API (JIRA-02 / D-04).

The human-in-the-loop surface the autonomy gate requires: a person reviews every machine-
classified product defect and either APPLIES it (files/updates a Jira issue via the gateway) or
REJECTS it, and reads the calibration numbers before flipping the autonomous-filing config flag.
Clones routers/heals.py — the router-level Depends(get_current_user), the status-filtered list,
_get_*_or_404, the apply/reject commit+refresh+log shape. Five endpoints, ALL auth-gated:

  - GET  /api/defects?status=draft&class=...  -> list[DefectSummaryResponse] (the review queue,
        ORM-parameterized filters, drafts-first then confidence-desc then updated-desc).
  - GET  /api/defects/{id}                    -> DefectDetailResponse (the proposed issue via
        build_adf/describe + the cited evidence + run_id-derived attachment refs + the calibrated
        confidence_threshold). 404 on an unknown id.
  - GET  /api/defects/calibration             -> CalibrationResponse (read-only accuracy/precision
        /threshold/autonomy; honest nulls when not measured).
  - POST /api/defects/{id}/apply              -> DefectDetailResponse (not-configured honest 4xx
        when no token; else file_or_update -> persist jira_key + status='applied' + report
        create-vs-update).
  - POST /api/defects/{id}/reject             -> DefectDetailResponse (status='rejected' flag flip).

AUTH (T-09-16): the router-level Depends(get_current_user) gates EVERY endpoint — especially the
state-changing apply/reject (state-changing endpoints are NEVER public, V4). `require_role` does
NOT exist — reuse get_current_user. SECURITY: id is an int PK + status/class are string filters,
all ORM-bound (no string SQL — V5). Attachment paths are run_id-derived (NEVER request paths,
T-09-15). The Jira token never enters a log event (T-09-17). The fp-<hash> is server-built
(T-09-13). The class/confidence decision is deterministic — the LLM here is description-prose only.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.defects import Classification, Defect
from app.schemas.defect import (
    AttachmentRef,
    CalibrationResponse,
    DefectDetailResponse,
    DefectSummaryResponse,
    ProposedIssue,
)
from app.services.defects.pipeline import _severity_priority, file_or_update
from app.services.jira.client import AtlassianJira, JiraGateway
from app.services.jira.description import describe

log = structlog.get_logger()

router = APIRouter(
    prefix="/api/defects",
    tags=["defects"],
    # Router-level gate: EVERY endpoint (incl. the state-changing apply/reject) is auth-gated.
    # get_current_user 401s an unauthenticated request before any handler runs (T-09-16, V4).
    dependencies=[Depends(get_current_user)],
)

_NOT_FOUND = "No defect found for this id"

# The actionable status order for the queue: drafts first (need review), then applied, then
# rejected (a small ORM-side ordering key — sorts before confidence-desc / updated-desc).
_STATUS_ORDER = {"draft": 0, "applied": 1, "rejected": 2}


def _gateway() -> JiraGateway:
    """The live Jira gateway (AtlassianJira) — boot-safe; is_configured reflects the secret."""
    return AtlassianJira()


async def _get_defect_or_404(db: AsyncSession, defect_id: int) -> Defect:
    """Load a Defect by int PK (ORM-parameterized) or raise 404 (unknown id)."""
    defect = await db.get(Defect, defect_id)
    if defect is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return defect


@router.get("/calibration", response_model=CalibrationResponse)
async def defect_calibration() -> CalibrationResponse:
    """The read-only DEF-03/QUAL-03 calibration numbers + the autonomy flag (honest nulls).

    classification_accuracy / draft_precision are NULL until measured (the harness writes no
    runtime store in this phase — the UI renders the honest "not measured yet" copy). The
    confidence_threshold + autonomous_enabled are the SHIPPED settings values (never literals).
    """
    return CalibrationResponse(
        classification_accuracy=None,
        draft_precision=None,
        confidence_threshold=settings.jira_confidence_threshold,
        autonomous_enabled=settings.jira_autonomous_enabled,
    )


@router.get("", response_model=list[DefectSummaryResponse])
async def list_defects(
    status: str = "draft",
    class_: str | None = Query(default=None, alias="class"),
    db: AsyncSession = Depends(get_db),
) -> list[Defect]:
    """The defects filtered by status (default 'draft') + optional class — the review queue.

    `status` matches the `status` column and `class_` (the `?class=` query alias) matches the
    `classification` column, both ORM-bound (parameterized — V5). 'all' lifts the status filter.
    Sort: drafts-first, then confidence desc, then most-recently-updated (the actionable order).
    """
    stmt = select(Defect)
    if status and status != "all":
        stmt = stmt.where(Defect.status == status)
    if class_:
        stmt = stmt.where(Defect.classification == class_)
    rows = list((await db.scalars(stmt)).all())
    rows.sort(
        key=lambda d: (
            _STATUS_ORDER.get(d.status, 9),
            -d.confidence,
            d.updated_at.timestamp() * -1,
        )
    )
    return rows


async def _load_evidence(db: AsyncSession, defect: Defect) -> dict | None:
    """The cited-evidence snapshot from the matching Classification row (run_id + flow_id)."""
    row = (
        await db.scalars(
            select(Classification)
            .where(
                Classification.run_id == defect.run_id,
                Classification.flow_id == defect.flow_id,
            )
            .order_by(Classification.id.desc())
        )
    ).first()
    return row.evidence if row else None


async def _proposed_issue(db: AsyncSession, defect: Defect, evidence: dict | None) -> ProposedIssue:
    """Build the proposed Jira issue body (summary + prose via describe + severity/priority)."""
    severity, priority = _severity_priority(defect.classification, defect.confidence)
    error_text = (evidence or {}).get("error_text", "") if evidence else ""
    prose, enriched = await describe(
        db=db,
        evidence={
            "classification": defect.classification,
            "flow": defect.flow_id,
            "summary": error_text,
        },
        run_id=defect.run_id,
    )
    return ProposedIssue(
        summary=f"[{defect.classification}] {defect.flow_id} failed (run {defect.run_id})",
        description=prose,
        enriched=enriched,
        steps=[],
        expected="The flow to succeed.",
        actual=error_text or f"The flow failed and was classified {defect.classification}.",
        severity=severity,
        priority=priority,
    )


def _attachment_refs(evidence: dict | None) -> list[AttachmentRef]:
    """The run-relative artifact refs from the evidence snapshot (never absolute paths)."""
    arts = (evidence or {}).get("artifacts", []) if evidence else []
    return [AttachmentRef(kind=a.get("kind", "artifact"), path=a.get("path", "")) for a in arts]


async def _detail(db: AsyncSession, defect: Defect, *, last_action: str | None = None) -> DefectDetailResponse:
    """Assemble the full detail response (the row + proposed issue + evidence + attachments)."""
    evidence = await _load_evidence(db, defect)
    proposed = await _proposed_issue(db, defect, evidence)
    return DefectDetailResponse(
        id=defect.id,
        run_id=defect.run_id,
        flow_id=defect.flow_id,
        classification=defect.classification,
        confidence=defect.confidence,
        fingerprint=defect.fingerprint,
        jira_key=defect.jira_key,
        status=defect.status,
        created_at=defect.created_at,
        updated_at=defect.updated_at,
        proposed_issue=proposed,
        evidence=evidence,
        attachments=_attachment_refs(evidence),
        confidence_threshold=settings.jira_confidence_threshold,
        last_action=last_action,
    )


@router.get("/{defect_id}", response_model=DefectDetailResponse)
async def get_defect(defect_id: int, db: AsyncSession = Depends(get_db)) -> DefectDetailResponse:
    """The per-defect review surface — proposed issue + cited evidence + attachment refs + threshold.

    404 on an unknown id. The attachment refs are run-relative (the UI builds the auth-gated URL);
    the confidence_threshold is the calibrated server value the UI bands confidence against.
    """
    defect = await _get_defect_or_404(db, defect_id)
    return await _detail(db, defect)


@router.post("/{defect_id}/apply", response_model=DefectDetailResponse)
async def apply_defect(
    defect_id: int, db: AsyncSession = Depends(get_db)
) -> DefectDetailResponse:
    """File-or-update the defect to Jira (the gateway dedup path) + persist jira_key + status.

    If Jira is NOT configured (no token) -> a clear 400 honest signal (the UI shows the not-
    configured caption; the defect stays a draft). Else file_or_update (a CREATE or UPDATE via the
    fingerprint-label JQL dedup) -> persist defect.jira_key + status='applied' and report the
    create-vs-update decision so the UI shows "Issue filed" / "Issue updated". 404 on unknown id.
    """
    defect = await _get_defect_or_404(db, defect_id)
    gateway = _gateway()
    if not gateway.is_configured:
        raise HTTPException(
            status_code=400,
            detail=(
                "Jira is not configured: set JIRA_URL, JIRA_EMAIL and JIRA_API_TOKEN to file "
                "issues. The defect stays a draft until then."
            ),
        )

    evidence = await _load_evidence(db, defect)
    proposed = await _proposed_issue(db, defect, evidence)
    artifacts = [a["path"] for a in (evidence or {}).get("artifacts", [])]
    result = await file_or_update(
        gateway, defect, artifacts, run_counter=0, prose=proposed.description
    )
    if result.action in ("create", "update"):
        defect.jira_key = result.jira_key
        defect.status = "applied"
        await db.commit()
        await db.refresh(defect)
        log.info("defect_applied", defect_id=defect_id, action=result.action, key=result.jira_key)
    return await _detail(db, defect, last_action=result.action)


@router.post("/{defect_id}/reject", response_model=DefectDetailResponse)
async def reject_defect(
    defect_id: int, db: AsyncSession = Depends(get_db)
) -> DefectDetailResponse:
    """Mark the defect rejected (status='rejected') — a flag flip; nothing was filed. 404 on unknown id."""
    defect = await _get_defect_or_404(db, defect_id)
    defect.status = "rejected"
    await db.commit()
    await db.refresh(defect)
    log.info("defect_rejected", defect_id=defect_id)
    return await _detail(db, defect, last_action="reject")
