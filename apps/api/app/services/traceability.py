"""DASH-05 traceability — a read-time CROSS-STORE JOIN, distinct from any graph write path.

Given ANY single entry artifact id — a flow_id, a scenario_id, a run_id, or a defect_id — this
service resolves and assembles the full lifecycle chain:

    flow  ↔  scenario  ↔  script  ↔  execution  ↔  defect

by joining the Neo4j discovered-flow set (via kg/flows.mine_flows_from_neo4j — READ only) with the
Postgres lifecycle tables that Phase 9 already FK-linked on run_id + flow_id. It mirrors the
exec_history.get_run_status discipline ("resolve a key → assemble related rows → return a dict") —
SQLAlchemy 2.0 select/scalars, no raw SQL, no ORM lazy loads.

NO NEW GRAPH WRITES (D-03 / 10-RESEARCH Anti-Patterns). reader.py + flows.py both document that
they hold NO write-Cypher; this module joins on READ only and adds NONE. The single-write-path grep
gate (MERGE|CREATE |SET .*=|DELETE) MUST stay green over this file. Lifecycle data is never coupled
into the KG — it is joined at read time and discarded.

HONEST GAPS (T-10-15): every missing chain segment renders as an EXPLICIT empty list / null —
never a fabricated node. An unknown entry id returns the entry echoed with every segment empty
(the "no chain found" honest state, NOT a 500/404 — the router returns it as a 200).

GRAPH-DOWN DEGRADE (T-10-16): the flow segment is best-effort — if the graph is unreachable, flow
is null + a note, and the relational chain still assembles (never a 500 from a down graph).

THE SCRIPT PATH IS CONVENTION-DERIVED (A4 — CONFIRMED): it is NOT a stored column. It is derived
from the Scenario row's run_id via core.workspaces.run_dir — the documented
workspaces/<run_id>/<target>/{pages,steps,features,...} layout. The chain marks it `derived=True`.

No LLM, no broker. Fixture-testable keyless (mine_flows_from_neo4j is the only graph touch).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspaces import run_dir
from app.models.defects import Classification, Defect
from app.models.execution_history import TestArtifact, TestResult, TestRun
from app.models.scenario import Scenario
from app.services.kg.flows import mine_flows_from_neo4j


async def _resolve_keys(
    db: AsyncSession,
    *,
    flow_id: str | None,
    run_id: str | None,
    scenario_id: int | None,
    defect_id: int | None,
) -> tuple[str | None, set[str]]:
    """Resolve (entry_run_id, flow_ids) from whichever single entry id was given.

    Returns the run_id when the entry pins one (scenario/defect/run entries do; a flow_id entry
    does not pin a run) and the set of flow_ids the chain spans. Unknown ids resolve to (None, set())
    so the caller assembles an honest-empty chain.
    """
    if scenario_id is not None:
        row = await db.get(Scenario, scenario_id)
        if row is None:
            return None, set()
        return row.run_id, {row.flow_id}

    if defect_id is not None:
        row = await db.get(Defect, defect_id)
        if row is None:
            return None, set()
        return row.run_id, {row.flow_id}

    if run_id is not None:
        # The distinct flow_ids carried by that run's TestResults (the execution segment's flows).
        flows = set(
            (
                await db.scalars(
                    select(TestResult.flow_id).where(TestResult.run_id == run_id).distinct()
                )
            ).all()
        )
        return run_id, flows

    if flow_id is not None:
        # A flow_id entry does not pin a run — the chain spans every run carrying that flow_id.
        return None, {flow_id}

    return None, set()


async def _flow_segment(flow_ids: set[str], *, driver) -> tuple[list[dict], str | None]:
    """The discovered-flow records (name/steps) for the entry flow_ids — best-effort, READ-only.

    Returns (flows, note). If the graph is unreachable the segment degrades to ([], a note) rather
    than raising — the relational chain still assembles (T-10-16). NEVER fabricates a flow node.
    """
    if not flow_ids:
        return [], None
    try:
        mined = await mine_flows_from_neo4j(driver=driver)
    except Exception as exc:  # noqa: BLE001 — graph-down degrades honestly, never 500s the chain.
        return [], f"Flow graph unavailable; flow segment omitted ({type(exc).__name__})."
    flows = [
        {
            "flow_id": rec.get("id"),
            "name": rec.get("name"),
            "category": rec.get("category"),
            "risk_tier": rec.get("risk_tier"),
            "step_count": rec.get("step_count"),
        }
        for rec in mined.get("flows", [])
        if rec.get("id") in flow_ids
    ]
    return flows, None


async def chain(
    db: AsyncSession,
    *,
    flow_id: str | None = None,
    run_id: str | None = None,
    scenario_id: int | None = None,
    defect_id: int | None = None,
    driver=None,
) -> dict:
    """Assemble the lifecycle chain from a single entry artifact id (READ-only cross-store join).

    Exactly one of flow_id / run_id / scenario_id / defect_id identifies the entry (the router
    enforces "exactly one" — here a None-everywhere call yields an honest-empty chain). Returns:

      {
        "entry": {"type", "id"},
        "flow": {... }|null,                  # best-effort from the graph; null when down/absent
        "flow_note": str|null,                # honest note when the flow segment degraded
        "scenarios": [{id, flow_id, run_id, feature_name, status}, ...],
        "scripts":   [{run_id, path, derived=True}, ...],   # convention-derived (A4), NOT stored
        "executions":[{run_id, flow_id, verdict, attempts, duration_ms, tier, status}, ...],
        "artifacts": [{run_id, flow_id, kind, path}, ...],
        "defects":   [{id, run_id, flow_id, classification, confidence, fingerprint,
                       jira_key, status}, ...],
      }

    Every missing segment is an EXPLICIT empty list / null (honest gap, never a fabricated node).
    """
    entry_type, entry_id = _entry(flow_id, run_id, scenario_id, defect_id)
    resolved_run_id, flow_ids = await _resolve_keys(
        db, flow_id=flow_id, run_id=run_id, scenario_id=scenario_id, defect_id=defect_id
    )

    empty: dict = {
        "entry": {"type": entry_type, "id": entry_id},
        "flow": None,
        "flow_note": None,
        "scenarios": [],
        "scripts": [],
        "executions": [],
        "artifacts": [],
        "defects": [],
    }
    if not flow_ids and resolved_run_id is None:
        # Unknown id / nothing to resolve → the honest "no chain found" state (NOT a 500/404).
        return empty

    # --- flow segment (best-effort, READ-only graph touch) ---
    flows, flow_note = await _flow_segment(flow_ids, driver=driver)
    # The flow segment is a single flow for a single-flow entry, else the set; the viewer renders
    # the matched flow records (or null when none matched / graph down).
    flow = flows[0] if len(flows) == 1 else (flows or None)

    # --- scenarios segment (by flow_id, and run_id when the entry pinned one) ---
    scn_stmt = select(Scenario).where(Scenario.flow_id.in_(flow_ids)) if flow_ids else select(Scenario)
    if resolved_run_id is not None:
        scn_stmt = scn_stmt.where(Scenario.run_id == resolved_run_id)
    scenario_rows = list((await db.scalars(scn_stmt.order_by(Scenario.id))).all())
    scenarios = [
        {
            "id": s.id,
            "flow_id": s.flow_id,
            "run_id": s.run_id,
            "feature_name": s.feature_name,
            "status": s.status,
        }
        for s in scenario_rows
    ]

    # --- scripts segment: the generated test project path is CONVENTION-DERIVED from run_id (A4),
    # NOT a stored column. One derived path per distinct scenario run_id (honest derived=True).
    script_run_ids: list[str] = []
    seen: set[str] = set()
    for s in scenario_rows:
        if s.run_id not in seen:
            seen.add(s.run_id)
            script_run_ids.append(s.run_id)
    scripts = [
        {"run_id": rid, "path": str(run_dir(rid)), "derived": True} for rid in script_run_ids
    ]

    # The run_ids the execution/defect segments span: the pinned entry run plus every scenario run.
    run_ids: set[str] = set(script_run_ids)
    if resolved_run_id is not None:
        run_ids.add(resolved_run_id)

    # --- executions segment: TestResult joined to its parent TestRun (tier/status) by run_id+flow ---
    executions: list[dict] = []
    if run_ids:
        tr_stmt = select(TestResult).where(TestResult.run_id.in_(run_ids))
        if flow_ids:
            tr_stmt = tr_stmt.where(TestResult.flow_id.in_(flow_ids))
        result_rows = list((await db.scalars(tr_stmt.order_by(TestResult.id))).all())
        # Parent TestRun tier/status, looked up once per run_id (small map; no lazy load).
        run_rows = list(
            (await db.scalars(select(TestRun).where(TestRun.run_id.in_(run_ids)))).all()
        )
        run_meta = {r.run_id: (r.tier, r.status) for r in run_rows}
        for r in result_rows:
            tier, status = run_meta.get(r.run_id, (None, None))
            executions.append(
                {
                    "run_id": r.run_id,
                    "flow_id": r.flow_id,
                    "verdict": r.verdict,
                    "attempts": r.attempts,
                    "duration_ms": r.duration_ms,
                    "tier": tier,
                    "status": status,
                }
            )

    # --- artifacts segment: TestArtifact by run_id (+ flow_id) — RUN-RELATIVE path only ---
    artifacts: list[dict] = []
    if run_ids:
        ar_stmt = select(TestArtifact).where(TestArtifact.run_id.in_(run_ids))
        if flow_ids:
            ar_stmt = ar_stmt.where(TestArtifact.flow_id.in_(flow_ids))
        for a in (await db.scalars(ar_stmt.order_by(TestArtifact.id))).all():
            artifacts.append(
                {"run_id": a.run_id, "flow_id": a.flow_id, "kind": a.kind, "path": a.path}
            )

    # --- defects segment: Defect by run_id+flow_id incl. the JIRA-04 jira_key link ---
    defects: list[dict] = []
    if run_ids:
        df_stmt = select(Defect).where(Defect.run_id.in_(run_ids))
        if flow_ids:
            df_stmt = df_stmt.where(Defect.flow_id.in_(flow_ids))
        for d in (await db.scalars(df_stmt.order_by(Defect.id))).all():
            defects.append(
                {
                    "id": d.id,
                    "run_id": d.run_id,
                    "flow_id": d.flow_id,
                    "classification": d.classification,
                    "confidence": d.confidence,
                    "fingerprint": d.fingerprint,
                    "jira_key": d.jira_key,
                    "status": d.status,
                }
            )

    return {
        "entry": {"type": entry_type, "id": entry_id},
        "flow": flow,
        "flow_note": flow_note,
        "scenarios": scenarios,
        "scripts": scripts,
        "executions": executions,
        "artifacts": artifacts,
        "defects": defects,
    }


def _entry(
    flow_id: str | None, run_id: str | None, scenario_id: int | None, defect_id: int | None
) -> tuple[str | None, str | None]:
    """The (type, id) of the entry artifact — echoed back so the viewer shows what was picked."""
    if scenario_id is not None:
        return "scenario", str(scenario_id)
    if defect_id is not None:
        return "defect", str(defect_id)
    if run_id is not None:
        return "run", run_id
    if flow_id is not None:
        return "flow", flow_id
    return None, None
