"""DASH-04 lifecycle coverage — a graph-derived join, DISTINCT from kg/coverage.py.

This metric answers: "of the flows we DISCOVERED, how many have made it all the way through the
lifecycle — i.e. have at least one APPROVED scenario AND at least one PASSING execution?"

It is deliberately a SEPARATE module from `kg/coverage.py` (Pitfall 5). `kg/coverage.py` is the
Phase-5 GROUND-TRUTH exploration metric (matched ground-truth pages ÷ committed fixture). This
module is the lifecycle metric (approved scenario AND passing execution). They share NO code path
and ship DIFFERENT honest definitions so the two numbers are never conflated.

The join (10-RESEARCH Code Examples), mirroring the exec_history.py select/scalars discipline —
no raw SQL, no ORM lazy loads:

    mined          = await mine_flows_from_neo4j(driver=driver)        # the CURRENT graph
    discovered_ids = {f"flow-{i}" for i in range(len(mined["flows"]))} # flows.py positional id
    approved       = distinct Scenario.flow_id WHERE status == 'approved'
    passing        = distinct TestResult.verdict == 'passed' flow ids
    covered        = discovered ∩ approved ∩ passing

flow_id stability caveat (Pitfall 2 / A3): `flow-{i}` is POSITIONAL — it is measured against the
CURRENT mining of the graph, not a stable identity across explorations. We surface that honesty in
the payload (`definition` + `measured_against`) rather than pretending the id is durable.

The verdict vocabulary is passed | flaky | product_failure | aborted — there is NO 'failed'
verdict (CHECKER LOW-1). "Passing" is strictly verdict == 'passed'.

No LLM, no broker. Fixture-testable keyless (mine_flows_from_neo4j is the only graph touch).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution_history import TestResult
from app.models.scenario import Scenario
from app.services.kg.flows import mine_flows_from_neo4j

# The D-02 honest definition shipped IN the payload (never fabricated). A discovered flow is
# "covered" only when BOTH lifecycle conditions hold.
DEFINITION = (
    "Covered = a discovered flow with at least one approved scenario AND at least one passing "
    "execution. Coverage = covered flows ÷ total discovered flows."
)

# The flow_id-positional honesty (A3 / Pitfall 2): the id convention is f"flow-{i}", measured
# against the CURRENT graph mining, not a stable cross-exploration identity.
MEASURED_AGAINST = (
    "Measured against the latest exploration's mined flows; flow ids are positional (flow-{i}) "
    "and are not stable identities across explorations."
)


async def coverage(db: AsyncSession, *, driver=None) -> dict:
    """Graph-derived lifecycle coverage over the CURRENT mined flows.

    Returns a dict carrying the honest definition + the percentage + a per-flow drill-down:
      {
        definition, measured_against,
        total_discovered, covered, coverage_percent (1dp, 0.0 when total==0),
        covered_flow_ids (sorted),
        flows: [{flow_id, has_approved, has_passing, covered}, ...]  (sorted by flow_id)
      }
    """
    mined = await mine_flows_from_neo4j(driver=driver)
    discovered_ids = {f"flow-{i}" for i in range(len(mined["flows"]))}

    # Distinct flows with an APPROVED scenario (the lifecycle "scenario approved" gate).
    approved = set(
        (
            await db.scalars(
                select(Scenario.flow_id).where(Scenario.status == "approved").distinct()
            )
        ).all()
    )
    # Distinct flows with a PASSING execution (verdict == 'passed' — there is no 'failed' verdict).
    passing = set(
        (
            await db.scalars(
                select(TestResult.flow_id).where(TestResult.verdict == "passed").distinct()
            )
        ).all()
    )

    covered_ids = discovered_ids & approved & passing
    total = len(discovered_ids)
    coverage_percent = round(100.0 * len(covered_ids) / total, 1) if total else 0.0

    # Per-flow drill-down for the table — only over DISCOVERED flows (approved/passing on a
    # non-discovered flow does not appear; coverage is discovered-relative).
    flows = [
        {
            "flow_id": fid,
            "has_approved": fid in approved,
            "has_passing": fid in passing,
            "covered": fid in covered_ids,
        }
        for fid in sorted(discovered_ids)
    ]

    return {
        "definition": DEFINITION,
        "measured_against": MEASURED_AGAINST,
        "total_discovered": total,
        "covered": len(covered_ids),
        "coverage_percent": coverage_percent,
        "covered_flow_ids": sorted(covered_ids),
        "flows": flows,
    }
