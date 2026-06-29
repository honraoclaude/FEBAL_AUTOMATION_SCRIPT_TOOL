"""/api/search — the DASH-06 full-text search endpoint (role-gated).

GET /api/search?q=...&index=... runs a parameterized multi_match + highlight over the
executions/failures/logs Elasticsearch indices and returns ranked, highlighted hits.

Role-gated per the rbac.py endpoint→role matrix: ALL authenticated roles (admin, qa_lead,
qa_engineer, developer) may search — they search what they may read; the per-row drill links
respect each surface's own gate. An unauthenticated request → 401 (require_role / get_current_user).

GRACEFUL-DEGRADE (T-10-20): when ES is down the underlying query raises
`elasticsearch.exceptions.ConnectionError`, which the main.py `@app.exception_handler` turns into an
honest 503 "Search is unavailable…". The router does NOT catch it and does NOT return a fake empty
list — an outage is surfaced honestly, never disguised as zero results.

INJECTION (T-10-17): `q` is forwarded as a structured VALUE into the multi_match query in
services/search/query.py — never concatenated into the DSL.

ROUTER-ORDERING: this router exposes ONLY the static `GET ""` with query params — no typed `/{id}`
path converter, so no static-before-typed ordering hazard (the defects.py /calibration lesson).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.security import require_role
from app.schemas.search import SearchHit, SearchResponse
from app.services.search import query as search_query

router = APIRouter(
    prefix="/api/search",
    tags=["search"],
    # rbac.py matrix: search -> all authenticated roles (they search what they may read).
    dependencies=[Depends(require_role("admin", "qa_lead", "qa_engineer", "developer"))],
)


@router.get("", response_model=SearchResponse)
async def get_search(
    q: str = Query(..., min_length=1, description="The full-text query."),
    index: str | None = Query(None, description="Optional scoped index (executions|failures|logs)."),
) -> SearchResponse:
    """Search executions/failures/logs for `q`, returning ranked highlighted hits.

    ES-down bubbles a ConnectionError to the main.py 503 handler (honest 'search unavailable',
    never a fabricated empty list). `q` is forwarded as a structured multi_match VALUE.
    """
    hits = await search_query.search(q, index=index)
    return SearchResponse(
        query=q,
        count=len(hits),
        hits=[SearchHit(**h) for h in hits],
    )
