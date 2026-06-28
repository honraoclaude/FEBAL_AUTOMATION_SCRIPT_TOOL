"""DASH-04 lifecycle-coverage response schemas (mirrors the coverage_dash.coverage dict).

BaseModel shapes for GET /api/coverage/flows. The `definition` + `measured_against` strings ship
the honest, server-authoritative coverage definition (never fabricated on the client). Distinct
from the kg/coverage (ground-truth) shape — different fields so the two metrics never conflate.
"""

from __future__ import annotations

from pydantic import BaseModel


class FlowCoverageRow(BaseModel):
    """One discovered flow's lifecycle-coverage drill-down."""

    flow_id: str
    has_approved: bool
    has_passing: bool
    covered: bool


class CoverageResponse(BaseModel):
    """The lifecycle-coverage payload — honest definition + percentage + per-flow drill-down."""

    definition: str
    measured_against: str
    total_discovered: int
    covered: int
    coverage_percent: float
    covered_flow_ids: list[str]
    flows: list[FlowCoverageRow]
