"""Knowledge-graph read-API response schemas (KG-02 / D-06).

The REAL response models for the read-only KG endpoints in `routers/kg.py` — they
SUPERSEDE the minimal `schemas/stub.py` `FlowSummary`/`FlowsResponse`/`CoverageResponse`
seeds (the Phase-3 501 stubs documented the shape; these carry the genuine fields).

Every field name here MUST stay aligned with the zod schemas in `apps/web/lib/api/kg.ts`
(boundary validation mirrors these Pydantic models). Pydantic remains the server-side
authority; zod is the UX-duplicate at the client boundary.

These models describe READ shapes only — there is no request body on any KG endpoint
(reads are auth-gated GETs), so no input-validation surface beyond path params (V5).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# --- GET /api/flows (KG-04 — mined business journeys + deterministic risk) ----------------


class FlowSchema(BaseModel):
    """One derived business flow with its deterministic risk score + tier (D-04)."""

    flow_id: str
    name: str
    category: str | None = None
    risk_score: int = Field(ge=0, le=100)
    risk_tier: str  # "high" | "medium" | "low"
    step_count: int = Field(ge=0)
    bounded: bool = False
    signals: dict = Field(default_factory=dict)


class FlowsResponse(BaseModel):
    """The list of derived flows, default-sorted by risk descending (the actionable order)."""

    flows: list[FlowSchema]


class FlowStepSchema(BaseModel):
    """One ordered step (page) in a flow's journey."""

    order: int
    fingerprint: str
    title: str | None = None
    url: str | None = None


class FlowDetailSchema(BaseModel):
    """A single flow with its ordered steps + the auditable risk-breakdown signals."""

    flow_id: str
    name: str
    category: str | None = None
    risk_score: int = Field(ge=0, le=100)
    risk_tier: str
    step_count: int = Field(ge=0)
    bounded: bool = False
    steps: list[FlowStepSchema]
    signals: dict = Field(default_factory=dict)


# --- GET /api/coverage (QUAL-01 / D-08 — honest coverage figure) --------------------------


class CoverageResponse(BaseModel):
    """Coverage vs the hand-labeled ground-truth graph.

    `measured` is the HONESTY flag (D-08 / T-05-14): when no graph has been discovered the
    metric is not measurable, so `measured=false` and the UI renders "Not yet measured" —
    NEVER a fabricated 0% / percentage. When a discovered graph exists, `measured=true`
    carries the real `kg/coverage.compute_coverage` percentage vs the ground-truth fixture.
    """

    screens_total: int = Field(ge=0)
    screens_covered: int = Field(ge=0)
    flows_total: int = Field(ge=0)
    flows_covered: int = Field(ge=0)
    coverage_percent: float = Field(ge=0.0, le=100.0)
    measured: bool


# --- GET /api/pages (KG-01 — discovered pages) -------------------------------------------


class PageSchema(BaseModel):
    """One discovered :Page with its freshness + element count."""

    fingerprint: str
    url: str | None = None
    title: str | None = None
    first_seen: str | None = None
    last_verified: str | None = None
    element_count: int = Field(ge=0)


class PagesResponse(BaseModel):
    """The list of discovered pages (the /pages index)."""

    pages: list[PageSchema]


class PageElementRef(BaseModel):
    """A compact element reference inside a page detail (drill-in to element detail)."""

    key: str
    role: str | None = None
    label: str | None = None


class PageFormRef(BaseModel):
    """A compact form reference inside a page detail."""

    key: str


class PageNavRef(BaseModel):
    """An outbound NavigatesTo edge (drill-in to the target page detail)."""

    to: str
    url: str | None = None
    via: str | None = None


class PageDetailSchema(BaseModel):
    """A single page + its elements, forms, and outbound navigation edges."""

    fingerprint: str
    url: str | None = None
    title: str | None = None
    first_seen: str | None = None
    last_verified: str | None = None
    elements: list[PageElementRef]
    forms: list[PageFormRef]
    navigates_to: list[PageNavRef]


# --- GET /api/elements (KG-05 — the Element Repository) -----------------------------------


class LocatorEntry(BaseModel):
    """One prioritized locator-chain entry (data-testid → aria-label → role → text → xpath)."""

    strategy: str
    value: str | None = None
    name: str | None = None


class LocatorHistoryEntry(BaseModel):
    """A prior step-stamped locator snapshot (how a locator changed across runs — KG-05)."""

    step: int | None = None
    chain: list[LocatorEntry] = Field(default_factory=list)


class ElementSchema(BaseModel):
    """One discovered :Element with its prioritized locator chain + history."""

    key: str
    role: str | None = None
    label: str | None = None
    page_fingerprint: str | None = None
    page_url: str | None = None
    locator_chain: list[LocatorEntry] = Field(default_factory=list)
    locator_history: list[LocatorHistoryEntry] = Field(default_factory=list)
    first_seen: str | None = None
    last_verified: str | None = None


class ElementsResponse(BaseModel):
    """The Element Repository — every element + its locator chain/history."""

    elements: list[ElementSchema]


# --- GET /api/graph (KG-01 — label-count summary) ----------------------------------------


class GraphSummaryResponse(BaseModel):
    """Node counts by label for the /graph index, plus a discovered flag (honest empty state)."""

    counts: dict[str, int] = Field(default_factory=dict)
    discovered: bool
