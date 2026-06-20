"""Scenario review-queue router (GEN-02 / D-01..D-04) — the approve/edit review step.

The auth-gated review API that sits BETWEEN generation (Slice 1) and codegen (Slice 3):

  GET  /api/scenarios?status=draft      list the queue (default drafts), each row carrying its
                                        source-flow risk (honest None when the flow is unscored)
  GET  /api/scenarios/{id}              one scenario + the HONEST per-Then no-vacuous results
                                        (computed server-side from resolve_then_refs — D-03)
  POST /api/scenarios/{id}/edit         edit-in-place: re-run BOTH gates on the body; 422 + NO
                                        save on failure; on pass update_gherkin (edited, draft)
  POST /api/scenarios/{id}/approve      re-run BOTH gates (defense-in-depth); set approved only
                                        on pass, else 422
  POST /api/scenarios/{id}/reject       set rejected (no gates — rejecting never needs quality)

INVARIANTS (carried from Slice 1 + the threat model):
  - T-06-07: router-level Depends(get_current_user) — NO endpoint is reachable unauthenticated.
  - T-06-08 / D-02 / D-04: edit AND approve both re-run validate_gherkin THEN assert_non_vacuous;
    a failing edit returns 422 and saves nothing (the row stays draft). An edited scenario
    cannot bypass quality.
  - T-06-10 / D-03: the per-Then results render strictly from the server's resolution — green
    only when the gate confirmed it; the client never fabricates a "Resolved".
  - T-06-11 / D-01: only status=approved scenarios feed codegen (scenario_service.list_approved
    enforces it in SQL).
  - Read-only Cypher in the gate (T-06-09, inherited); the request db session per convention;
    GenerationError → HTTPException(422) exactly like generate.py.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.scenario import Scenario
from app.schemas.scenario import (
    ScenarioDetail,
    ScenarioSummary,
    ThenRefResult,
)
from app.schemas.scenario import EditRequest
from app.services import scenario_service
from app.services.gates.assertion_gate import assert_non_vacuous, resolve_then_refs
from app.services.gates.gherkin_lint import GenerationError, validate_gherkin
from app.services.kg import flows as kg_flows
from app.services.kg import reader as kg_reader

router = APIRouter(
    prefix="/api",
    tags=["scenarios"],
    # Router-level auth gate: NO scenario endpoint is reachable unauthenticated (T-06-07, V2/V4).
    dependencies=[Depends(get_current_user)],
)

# A stable synthetic run_id for the read-surface flow categorization spend (mirrors kg.py).
_READ_RUN_ID = "scenario-read"

# Risk is BEST-EFFORT UI enrichment, not core to any mutation's success. The graph profile is
# optional (the api boots without neo4j); a Bolt connect against a down graph can block until a
# connection timeout, so cap the risk lookup so reject/edit/approve never hang on a down graph.
_RISK_TIMEOUT_S = 3.0


async def _flow_risk_index() -> dict[str, dict]:
    """Map flow_id -> {risk_score, risk_tier} from the live graph (honest empty when unscored).

    Reuses the same mine+score path as the KG /flows surface. If the graph is unreachable, no
    flows mine, or the lookup exceeds _RISK_TIMEOUT_S, the index is empty and every row's risk
    is honestly None — the mutation/read still completes (risk is enrichment, never blocking).
    """
    try:
        graph = await asyncio.wait_for(kg_reader.flows_source(), timeout=_RISK_TIMEOUT_S)
        records = await asyncio.wait_for(
            kg_flows.build_flows(graph, _READ_RUN_ID), timeout=_RISK_TIMEOUT_S
        )
    except Exception:  # noqa: BLE001 -- graph down/slow/not discovered → honest None risk
        return {}
    return {
        rec["id"]: {"risk_score": rec.get("risk_score"), "risk_tier": rec.get("risk_tier")}
        for rec in records
    }


def _summary(row: Scenario, risk: dict[str, dict]) -> ScenarioSummary:
    r = risk.get(row.flow_id, {})
    return ScenarioSummary(
        id=row.id,
        run_id=row.run_id,
        flow_id=row.flow_id,
        feature_name=row.feature_name,
        status=row.status,
        edited=row.edited,
        stale=row.stale,
        flow_risk_score=r.get("risk_score"),
        flow_risk_tier=r.get("risk_tier"),
        updated_at=row.updated_at,
    )


def _kg_ref_label(entry: dict) -> str | None:
    """A human-readable mono caption for a resolved Then's KG target (D-03 display)."""
    kind = (entry or {}).get("kind")
    ref = (entry or {}).get("ref") or {}
    if kind == "edge":
        return f"{ref.get('edge_type')} → {ref.get('entity')}"
    if kind == "element":
        return f"element: {ref.get('element_key')}"
    if kind == "page":
        return f"page: {ref.get('page_fingerprint') or ref.get('page_url')}"
    return None


def _vacuous_reason(entry: dict) -> str:
    """The honest reason a Then is vacuous (named in the UI's red caption)."""
    kind = (entry or {}).get("kind")
    ref = (entry or {}).get("ref") or {}
    if kind not in {"edge", "element", "page"}:
        return "unknown assertion kind"
    if kind == "edge" and not (ref.get("edge_type") and ref.get("entity")):
        return "no graph-backed outcome"
    if kind == "element" and not ref.get("element_key"):
        return "no graph-backed outcome"
    if kind == "page" and not (ref.get("page_fingerprint") or ref.get("page_url")):
        return "no graph-backed outcome"
    return "ref not found in graph"


async def _then_results(then_refs: list) -> list[ThenRefResult]:
    """Compute the HONEST per-Then results from the server's no-vacuous resolution (D-03).

    Runs resolve_then_refs once (the authoritative gate read) to get the vacuous Then texts,
    then maps each entry to resolved/kg_ref or vacuous/reason. The client renders strictly
    from this — green requires the server to have confirmed resolution.

    HONESTY when the graph is unreachable (T-06-10): the gate cannot confirm ANY resolution, so
    every Then is reported NOT resolved (never a fabricated green) with a graph-unreachable
    reason — and the call degrades fast (a bounded wait) instead of hanging on a down Bolt.
    """
    try:
        unresolved = set(
            await asyncio.wait_for(resolve_then_refs(then_refs or []), timeout=_RISK_TIMEOUT_S)
        )
    except Exception:  # noqa: BLE001 -- graph down/slow → honestly report all as unresolved
        return [
            ThenRefResult(
                then_text=(entry or {}).get("then_text", ""),
                resolved=False,
                reason="knowledge graph unreachable",
            )
            for entry in then_refs or []
        ]
    results: list[ThenRefResult] = []
    for entry in then_refs or []:
        then_text = (entry or {}).get("then_text", "")
        if then_text in unresolved:
            results.append(
                ThenRefResult(
                    then_text=then_text, resolved=False, reason=_vacuous_reason(entry)
                )
            )
        else:
            results.append(
                ThenRefResult(
                    then_text=then_text, resolved=True, kg_ref=_kg_ref_label(entry)
                )
            )
    return results


async def _require_scenario(db: AsyncSession, scenario_id: int) -> Scenario:
    row = await scenario_service.get(db, scenario_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No scenario found for this id")
    return row


@router.get("/scenarios", response_model=list[ScenarioSummary])
async def list_scenarios(
    status: str = Query(default="draft"),
    db: AsyncSession = Depends(get_db),
) -> list[ScenarioSummary]:
    """List review-queue scenarios (default drafts), each with its source-flow risk.

    `status=all` lists every row; any other value filters to that status. The risk index is
    computed once per request and attached per row (honest None when the flow is unscored).
    """
    filter_status = None if status == "all" else status
    rows = await scenario_service.list_scenarios(db, status=filter_status)
    risk = await _flow_risk_index()
    return [_summary(row, risk) for row in rows]


@router.get("/scenarios/{scenario_id}", response_model=ScenarioDetail)
async def get_scenario(
    scenario_id: int, db: AsyncSession = Depends(get_db)
) -> ScenarioDetail:
    """One scenario + the HONEST per-Then no-vacuous results (server-authoritative, D-03)."""
    row = await _require_scenario(db, scenario_id)
    risk = await _flow_risk_index()
    summary = _summary(row, risk)
    return ScenarioDetail(
        **summary.model_dump(),
        gherkin_text=row.gherkin_text,
        then_results=await _then_results(row.then_refs or []),
    )


def _detail(row: Scenario, risk: dict[str, dict], then_results: list[ThenRefResult]) -> ScenarioDetail:
    summary = _summary(row, risk)
    return ScenarioDetail(
        **summary.model_dump(),
        gherkin_text=row.gherkin_text,
        then_results=then_results,
    )


@router.post("/scenarios/{scenario_id}/edit", response_model=ScenarioDetail)
async def edit_scenario(
    scenario_id: int, body: EditRequest, db: AsyncSession = Depends(get_db)
) -> ScenarioDetail:
    """Edit-in-place: re-run BOTH gates on the body; 422 + NO save on failure (D-02 / D-04).

    On pass: update_gherkin (edited=True, stays draft) and return the fresh ScenarioDetail with
    the recomputed honest per-Then results. On gate failure: GenerationError → 422, the row is
    NOT touched (status + text unchanged), and the editor keeps the reviewer's text.
    """
    await _require_scenario(db, scenario_id)
    # Re-run BOTH gates BEFORE any write — an edited scenario cannot bypass quality (D-04).
    try:
        validate_gherkin(body.gherkin_text)
        await assert_non_vacuous(body.then_refs)
    except GenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    row = await scenario_service.update_gherkin(
        db, scenario_id, body.gherkin_text, body.then_refs
    )
    risk = await _flow_risk_index()
    return _detail(row, risk, await _then_results(row.then_refs or []))


@router.post("/scenarios/{scenario_id}/approve", response_model=ScenarioDetail)
async def approve_scenario(
    scenario_id: int, db: AsyncSession = Depends(get_db)
) -> ScenarioDetail:
    """Approve: re-run BOTH gates (defense-in-depth) → status=approved only on pass, else 422."""
    row = await _require_scenario(db, scenario_id)
    try:
        validate_gherkin(row.gherkin_text)
        await assert_non_vacuous(row.then_refs or [])
    except GenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    row = await scenario_service.set_status(db, scenario_id, "approved")
    risk = await _flow_risk_index()
    return _detail(row, risk, await _then_results(row.then_refs or []))


@router.post("/scenarios/{scenario_id}/reject", response_model=ScenarioDetail)
async def reject_scenario(
    scenario_id: int, db: AsyncSession = Depends(get_db)
) -> ScenarioDetail:
    """Reject: set status=rejected (rejecting never needs the quality gates)."""
    await _require_scenario(db, scenario_id)
    row = await scenario_service.set_status(db, scenario_id, "rejected")
    risk = await _flow_risk_index()
    return _detail(row, risk, await _then_results(row.then_refs or []))
