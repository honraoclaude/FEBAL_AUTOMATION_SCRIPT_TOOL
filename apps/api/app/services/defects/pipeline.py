"""The defect pipeline: draft-row persistence + the file-or-update dedup/cap/autonomy core.

This module composes the SHIPPED pieces into the JIRA-02/03/04 draft-queue lifecycle:

  - `file_or_update(gateway, defect, artifacts, *, run_counter)` — the dedup + per-run cap core
    (Task 1). It builds the server-side `fp-<hash>` JQL `labels = "fp-<hash>" AND statusCategory
    != Done`, searches via the gateway, and:
        * a HIT  -> add_comment + re-attach each artifact (an UPDATE — never a create, never
          consumes a cap slot — T-09-14);
        * a MISS -> only when run_counter < settings.jira_max_tickets_per_run: create_issue with
          the fp-<hash> label + ADF description, add_attachment per artifact, best-effort
          create_issue_link (JIRA-04), increment the counter (a CREATE);
        * a MISS at the cap -> a NO-FILE result (the draft persists, never dropped — Pitfall 5).

  - `run_defect_pipeline(db, run_id, flow_id, *, gateway, run_counter)` — the post-run
    orchestrator (Task 2): classify_failure -> persist a Classification + a draft Defect row
    (the JIRA-04 run_id/flow_id traceability link) -> (only when may_autofile AND product_defect)
    auto-file via file_or_update.

SECURITY: the `fp-<hash>` JQL carries a server-built sha1 hex ONLY (no user text — T-09-13/V5).
Every artifact path is resolved under run_dir(defect.run_id) via the executions.py multi-segment
containment guard (reject "", ".", "..", "\\") — NEVER a request-body path (T-09-15). No Jira
token is logged. NO LLM on the class/confidence decision (the classifier is deterministic, D-01).
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.core.config import settings
from app.core.workspaces import run_dir
from app.models.defects import Classification, Defect
from app.services.defects import autonomy
from app.services.defects.evidence import classify_failure
from app.services.jira.adf import build_adf
from app.services.jira.description import describe
from app.services.search.indexer import index_failure

log = structlog.get_logger()


def _failure_error_text(evidence: dict | None) -> str | None:
    """Pull the searchable error text out of a classifier evidence snapshot for the ES index.

    Only the textual error/notes — never a token (T-10-21; the classifier evidence carries no
    secret, and structlog redaction already masks any password/secret/token before render).
    """
    if not evidence:
        return None
    for key in ("error_text", "error", "notes", "summary"):
        val = evidence.get(key)
        if isinstance(val, str) and val:
            return val
    return None


# --- severity -> priority map (RESEARCH Open-Q3 — a small PURE map, planner's discretion) -------
# Product defects matter most; automation/infrastructure are secondary. High confidence on a
# product defect -> High priority. Not load-bearing; deterministic.
def _severity_priority(classification: str, confidence: int) -> tuple[str, str]:
    """Map the deterministic class + confidence to (severity, priority) — pure, no LLM."""
    if classification == "product_defect":
        if confidence >= 80:
            return "High", "High"
        return "Medium", "Medium"
    if classification == "automation":
        return "Medium", "Medium"
    # infrastructure
    return "Low", "Low"


@dataclass(frozen=True)
class FileResult:
    """The outcome of file_or_update — what the router/pipeline persists + reports to the UI.

    action: "create" (new issue filed) | "update" (existing issue commented+re-attached) |
            "none" (the per-run cap was reached — the defect stays a draft, never dropped).
    jira_key: the created/updated issue key (None for a NO-FILE result).
    counter: the (possibly incremented) per-run create counter to thread to the next call.
    """

    action: str
    jira_key: str | None
    counter: int


def _dedup_jql(fingerprint: str) -> str:
    """The fixed dedup JQL built from the SERVER-side fingerprint (no user text — T-09-13)."""
    return f'labels = "fp-{fingerprint}" AND statusCategory != Done'


def _safe_artifact_paths(run_id: str, artifacts: list[str]) -> list[str]:
    """Resolve each run-relative artifact path under run_dir(run_id) with the containment guard.

    Mirrors executions.execution_artifact (T-09-15): split into segments, reject any empty / "."
    / ".." / backslash-bearing segment, then require the resolved path to stay inside the run's
    workspace. Returns the absolute string paths the gateway attaches. NEVER a request-body path.
    """
    base = run_dir(run_id).resolve()
    out: list[str] = []
    for rel in artifacts:
        segments = rel.split("/")
        if any(seg in ("", ".", "..") or "\\" in seg for seg in segments):
            log.warning("defect_artifact_rejected", reason="invalid_segment")
            continue
        target = (base / rel).resolve()
        if target != base and base not in target.parents:
            log.warning("defect_artifact_rejected", reason="outside_run_dir")
            continue
        out.append(str(target))
    return out


def _comment_adf(defect: Defect) -> dict:
    """An ADF v3 comment doc for the update-on-dup path (re-classified, new evidence re-attached)."""
    return build_adf(
        prose=(
            f"Recurrence: the same failure ({defect.classification}, fingerprint "
            f"fp-{defect.fingerprint}) was observed again in run {defect.run_id} "
            f"flow {defect.flow_id}. New evidence re-attached."
        ),
        steps=[],
        expected="The flow to succeed.",
        actual="The same classified failure recurred.",
        severity=_severity_priority(defect.classification, defect.confidence)[0],
        priority=_severity_priority(defect.classification, defect.confidence)[1],
    )


def _create_fields(defect: Defect, *, prose: str) -> dict:
    """Build the Jira v3 create fields for a defect (ADF description, fp-<hash> label)."""
    severity, priority = _severity_priority(defect.classification, defect.confidence)
    summary = (
        f"[{defect.classification}] {defect.flow_id} failed (run {defect.run_id})"
    )
    description = build_adf(
        prose=prose,
        steps=[],
        expected="The flow to succeed.",
        actual="The flow failed and was classified " + defect.classification + ".",
        severity=severity,
        priority=priority,
    )
    return {
        "project": {"key": settings.jira_project_key},
        "issuetype": {"name": "Bug"},
        "summary": summary,
        "description": description,
        "labels": [f"fp-{defect.fingerprint}"],
        "priority": {"name": priority},
    }


async def file_or_update(
    gateway,
    defect: Defect,
    artifacts: list[str],
    *,
    run_counter: int,
    prose: str | None = None,
) -> FileResult:
    """File-or-update a defect to Jira via fingerprint-label JQL dedup under the per-run cap.

    HIT  -> add_comment + re-attach each artifact (UPDATE; no cap consumption).
    MISS -> create (only if run_counter < settings.jira_max_tickets_per_run) + attach + link.
    MISS at the cap -> NO-FILE (the defect persists as a draft — Pitfall 5).

    `artifacts` are RUN-RELATIVE paths resolved under run_dir(defect.run_id) (the containment
    guard). `prose` is the (optionally LLM-enriched) description prose; a deterministic default
    is used when omitted so the core is keyless-testable.
    """
    paths = _safe_artifact_paths(defect.run_id, artifacts)

    existing = await gateway.search_jql(_dedup_jql(defect.fingerprint))
    if existing:
        # --- HIT: UPDATE the existing issue (comment + re-attach). Never a create. ---
        key = existing[0].get("key")
        await gateway.add_comment(key, _comment_adf(defect))
        for path in paths:
            await gateway.add_attachment(key, path)
        log.info("defect_filed", action="update", key=key)
        return FileResult(action="update", jira_key=key, counter=run_counter)

    # --- MISS: a CREATE, but only under the per-run cap (T-09-14). ---
    if run_counter >= settings.jira_max_tickets_per_run:
        log.info("defect_cap_reached", fingerprint=defect.fingerprint)
        return FileResult(action="none", jira_key=None, counter=run_counter)

    default_prose = (
        f"Automated test failure classified as {defect.classification} "
        f"({defect.confidence} confidence) in flow {defect.flow_id} (run {defect.run_id})."
    )
    issue = await gateway.create_issue(
        _create_fields(defect, prose=prose or default_prose)
    )
    key = (issue or {}).get("key")
    for path in paths:
        await gateway.add_attachment(key, path)
    # Best-effort traceability link (JIRA-04) — a gateway hiccup never fails the file.
    try:
        await gateway.create_issue_link(
            {
                "type": {"name": "Relates"},
                "inwardIssue": {"key": key},
                "outwardIssue": {"key": key},
            }
        )
    except Exception as exc:  # noqa: BLE001 -- best-effort link; never fail the file
        log.info("defect_issue_link_skipped", error=str(exc))

    log.info("defect_filed", action="create", key=key)
    return FileResult(action="create", jira_key=key, counter=run_counter + 1)


async def run_defect_pipeline(
    db,
    run_id: str,
    flow_id: str,
    *,
    gateway,
    run_counter: int,
) -> tuple[Defect, int]:
    """Post-run orchestrator (DEF-02, called for verdict == 'product_failure' ONLY).

    Persists a Classification row + a draft Defect row (the JIRA-04 run_id/flow_id traceability
    link) for EVERY product-failure classification regardless of cap/autonomy (the cap throttles
    Jira writes, not classification — Pitfall 5). Then, ONLY when may_autofile(confidence) AND the
    class is 'product_defect', auto-files via file_or_update and persists the jira_key + status.

    Returns (defect, run_counter) — the (possibly incremented) counter to thread to the next flow.
    """
    decision = await classify_failure(db, run_id, flow_id)
    classification = decision["classification"]
    confidence = decision["confidence"]
    fingerprint = decision["fingerprint"]

    db.add(
        Classification(
            run_id=run_id,
            flow_id=flow_id,
            classification=classification,
            confidence=confidence,
            evidence=decision["evidence"],
        )
    )
    defect = Defect(
        run_id=run_id,
        flow_id=flow_id,
        classification=classification,
        confidence=confidence,
        fingerprint=fingerprint,
        jira_label=f"fp-{fingerprint}",
        jira_key=None,
        status="draft",
    )
    db.add(defect)
    await db.commit()
    await db.refresh(defect)

    # DASH-06 on-write dual-index (AFTER the draft Defect commit — the row is durable first).
    # Best-effort: index_failure SWALLOWS any ES failure (es_index_skipped), so a down search
    # profile NEVER breaks this Postgres write path (T-10-19). The PG row stays backfillable.
    await index_failure(
        run_id,
        flow_id,
        classification=classification,
        fingerprint=fingerprint,
        confidence=confidence,
        error_text=_failure_error_text(decision.get("evidence")),
    )

    # The draft is now durable. Auto-file ONLY for an enabled+above-threshold product defect.
    if classification == "product_defect" and autonomy.may_autofile(confidence):
        artifacts = [a["path"] for a in (decision["evidence"] or {}).get("artifacts", [])]
        prose, _enriched = await describe(
            db=db,
            evidence={
                "classification": classification,
                "flow": flow_id,
                "step": "",
            },
            run_id=run_id,
        )
        result = await file_or_update(
            gateway, defect, artifacts, run_counter=run_counter, prose=prose
        )
        if result.action in ("create", "update"):
            defect.jira_key = result.jira_key
            defect.status = "applied"
            await db.commit()
            await db.refresh(defect)
        run_counter = result.counter

    return defect, run_counter
