"""Read-only knowledge-graph API (KG-02 / D-06) — the REAL /flows + /coverage + /graph.

This router makes the Phase-3 `GET /flows` + `GET /coverage` 501 stubs real and adds
`GET /graph` / `/pages` / `/elements` (+ drill-in detail routes). The shape mirrors
`routers/executions.py`: a read-only router with a ROUTER-LEVEL `Depends(get_current_user)`
auth gate (V4 / T-05-09 — no KG data is reachable unauthenticated; an unauthenticated
request gets 401 before any handler runs). RBAC roles arrive in Phase 10.

ON-DEMAND computation (RESEARCH Open Q3): flows/coverage/graph are computed at request
time from the live graph via `kg/reader` + the pure `kg/flows` miner — no write happens
on a read (the single-write-path grep gate stays green; all writes go through kg/writer).

Coverage: slice 4 wires the real ground-truth metric. Until then this returns the HONEST
`measured=false` shape so the UI renders "Not yet measured" — never a fabricated percent
(D-08). `routers/kg.py` + `schemas/kg.py` are created here and EXTENDED by 05-04 (which
swaps the coverage stub for the real `kg/coverage.py` computation).

Every query is read-only and parameterized (the reader owns the Cypher; labels/edge types
are code constants, never interpolated from page-derived text — T-05-08 / V5).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.schemas.kg import (
    CoverageResponse,
    ElementSchema,
    ElementsResponse,
    FlowDetailSchema,
    FlowSchema,
    FlowsResponse,
    FlowStepSchema,
    GraphSummaryResponse,
    PageDetailSchema,
    PageElementRef,
    PageFormRef,
    PageNavRef,
    PagesResponse,
    PageSchema,
)
from app.services.kg import flows as kg_flows
from app.services.kg import reader as kg_reader

router = APIRouter(
    prefix="/api",
    tags=["kg"],
    # Router-level auth gate: NO KG read is reachable unauthenticated (T-05-09, V4).
    dependencies=[Depends(get_current_user)],
)

# On-demand flow categorization is metered per-run through the gateway; reads use a stable
# synthetic run_id so the budget/usage ledger attributes the categorization spend to the
# read surface (deterministic no-key fallback means flows still render without a provider key).
_READ_RUN_ID = "kg-read"


# --- Flows (KG-04) -----------------------------------------------------------------------


async def _build_sorted_flows() -> list[dict]:
    """Mine + score + categorize flows from the live graph, sorted by risk descending."""
    graph = await kg_reader.flows_source()
    records = await kg_flows.build_flows(graph, _READ_RUN_ID)
    records.sort(key=lambda r: r["risk_score"], reverse=True)
    return records


def _flow_schema(rec: dict) -> FlowSchema:
    return FlowSchema(
        flow_id=rec["id"],
        name=rec["name"],
        category=rec.get("category"),
        risk_score=rec["risk_score"],
        risk_tier=rec["risk_tier"],
        step_count=rec["step_count"],
        bounded=rec.get("bounded", False),
        signals=rec.get("signals", {}),
    )


@router.get("/flows", response_model=FlowsResponse)
async def flows() -> FlowsResponse:
    """Derived business flows with deterministic risk scores, default-sorted risk-desc."""
    records = await _build_sorted_flows()
    return FlowsResponse(flows=[_flow_schema(r) for r in records])


@router.get("/flows/{flow_id}", response_model=FlowDetailSchema)
async def flow_detail(flow_id: str) -> FlowDetailSchema:
    """A single flow with its ordered steps + the auditable risk-breakdown signals."""
    graph = await kg_reader.flows_source()
    records = await kg_flows.build_flows(graph, _READ_RUN_ID)
    rec = next((r for r in records if r["id"] == flow_id), None)
    if rec is None:
        raise HTTPException(status_code=404, detail="No flow found for this id")
    nodes = graph.get("nodes", {})
    steps = [
        FlowStepSchema(
            order=i,
            fingerprint=fp,
            title=nodes.get(fp, {}).get("label") or None,
            url=nodes.get(fp, {}).get("url") or None,
        )
        for i, fp in enumerate(rec.get("node_fps", []))
    ]
    return FlowDetailSchema(
        flow_id=rec["id"],
        name=rec["name"],
        category=rec.get("category"),
        risk_score=rec["risk_score"],
        risk_tier=rec["risk_tier"],
        step_count=rec["step_count"],
        bounded=rec.get("bounded", False),
        steps=steps,
        signals=rec.get("signals", {}),
    )


# --- Coverage (QUAL-01 / D-08 — honest until slice 4 wires the real metric) ---------------


@router.get("/coverage", response_model=CoverageResponse)
async def coverage() -> CoverageResponse:
    """Coverage vs the ground-truth graph.

    Slice 4 replaces this body with the real `kg/coverage.py` computation. Until then it
    returns the HONEST not-yet-measured shape (`measured=false`, zeros) so the UI shows
    "Not yet measured" rather than a fabricated 0% (D-08). The response MODEL is final —
    slice 4 only changes the computed values + the `measured` flag.
    """
    return CoverageResponse(
        screens_total=0,
        screens_covered=0,
        flows_total=0,
        flows_covered=0,
        coverage_percent=0.0,
        measured=False,
    )


# --- Graph summary (KG-01) ---------------------------------------------------------------


@router.get("/graph", response_model=GraphSummaryResponse)
async def graph() -> GraphSummaryResponse:
    """Node counts by label for the /graph index (+ a discovered flag for the empty state)."""
    counts = await kg_reader.graph_summary()
    return GraphSummaryResponse(counts=counts, discovered=bool(counts))


# --- Pages (KG-01) -----------------------------------------------------------------------


@router.get("/pages", response_model=PagesResponse)
async def pages() -> PagesResponse:
    """All discovered pages with freshness + element count."""
    rows = await kg_reader.list_pages()
    return PagesResponse(
        pages=[
            PageSchema(
                fingerprint=r["fingerprint"],
                url=r.get("url"),
                title=r.get("title"),
                first_seen=r.get("first_seen"),
                last_verified=r.get("last_verified"),
                element_count=int(r.get("element_count") or 0),
            )
            for r in rows
        ]
    )


@router.get("/pages/{fingerprint}", response_model=PageDetailSchema)
async def page_detail(fingerprint: str) -> PageDetailSchema:
    """A single page + its elements, forms, and outbound NavigatesTo edges."""
    row = await kg_reader.page_detail(fingerprint)
    if row is None:
        raise HTTPException(status_code=404, detail="No page found for this fingerprint")
    return PageDetailSchema(
        fingerprint=row["fingerprint"],
        url=row.get("url"),
        title=row.get("title"),
        first_seen=row.get("first_seen"),
        last_verified=row.get("last_verified"),
        elements=[
            PageElementRef(key=e["key"], role=e.get("role"), label=e.get("label"))
            for e in row.get("elements", [])
        ],
        forms=[PageFormRef(key=f["key"]) for f in row.get("forms", [])],
        navigates_to=[
            PageNavRef(to=n["to"], url=n.get("url"), via=n.get("via"))
            for n in row.get("navigates_to", [])
        ],
    )


# --- Element Repository (KG-05) ----------------------------------------------------------


def _element_schema(row: dict) -> ElementSchema:
    return ElementSchema(
        key=row["key"],
        role=row.get("role"),
        label=row.get("label"),
        page_fingerprint=row.get("page_fp"),
        page_url=row.get("page_url"),
        locator_chain=row.get("chain", []),
        locator_history=row.get("history", []),
        first_seen=row.get("first_seen"),
        last_verified=row.get("last_verified"),
    )


@router.get("/elements", response_model=ElementsResponse)
async def elements() -> ElementsResponse:
    """The Element Repository — every element + its prioritized locator chain + history."""
    rows = await kg_reader.element_repository()
    return ElementsResponse(elements=[_element_schema(r) for r in rows])


@router.get("/elements/{key:path}", response_model=ElementSchema)
async def element_detail(key: str) -> ElementSchema:
    """A single element's locator chain + history (key may contain '#' / slashes)."""
    row = await kg_reader.element_detail(key)
    if row is None:
        raise HTTPException(status_code=404, detail="No element found for this key")
    return _element_schema(row)
