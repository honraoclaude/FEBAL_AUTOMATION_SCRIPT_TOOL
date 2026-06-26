"""/api/heals — the MINIMAL auth-gated quarantine review API (D-05 — API ONLY, no UI).

Exposes the heal_audit ledger (Plan 03) for reporting + review. NO heal screen / dashboard is
built here (the rich quarantine review SCREEN + heal-trend charts are DEFERRED to Phase 10 — this
plan persists + exposes only). The four endpoints, all auth-gated at the router level:

  - GET  /api/heals?status=quarantined  -> list[HealAuditResponse]  (the quarantine queue with the
        before/after diff + confidence served straight off the audit record, HEAL-03 review).
  - POST /api/heals/{heal_id}/apply     -> promote a quarantined proposal to a heal: perform the
        DEFERRED page-object rewrite (the rewrite was STAGED, not written, for quarantine in Plan
        03 — Open Q3) + append the KG Element history (best-effort), then set outcome='applied'.
  - POST /api/heals/{heal_id}/reject    -> mark the row a FALSE heal (reviewed_outcome='rejected',
        the HEAL-04 false-heal signal). Quarantine wrote no file, so reject is a flag flip.
  - GET  /api/heals/stats?element=<key> -> list[HealStatsResponse] via per_element_heal_stats (the
        per-element heal-success + false-heal rates, HEAL-04).

AUTH (T-08-18, RESEARCH A6): the router-level Depends(get_current_user) gates EVERY endpoint —
especially the STATE-CHANGING apply/reject (state-changing endpoints are NEVER public, V4). An
unauthenticated request -> 401. `require_role` does NOT exist (no 4-role DI yet) — reuse
get_current_user, do NOT invent role enforcement here.

SECURITY: heal_id is an int PK + element is a string filter, both bound via the SQLAlchemy ORM —
parameterized, no string-built SQL (T-08-19/V5). apply reuses the SAME ast-validated page-object
rewrite path from Plan 03 (healing.ingest._apply_page_object_rewrite — a non-parsing rewrite
RAISES, never persisted, T-08-20), and the KG write-back routes through the single writer
(kg/writer.append_element_history, parameterized + read-back guarded, T-08-21). pages_dir is
run_id-derived (run_dir(heal.run_id)/target/pages), NEVER a path from the request body.
"""

from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.core.workspaces import run_dir
from app.db.session import get_db
from app.models.heal_audit import HealAudit
from app.schemas.heal import HealAuditResponse, HealStatsResponse
from app.services.healing import ingest
from app.services.healing.stats import per_element_heal_stats

log = structlog.get_logger()

# The ingest layout: project_root = run_dir(run_id)/"target", pages live under project_root/pages
# (mirrors test_heal_ingest._plant + ingest_heal_journal's project_root contract).
_PROJECT_SUBDIR = "target"

router = APIRouter(
    prefix="/api/heals",
    tags=["heals"],
    # Router-level gate: EVERY endpoint (incl. the state-changing apply/reject) is auth-gated.
    # get_current_user 401s an unauthenticated request before any handler runs (T-08-18, A6).
    dependencies=[Depends(get_current_user)],
)

_NOT_FOUND = "No heal_audit row found for this id"


@router.get("", response_model=list[HealAuditResponse])
async def list_heals(
    status: str = "quarantine", db: AsyncSession = Depends(get_db)
) -> list[HealAudit]:
    """The heals filtered by outcome (default 'quarantine') — the review queue with diff+confidence.

    `status` is matched against the `outcome` column via the ORM (parameterized — V5); the default
    'quarantine' surfaces the proposals awaiting apply/reject (the audit vocabulary value, NOT the
    past-tense 'quarantined' — the column stores 'quarantine'). Newest-first (created_at desc).
    """
    rows = (
        await db.scalars(
            select(HealAudit)
            .where(HealAudit.outcome == status)
            .order_by(HealAudit.created_at.desc(), HealAudit.id.desc())
        )
    ).all()
    return list(rows)


async def _get_heal_or_404(db: AsyncSession, heal_id: int) -> HealAudit:
    """Load a HealAudit by int PK (ORM-parameterized) or raise 404 (unknown id)."""
    heal = await db.get(HealAudit, heal_id)
    if heal is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return heal


@router.post("/{heal_id}/apply", response_model=HealAuditResponse)
async def apply_heal(heal_id: int, db: AsyncSession = Depends(get_db)) -> HealAudit:
    """Promote a quarantined heal: perform the DEFERRED page-object rewrite + KG append, set applied.

    Reuses the SAME ast-validated rewrite path Plan 03 uses for auto_heal
    (ingest._apply_page_object_rewrite — a non-parsing rewrite RAISES, never persists, T-08-20) on
    the run's pages dir (run_id-derived, NEVER a request path). The KG Element history is appended
    best-effort through the single writer (T-08-21). The audit row's outcome flips to 'applied'.
    404 on an unknown heal_id.
    """
    heal = await _get_heal_or_404(db, heal_id)

    after_chain = heal.after_chain or []
    pages_dir = run_dir(heal.run_id) / _PROJECT_SUBDIR / "pages"
    if after_chain:
        # The deferred rewrite (STAGED for quarantine in Plan 03, applied here). Reuse the Plan-03
        # ast-validated helper verbatim — do NOT reimplement (T-08-20). Tolerant of a missing
        # module / non-parsing rewrite (logged + skipped inside the helper).
        ingest._apply_page_object_rewrite(
            pages_dir, element_key=heal.element_key, after_chain=after_chain
        )
        # Best-effort KG write-back via the single writer (a down neo4j never fails the apply).
        await ingest._append_kg_history(
            {
                "element_key": heal.element_key,
                "after_chain": after_chain,
                "before_chain": heal.before_chain,
            },
            driver=None,
            now=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    heal.outcome = "applied"
    await db.commit()
    await db.refresh(heal)
    log.info("heal_applied", heal_id=heal_id, element_key=heal.element_key)
    return heal


@router.post("/{heal_id}/reject", response_model=HealAuditResponse)
async def reject_heal(heal_id: int, db: AsyncSession = Depends(get_db)) -> HealAudit:
    """Mark a heal a FALSE heal: set reviewed_outcome='rejected' (the HEAL-04 false-heal signal).

    Quarantine STAGED the proposal in the audit row and wrote NO file (Plan 03 Open Q3), so reject
    is a no-op flag flip — there is nothing to revert. 404 on an unknown heal_id.
    """
    heal = await _get_heal_or_404(db, heal_id)
    heal.reviewed_outcome = "rejected"
    await db.commit()
    await db.refresh(heal)
    log.info("heal_rejected", heal_id=heal_id, element_key=heal.element_key)
    return heal


@router.get("/stats", response_model=list[HealStatsResponse])
async def heal_stats(
    element: str | None = None, db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Per-element heal-success + false-heal rates (HEAL-04) via per_element_heal_stats.

    `element` (a string filter, ORM-bound — V5) narrows to one element; omitted returns every
    element with at least one heal attempt (zero-attempt elements are absent — no divide-by-zero).
    """
    return await per_element_heal_stats(db, element_key=element)
