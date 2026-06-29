"""DASH-06 search request/response schemas (mirror the query.search() typed hit list).

BaseModel shapes for GET /api/search — the ranked, highlighted full-text results over the
executions/failures/logs indices. Each hit carries its index + id (the drill keys), the raw
`_score`, the `_source` doc, and the per-field `highlight` fragments the UI renders with <em>
emphasis. The response echoes the query + a count so the UI shows "N results for '<q>'".
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SearchHit(BaseModel):
    """One ES hit — the index + id are the drill keys; highlight carries the emphasized fragments."""

    index: str
    id: str
    score: float | None = None
    source: dict[str, Any] = {}
    highlight: dict[str, list[str]] = {}


class SearchResponse(BaseModel):
    """The ranked hit list + the echoed query + the count (the UI's 'N results for q' header)."""

    query: str
    count: int
    hits: list[SearchHit]
