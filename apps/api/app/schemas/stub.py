"""Honest-stub contracts (PLAT-02) — the EVENTUAL request/response shapes for the 5
not-yet-built PLAT-02 endpoints.

These Pydantic models exist so the OpenAPI schema is COMPLETE even though the endpoints
return 501: the surface documents WHAT each endpoint will accept and return, while the
handlers never fabricate a result (CONTEXT discretion + RESEARCH anti-pattern — a stub
returns 501, never a plausible-but-fake payload). Each model is minimal but representative
of the phase that implements it (heal=Phase 8, create-defect=Phase 9, flows=Phase 5,
coverage=Phase 10, dashboard=Phase 10).
"""

from pydantic import BaseModel, Field

# --- POST /api/heal (Phase 8 — locator self-healing) -------------------------------------


class HealRequest(BaseModel):
    """Request a self-heal of a broken locator for a failing step (Phase 8 shape)."""

    run_id: str = Field(min_length=1)
    spec_path: str = Field(min_length=1)
    failing_selector: str = Field(min_length=1)


class HealResponse(BaseModel):
    """The healed-locator proposal + audit fields (Phase 8 shape)."""

    run_id: str
    original_selector: str
    healed_selector: str
    confidence: float = Field(ge=0.0, le=100.0)
    applied: bool


# --- POST /api/create-defect (Phase 9 — auto-file a Jira defect) --------------------------


class CreateDefectRequest(BaseModel):
    """Request creation of a Jira defect from a classified failure (Phase 9 shape)."""

    run_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    description: str = Field(min_length=1)
    classification: str = Field(min_length=1)


class CreateDefectResponse(BaseModel):
    """The created Jira issue reference (Phase 9 shape)."""

    run_id: str
    issue_key: str
    issue_url: str
    draft: bool


# --- GET /api/flows (Phase 5 — learned business flows from the KG) ------------------------


class FlowSummary(BaseModel):
    """One learned business flow (Phase 5 shape)."""

    flow_id: str
    name: str
    step_count: int


class FlowsResponse(BaseModel):
    """The list of learned flows discovered in the knowledge graph (Phase 5 shape)."""

    flows: list[FlowSummary]


# --- GET /api/coverage (Phase 10 — coverage metrics) -------------------------------------


class CoverageResponse(BaseModel):
    """Aggregate coverage metrics for the dashboard (Phase 10 shape)."""

    screens_total: int
    screens_covered: int
    flows_total: int
    flows_covered: int
    coverage_percent: float = Field(ge=0.0, le=100.0)


# --- GET /api/dashboard (Phase 10 — role-based dashboard rollup) --------------------------


class DashboardResponse(BaseModel):
    """The top-level dashboard rollup (Phase 10 shape)."""

    total_runs: int
    pass_rate: float = Field(ge=0.0, le=100.0)
    open_defects: int
    healing_success_rate: float = Field(ge=0.0, le=100.0)
    classification_confidence: float = Field(ge=0.0, le=100.0)
