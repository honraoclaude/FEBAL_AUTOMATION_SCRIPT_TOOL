"""Dashboard aggregation response schemas (DASH-01/02/03) — mirrors the dashboards.* dicts.

BaseModel shapes for GET /api/dashboards/{executive,qa,developer}. Reuses CoverageResponse
(DASH-04) for the executive coverage tile and TestRunResponse (ORM-readable, from_attributes) for
the QA run history. Every field renders from the server payload — no client fabrication.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.schemas.coverage_dash import CoverageResponse
from app.schemas.execution import TestRunResponse


# --- shared trend/row primitives --------------------------------------------------------------


class PassRatePoint(BaseModel):
    """One per-day pass-rate point (pass_rate is 0..1; the executive KPI exposes the % form)."""

    day: str | None
    pass_rate: float
    total: int
    passed: int


class CountPoint(BaseModel):
    """One per-day count point (defects filed / errors classified)."""

    day: str | None
    count: int


# --- executive (DASH-01) ----------------------------------------------------------------------


class ExecutiveKpis(BaseModel):
    pass_rate_percent: float  # the latest day's pass rate as a 0..100 PERCENT (LOW-2 ×100 point)
    open_defects: int


class ExecutiveDashboard(BaseModel):
    coverage: CoverageResponse
    pass_rate_trend: list[PassRatePoint]
    defects_trend: list[CountPoint]
    kpis: ExecutiveKpis


# --- qa (DASH-02) -----------------------------------------------------------------------------


class ArtifactRef(BaseModel):
    """A RUN-RELATIVE artifact reference (kind + stored path; never an absolute fs path)."""

    kind: str
    path: str


class FailedTest(BaseModel):
    run_id: str
    flow_id: str
    verdict: str
    attempts: int
    error_text: str | None
    artifacts: list[ArtifactRef]


class QaDashboard(BaseModel):
    runs: list[TestRunResponse]
    failed_tests: list[FailedTest]


# --- developer (DASH-03) ----------------------------------------------------------------------


class RootCauseGroup(BaseModel):
    classification: str
    fingerprint: str
    count: int
    rep_defect_id: int


class ModuleFailure(BaseModel):
    flow_id: str
    failure_count: int


class DeveloperDashboard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    root_cause_groups: list[RootCauseGroup]
    errors_trend: list[CountPoint]
    module_breakdown: list[ModuleFailure]
