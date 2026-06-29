/**
 * Traceability API surface (plan 10-06 — DASH-05 traceability viewer UI half).
 *
 * Mirrors the backend read-time cross-store join (Plan 03 — services/traceability.py +
 * schemas/traceability.py), role-gated by `require_role` server-side:
 *
 *   GET /api/traceability?{flow_id|scenario_id|run_id|defect_id}=...  -> TraceabilityResponse
 *
 * The viewer picks ONE entry artifact (flow / scenario / run / defect) and the server assembles the
 * lifecycle chain flow ↔ scenario ↔ script ↔ execution ↔ defect on the resolved run_id + flow_id.
 * The router enforces EXACTLY one entry id (422 for zero or multiple); an UNKNOWN id returns an
 * honest empty chain at 200 (the viewer renders the gaps, never a 404). A graph-down degrades the
 * flow segment to null + a `flow_note` (the relational chain still assembles).
 *
 * zod parses every payload at the boundary — every chain node renders STRICTLY from the server; a
 * missing segment is an honest empty list / null gap, never a fabricated node (T-10-30). The api
 * wrapper handles 401 -> refresh -> /login; a 403 the page maps to the no-access state.
 */

import { z } from "zod";

import { api } from "./client";

// --- the entry artifact types the picker offers (map 1:1 to the four query params) -------------

/** The four entry artifact kinds the picker offers (UI label -> the API query param). */
export type EntryType = "flow" | "scenario" | "run" | "defect";

/** Map a picker entry type to its API query-param name (run -> run_id, etc.). */
const ENTRY_PARAM: Record<EntryType, string> = {
  flow: "flow_id",
  scenario: "scenario_id",
  run: "run_id",
  defect: "defect_id",
};

// --- segment schemas (mirror schemas/traceability.py) -----------------------------------------

export const entryRefSchema = z.object({
  type: z.string().nullable().optional(),
  id: z.string().nullable().optional(),
});

export const flowSegmentSchema = z.object({
  flow_id: z.string().nullable().optional(),
  name: z.string().nullable().optional(),
  category: z.string().nullable().optional(),
  risk_tier: z.string().nullable().optional(),
  step_count: z.number().int().nullable().optional(),
});
export type FlowSegment = z.infer<typeof flowSegmentSchema>;

export const scenarioSegmentSchema = z.object({
  id: z.number().int(),
  flow_id: z.string(),
  run_id: z.string(),
  feature_name: z.string(),
  status: z.string(),
});
export type ScenarioSegment = z.infer<typeof scenarioSegmentSchema>;

export const scriptSegmentSchema = z.object({
  run_id: z.string(),
  path: z.string(),
  derived: z.boolean(),
});
export type ScriptSegment = z.infer<typeof scriptSegmentSchema>;

export const executionSegmentSchema = z.object({
  run_id: z.string(),
  flow_id: z.string(),
  verdict: z.string(),
  attempts: z.number().int(),
  duration_ms: z.number().int().nullable().optional(),
  tier: z.string().nullable().optional(),
  status: z.string().nullable().optional(),
});
export type ExecutionSegment = z.infer<typeof executionSegmentSchema>;

export const defectSegmentSchema = z.object({
  id: z.number().int(),
  run_id: z.string(),
  flow_id: z.string(),
  classification: z.string(),
  confidence: z.number().int(),
  fingerprint: z.string(),
  jira_key: z.string().nullable().optional(),
  status: z.string(),
});
export type DefectSegment = z.infer<typeof defectSegmentSchema>;

export const traceabilityResponseSchema = z.object({
  entry: entryRefSchema,
  // The flow segment is a single record, a set (a multi-flow run entry), or null (graph-down/absent).
  flow: z
    .union([flowSegmentSchema, z.array(flowSegmentSchema), z.null()])
    .optional(),
  flow_note: z.string().nullable().optional(),
  scenarios: z.array(scenarioSegmentSchema),
  scripts: z.array(scriptSegmentSchema),
  executions: z.array(executionSegmentSchema),
  artifacts: z.array(
    z.object({
      run_id: z.string(),
      flow_id: z.string(),
      kind: z.string(),
      path: z.string(),
    }),
  ),
  defects: z.array(defectSegmentSchema),
});
export type TraceabilityResponse = z.infer<typeof traceabilityResponseSchema>;

/** Normalize the nullable `flow` union to an array (single record -> [record], null -> []). */
export function flowSegments(resp: TraceabilityResponse): FlowSegment[] {
  if (!resp.flow) return [];
  return Array.isArray(resp.flow) ? resp.flow : [resp.flow];
}

// --- fetcher ----------------------------------------------------------------------------------

/**
 * GET /api/traceability with exactly ONE entry id (role: admin | qa_lead | developer). An unknown
 * id returns an honest empty chain (200); a 422 means the (programming) caller passed != 1 id; a
 * 403 the page maps to no-access.
 */
export async function getTraceability(
  type: EntryType,
  id: string,
): Promise<TraceabilityResponse> {
  const param = ENTRY_PARAM[type];
  const qs = new URLSearchParams({ [param]: id }).toString();
  return traceabilityResponseSchema.parse(await api.get(`/api/traceability?${qs}`));
}
