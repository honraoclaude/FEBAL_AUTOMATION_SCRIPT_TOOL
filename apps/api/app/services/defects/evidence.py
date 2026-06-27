"""Evidence gather (read joins) + classify-over-evidence wiring (DEF-02) — keyless, ORM-only.

DEF-02: classification runs AFTER the Phase-7 retry — the pipeline (Plan 04) calls these helpers
ONLY for verdict == 'product_failure'. This module provides the JOIN + the classify-over-evidence
helper, unit-tested against seeded rows (no real run needed).

gather_evidence(db, run_id, flow_id) reads, all threaded by run_id+flow_id (both already indexed):
  - TestResult.error_text   — the persisted last-attempt error text (the classifier's error-type input);
  - HealAudit row(s)        — the DOM before/after chains + outcome = the healing history (DEF-02 cite);
  - TestArtifact paths      — the screenshot/trace/video evidence the review UI links;
and derives the infra_health signal (pure, over the error text). It returns BOTH the classify()
input dict AND a `cited` snapshot suitable for the classifications.evidence JSON.

classify_failure(db, run_id, flow_id) gathers evidence, runs the PURE classifier, and returns
{classification, confidence, cited, evidence, fingerprint} — the fingerprint built from the class
+ error_text + flow_id + the failing step.

PURITY: reads via the ORM (parameterized — ASVS V5; no string SQL), uses the PASSED-IN session
(never opens its own — the caller/pipeline owns the SessionLocal, the worker/job discipline), and
imports NOTHING from the LLM/gateway path (the test_no_llm_in_classifier gate scans this file).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_history import TestArtifact, TestResult
from app.models.heal_audit import HealAudit
from app.services.defects import classifier as _classifier
from app.services.defects.fingerprint import fingerprint
from app.services.defects.infra_health import infra_health


def _page_loaded(error_text: str, heals: list[HealAudit]) -> bool:
    """Heuristic: the page LOADED unless the error text shows it never reached the target.

    A navigation/connection/timeout-reaching-target signature means the page never loaded; any
    other failure (assertion, locator on a rendered page) implies it did. Pure, over the same
    error text the infra_health signal reads.
    """
    health = infra_health(error_text, page_loaded=None)
    return health != "down"


async def gather_evidence(db: AsyncSession, run_id: str, flow_id: str) -> dict:
    """Assemble the classify() input dict + the cited-evidence snapshot from the joins.

    Returns a dict with the classify() keys (error_text, page_loaded, heal_outcome, infra_health,
    flow_id, step) PLUS a `cited` sub-dict (the full snapshot for classifications.evidence:
    heal chains, artifact paths, the derived signals). Missing rows degrade to falsey, never raise.
    """
    result = (
        await db.scalars(
            select(TestResult)
            .where(TestResult.run_id == run_id, TestResult.flow_id == flow_id)
            .order_by(TestResult.id.desc())
        )
    ).first()
    error_text = (result.error_text if result else None) or ""
    verdict = result.verdict if result else None

    heals = list(
        await db.scalars(
            select(HealAudit)
            .where(HealAudit.run_id == run_id, HealAudit.flow_id == flow_id)
            .order_by(HealAudit.id.asc())
        )
    )
    # The healing history: the most recent heal outcome is the classifier's automation signal.
    heal_outcome = heals[-1].outcome if heals else None

    artifacts = list(
        await db.scalars(
            select(TestArtifact)
            .where(TestArtifact.run_id == run_id, TestArtifact.flow_id == flow_id)
            .order_by(TestArtifact.id.asc())
        )
    )

    page_loaded = _page_loaded(error_text, heals)
    health = infra_health(error_text, page_loaded=page_loaded)
    # The failing step is the most recent heal's element key when present, else a flow-scoped marker
    # (the fingerprint just needs a stable per-step discriminator; the worker has no step index here).
    step = heals[-1].element_key if heals else "flow"

    return {
        # --- the classify() input keys ---
        "error_text": error_text,
        "page_loaded": page_loaded,
        "heal_outcome": heal_outcome,
        "infra_health": health,
        "flow_id": flow_id,
        "step": step,
        # --- the full cited-evidence snapshot for classifications.evidence JSON (DEF-02) ---
        "cited": {
            "verdict": verdict,
            "error_text": error_text,
            "infra_health": health,
            "page_loaded": page_loaded,
            "heal_history": [
                {
                    "element_key": h.element_key,
                    "outcome": h.outcome,
                    "before_chain": h.before_chain,
                    "after_chain": h.after_chain,
                    "confidence": h.confidence,
                }
                for h in heals
            ],
            "artifacts": [{"kind": a.kind, "path": a.path} for a in artifacts],
        },
    }


async def classify_failure(db: AsyncSession, run_id: str, flow_id: str) -> dict:
    """Gather evidence -> PURE classify -> fingerprint. Returns the full decision record.

    {classification, confidence, cited, evidence, fingerprint}. The fingerprint is built from the
    class + error_text + flow_id + failing step (D-05). No LLM, no spend — the decision is keyless.
    """
    evidence = await gather_evidence(db, run_id, flow_id)
    decision = _classifier.classify(evidence)
    fp = fingerprint(
        decision["classification"],
        evidence["error_text"],
        flow_id,
        evidence["step"],
    )
    return {
        "classification": decision["classification"],
        "confidence": decision["confidence"],
        "cited": decision["cited"],
        "evidence": evidence["cited"],
        "fingerprint": fp,
    }
