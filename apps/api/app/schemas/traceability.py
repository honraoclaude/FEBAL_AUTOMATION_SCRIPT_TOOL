"""DASH-05 traceability response schemas (mirrors the traceability.chain dict).

BaseModel shapes for GET /api/traceability — the lifecycle chain the viewer renders:
flow ↔ scenario ↔ script ↔ execution ↔ defect, assembled from a single entry artifact id.

Each segment is a LIST (empty = an honest gap the viewer renders as "No {segment} linked.") and the
flow segment is nullable (null = the flow graph is down/absent — never a fabricated node). The
`flow_note` carries the honest degrade reason when the flow segment could not be read. Each segment
item carries its own id + the keys the viewer drills on (run_id/flow_id). Distinct fields from the
dashboards/coverage shapes so the chain shape is never conflated with an aggregate.
"""

from __future__ import annotations

from pydantic import BaseModel


class EntryRef(BaseModel):
    """The picked entry artifact echoed back so the viewer shows what was resolved."""

    type: str | None = None  # flow | scenario | run | defect (None only on an empty echo)
    id: str | None = None


class FlowSegment(BaseModel):
    """The discovered-flow record (best-effort from the graph; the whole segment is nullable)."""

    flow_id: str | None = None
    name: str | None = None
    category: str | None = None
    risk_tier: str | None = None
    step_count: int | None = None


class ScenarioSegment(BaseModel):
    """A generated BDD scenario row in the chain."""

    id: int
    flow_id: str
    run_id: str
    feature_name: str
    status: str


class ScriptSegment(BaseModel):
    """The generated test-project path — CONVENTION-DERIVED from run_id (A4), never a stored column."""

    run_id: str
    path: str
    derived: bool = True


class ExecutionSegment(BaseModel):
    """A per-flow execution result joined to its parent run (tier/status)."""

    run_id: str
    flow_id: str
    verdict: str
    attempts: int
    duration_ms: int | None = None
    tier: str | None = None
    status: str | None = None


class ArtifactSegment(BaseModel):
    """A captured artifact — RUN-RELATIVE path only (the viewer builds the auth-gated URL)."""

    run_id: str
    flow_id: str
    kind: str
    path: str


class DefectSegment(BaseModel):
    """A defect draft/issue in the chain incl. the JIRA-04 jira_key link (nullable until filed)."""

    id: int
    run_id: str
    flow_id: str
    classification: str
    confidence: int
    fingerprint: str
    jira_key: str | None = None
    status: str


class TraceabilityResponse(BaseModel):
    """The assembled lifecycle chain — honest gaps (empty lists / null flow), never fabricated."""

    entry: EntryRef
    flow: FlowSegment | list[FlowSegment] | None = None
    flow_note: str | None = None
    scenarios: list[ScenarioSegment]
    scripts: list[ScriptSegment]
    executions: list[ExecutionSegment]
    artifacts: list[ArtifactSegment]
    defects: list[DefectSegment]
