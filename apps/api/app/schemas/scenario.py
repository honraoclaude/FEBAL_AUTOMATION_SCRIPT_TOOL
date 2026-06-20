"""Scenario review-queue API schemas (GEN-02 / D-01..D-04).

Pydantic v2 request/response models for the auth-gated review router in
`routers/scenarios.py`. They mirror the `scenarios` row (Slice 1's Scenario model) PLUS the
server-resolved per-Then no-vacuous result (`ThenRefResult`) — the honest, server-authoritative
gate display the UI renders strictly from (D-03: a green indicator means the server CONFIRMED
the Then resolves; the client never fabricates it).

Every field name here MUST stay aligned with the zod schemas in `apps/web/lib/api/scenarios.ts`
(boundary validation mirrors these models). Pydantic is the server-side authority; zod is the
UX duplicate at the client boundary (the same discipline as schemas/kg.py ↔ lib/api/kg.ts).

The request bodies (EditRequest / GenerateScenariosRequest / GenerateScriptsRequest) are the
ONLY input-validation surface — every gate re-run still happens server-side regardless of body.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ThenRefResult(BaseModel):
    """One Then step's server-resolved no-vacuous outcome (D-03 — honest, never fabricated).

    `resolved` is True ONLY when the assertion gate confirmed the Then maps to an existing
    Neo4j node/edge; `kg_ref` names the resolved target (mono caption in the UI); `reason`
    names WHY a vacuous Then failed. The client renders green strictly from `resolved`.
    """

    then_text: str
    resolved: bool
    kg_ref: str | None = None
    reason: str | None = None


class ScenarioSummary(BaseModel):
    """A review-queue list row — the scenarios row + its source-flow risk (honest None unscored)."""

    id: int
    run_id: str
    flow_id: str
    feature_name: str
    status: str  # draft | approved | rejected
    edited: bool
    stale: bool
    flow_risk_score: int | None = Field(default=None, ge=0, le=100)
    flow_risk_tier: str | None = None  # "high" | "medium" | "low" | None when unscored
    updated_at: datetime


class ScenarioDetail(ScenarioSummary):
    """A single scenario for review — the summary fields + the Gherkin + per-Then gate results."""

    gherkin_text: str
    then_results: list[ThenRefResult] = Field(default_factory=list)


class EditRequest(BaseModel):
    """POST /scenarios/{id}/edit body — the edited Gherkin + its sidecar then_refs (D-02).

    The router re-runs BOTH gates (lint THEN no-vacuous) on this body BEFORE any save; a
    failing edit returns 422 and saves NOTHING (the row stays draft, the text is preserved
    client-side).
    """

    gherkin_text: str = Field(min_length=1)
    then_refs: list = Field(default_factory=list)


class GenerateScenariosRequest(BaseModel):
    """POST /generate-scenarios body — the explored run_id to generate draft scenarios for."""

    run_id: str = Field(min_length=1)


class GenerateScriptsRequest(BaseModel):
    """POST /generate-scripts body (Slice-3 codegen consumer) — the run_id to codegen for.

    Defined here so the scenario/codegen request contract lives in one module; the codegen
    wiring that consumes it (approved-only → Playwright project) lands in Slice 3.
    """

    run_id: str = Field(min_length=1)
