/**
 * Coverage API surface (plan 10-06 — DASH-04 coverage panel UI half).
 *
 * Two DISTINCT coverage metrics, each with its OWN honest definition — the two are NEVER conflated
 * (Pitfall 5 / T-10-31):
 *
 *   - GET /api/coverage/flows  (Plan 02, role-gated) -> the LIFECYCLE coverage:
 *       a discovered flow with ≥1 approved scenario AND ≥1 passing execution; ships the honest
 *       `definition` + `measured_against` strings + the per-flow drill-down (has_approved/has_passing
 *       /covered) IN the payload (server-authoritative, never a client-fabricated number).
 *   - GET /api/coverage  (Phase-5 ground-truth, EXISTING) -> EXPLORATION completeness:
 *       discovered flows ÷ the committed ground-truth set — a different question, shown on its OWN
 *       card with its OWN definition.
 *
 * zod parses every payload at the boundary (the lib/api/executions.ts precedent). A forbidden role
 * gets a 403 the page maps to the no-access state; a graph-down surfaces as a 503 the page renders as
 * the honest "graph unavailable" message; the api wrapper handles 401 -> refresh -> /login.
 */

import { z } from "zod";

import { api } from "./client";

// --- DASH-04 lifecycle coverage (GET /api/coverage/flows) -------------------------------------

/** One discovered flow's lifecycle-coverage drill-down (the per-flow table row). */
export const flowCoverageRowSchema = z.object({
  flow_id: z.string(),
  has_approved: z.boolean(),
  has_passing: z.boolean(),
  covered: z.boolean(),
});
export type FlowCoverageRow = z.infer<typeof flowCoverageRowSchema>;

/** The lifecycle-coverage payload — honest definition + percentage + per-flow drill-down. */
export const coverageResponseSchema = z.object({
  definition: z.string(),
  measured_against: z.string(),
  total_discovered: z.number().int(),
  covered: z.number().int(),
  coverage_percent: z.number(),
  covered_flow_ids: z.array(z.string()),
  flows: z.array(flowCoverageRowSchema),
});
export type CoverageResponse = z.infer<typeof coverageResponseSchema>;

// --- Phase-5 ground-truth coverage (GET /api/coverage) ----------------------------------------

/**
 * The EXISTING Phase-5 ground-truth coverage shape (routers/kg.py CoverageResponse). It is shown
 * SEPARATELY with its own definition. When NO page has been discovered the metric is NOT measurable,
 * so the backend returns `measured: false` with zero counts — the page renders the honest
 * "Not yet measured" state, NEVER a fabricated 0%-as-measured. When `measured: true`,
 * `coverage_percent` carries the real computed percentage (screens_covered ÷ screens_total).
 */
export const groundTruthCoverageSchema = z.object({
  screens_total: z.number().int(),
  screens_covered: z.number().int(),
  flows_total: z.number().int(),
  flows_covered: z.number().int(),
  coverage_percent: z.number(),
  measured: z.boolean(),
});
export type GroundTruthCoverage = z.infer<typeof groundTruthCoverageSchema>;

// --- fetchers ---------------------------------------------------------------------------------

/**
 * GET /api/coverage/flows (role: admin | qa_lead | developer). 403 -> ApiError the page maps to
 * no-access; 503 -> the honest graph-down state.
 */
export async function getCoverageFlows(): Promise<CoverageResponse> {
  return coverageResponseSchema.parse(await api.get("/api/coverage/flows"));
}

/**
 * GET /api/coverage (the Phase-5 ground-truth metric — shown SEPARATELY, never merged). Best-effort:
 * the caller renders the honest unmeasured/graph-down state rather than failing the whole panel.
 */
export async function getGroundTruthCoverage(): Promise<GroundTruthCoverage> {
  return groundTruthCoverageSchema.parse(await api.get("/api/coverage"));
}
