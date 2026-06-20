/**
 * Scenario review-queue API client (GEN-02 / D-01..D-04).
 *
 * zod schemas mirror the Pydantic response models in `apps/api/app/schemas/scenario.py`
 * (boundary validation — Pydantic is the server-side authority, zod is the UX duplicate).
 * Every fetcher rides the same-origin `/api/*` rewrite via `./client`, so the httpOnly auth
 * cookie authenticates without any token handling (401 → refresh → /login centrally).
 *
 * Mutations (edit/approve/reject) go through `api.post`; the caller invalidates the list +
 * detail queries on success (NO optimistic updates — the gate result is server-authoritative,
 * D-03). The per-Then `then_results` are rendered STRICTLY from the server; the client never
 * fabricates a "resolved".
 *
 * Field names MUST stay aligned with schemas/scenario.py.
 */

import { z } from "zod";

import { api } from "./client";

// --- Per-Then gate result (D-03 — honest, server-authoritative) ---------------------------

export const thenRefResultSchema = z.object({
  then_text: z.string(),
  resolved: z.boolean(),
  kg_ref: z.string().nullable().optional(),
  reason: z.string().nullable().optional(),
});

export type ThenRefResult = z.infer<typeof thenRefResultSchema>;

// --- Scenario summary (list row) + detail --------------------------------------------------

export const scenarioSummarySchema = z.object({
  id: z.number().int(),
  run_id: z.string(),
  flow_id: z.string(),
  feature_name: z.string(),
  status: z.string(), // draft | approved | rejected
  edited: z.boolean(),
  stale: z.boolean(),
  flow_risk_score: z.number().int().nullable().optional(),
  flow_risk_tier: z.string().nullable().optional(),
  updated_at: z.string(),
});

export type ScenarioSummary = z.infer<typeof scenarioSummarySchema>;

export const scenarioDetailSchema = scenarioSummarySchema.extend({
  gherkin_text: z.string(),
  // The raw structured sidecar refs (kind/ref per Then) — forwarded UNCHANGED on an edit-save
  // so the no-vacuous gate re-validates the row's own refs (D-02). Opaque to the client.
  then_refs: z.array(z.unknown()).default([]),
  then_results: z.array(thenRefResultSchema).default([]),
});

export type ScenarioDetail = z.infer<typeof scenarioDetailSchema>;

const scenariosListSchema = z.array(scenarioSummarySchema);

// --- Fetchers ------------------------------------------------------------------------------

/** List review-queue scenarios filtered by status ("draft" | "approved" | "rejected" | "all"). */
export async function listScenarios(status: string): Promise<ScenarioSummary[]> {
  return scenariosListSchema.parse(
    await api.get(`/api/scenarios?status=${encodeURIComponent(status)}`),
  );
}

/** One scenario for review, including the server-resolved per-Then results. */
export async function scenarioDetail(id: number): Promise<ScenarioDetail> {
  return scenarioDetailSchema.parse(await api.get(`/api/scenarios/${id}`));
}

/** Edit-in-place: re-runs both gates server-side (422 + no save on failure). */
export async function editScenario(
  id: number,
  body: { gherkin_text: string; then_refs: unknown[] },
): Promise<ScenarioDetail> {
  return scenarioDetailSchema.parse(await api.post(`/api/scenarios/${id}/edit`, body));
}

/** Approve: re-runs both gates; sets status=approved only on pass. */
export async function approveScenario(id: number): Promise<ScenarioDetail> {
  return scenarioDetailSchema.parse(await api.post(`/api/scenarios/${id}/approve`));
}

/** Reject: sets status=rejected. */
export async function rejectScenario(id: number): Promise<ScenarioDetail> {
  return scenarioDetailSchema.parse(await api.post(`/api/scenarios/${id}/reject`));
}
