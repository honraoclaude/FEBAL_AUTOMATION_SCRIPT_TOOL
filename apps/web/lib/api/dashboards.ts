/**
 * Dashboards API surface (plan 10-05 — DASH-01/02/03 UI half).
 *
 * Mirrors the backend read-services (Plan 02 — services/dashboards.py + schemas/dashboards.py),
 * all role-gated by `require_role` server-side:
 *   - GET /api/dashboards/executive  -> ExecutiveDashboard (coverage + trends + KPIs)
 *   - GET /api/dashboards/qa         -> QaDashboard (runs + failed tests + run-relative artifact refs)
 *   - GET /api/dashboards/developer  -> DeveloperDashboard (root-cause + error trend + module breakdown)
 *
 * zod parses every payload at the boundary (the lib/api/executions.ts precedent) — every KPI, chart
 * point, table row, and artifact ref renders STRICTLY from the server (no fabricated/optimistic
 * numbers, the honesty rule). A forbidden role gets a 403 the page maps to the no-access state; the
 * api wrapper handles 401 -> refresh -> /login.
 *
 * Artifact links: the QA payload carries the kind + the RUN-RELATIVE stored path ONLY (never an fs
 * path, T-10-24). The auth-gated URL is built via the Phase-7 artifactUrl() — the {flow_id} segment
 * participates in the server-side containment guard. We reuse executions.artifactUrl/artifactBasename
 * verbatim so the contract stays in one place.
 */

import { z } from "zod";

import { api } from "./client";
import { type ArtifactKind } from "./executions";

// --- shared primitives ------------------------------------------------------------------------

/** One per-day pass-rate point (pass_rate is 0..1; the chart renders it as a %). */
export const passRatePointSchema = z.object({
  day: z.string().nullable(),
  pass_rate: z.number(),
  total: z.number().int(),
  passed: z.number().int(),
});
export type PassRatePoint = z.infer<typeof passRatePointSchema>;

/** One per-day count point (defects filed / errors classified). */
export const countPointSchema = z.object({
  day: z.string().nullable(),
  count: z.number().int(),
});
export type CountPoint = z.infer<typeof countPointSchema>;

// --- DASH-04 lifecycle coverage (reused on the executive dashboard) ---------------------------

export const flowCoverageRowSchema = z.object({
  flow_id: z.string(),
  has_approved: z.boolean(),
  has_passing: z.boolean(),
  covered: z.boolean(),
});
export type FlowCoverageRow = z.infer<typeof flowCoverageRowSchema>;

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

// --- executive (DASH-01) ----------------------------------------------------------------------

export const executiveKpisSchema = z.object({
  // The latest day's pass rate already converted to a 0..100 PERCENT server-side (LOW-2 ×100).
  pass_rate_percent: z.number(),
  open_defects: z.number().int(),
});

export const executiveDashboardSchema = z.object({
  coverage: coverageResponseSchema,
  pass_rate_trend: z.array(passRatePointSchema),
  defects_trend: z.array(countPointSchema),
  kpis: executiveKpisSchema,
});
export type ExecutiveDashboard = z.infer<typeof executiveDashboardSchema>;

// --- qa (DASH-02) -----------------------------------------------------------------------------

/** A RUN-RELATIVE artifact reference (kind + stored path; the URL is built client-side). */
export const artifactRefSchema = z.object({
  kind: z.string(),
  path: z.string(),
});
export type ArtifactRef = z.infer<typeof artifactRefSchema>;

export const failedTestSchema = z.object({
  run_id: z.string(),
  flow_id: z.string(),
  verdict: z.string(),
  attempts: z.number().int(),
  error_text: z.string().nullable(),
  artifacts: z.array(artifactRefSchema),
});
export type FailedTest = z.infer<typeof failedTestSchema>;

/** A QA history row (TestRunResponse — started/finished are ISO datetimes here). */
export const qaRunSchema = z.object({
  run_id: z.string(),
  tier: z.string(),
  selector: z.string().nullable(),
  status: z.string(),
  total: z.number().int(),
  passed: z.number().int(),
  failed: z.number().int(),
  flaky: z.number().int(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  created_at: z.string(),
});
export type QaRun = z.infer<typeof qaRunSchema>;

export const qaDashboardSchema = z.object({
  runs: z.array(qaRunSchema),
  failed_tests: z.array(failedTestSchema),
});
export type QaDashboard = z.infer<typeof qaDashboardSchema>;

// --- developer (DASH-03) ----------------------------------------------------------------------

export const rootCauseGroupSchema = z.object({
  classification: z.string(),
  fingerprint: z.string(),
  count: z.number().int(),
  rep_defect_id: z.number().int(),
});
export type RootCauseGroup = z.infer<typeof rootCauseGroupSchema>;

export const moduleFailureSchema = z.object({
  flow_id: z.string(),
  failure_count: z.number().int(),
});
export type ModuleFailure = z.infer<typeof moduleFailureSchema>;

export const developerDashboardSchema = z.object({
  root_cause_groups: z.array(rootCauseGroupSchema),
  errors_trend: z.array(countPointSchema),
  module_breakdown: z.array(moduleFailureSchema),
});
export type DeveloperDashboard = z.infer<typeof developerDashboardSchema>;

// --- fetchers ---------------------------------------------------------------------------------

/** GET /api/dashboards/executive (role: admin | qa_lead). 403 -> ApiError the page maps to no-access. */
export async function getExecutiveDashboard(): Promise<ExecutiveDashboard> {
  return executiveDashboardSchema.parse(await api.get("/api/dashboards/executive"));
}

/** GET /api/dashboards/qa (role: admin | qa_lead | qa_engineer). */
export async function getQaDashboard(): Promise<QaDashboard> {
  return qaDashboardSchema.parse(await api.get("/api/dashboards/qa"));
}

/** GET /api/dashboards/developer (role: admin | qa_lead | developer). */
export async function getDeveloperDashboard(): Promise<DeveloperDashboard> {
  return developerDashboardSchema.parse(await api.get("/api/dashboards/developer"));
}

/**
 * The artifact kind on a QA failed-test ref, narrowed to the 3 REAL TestArtifact kinds
 * (screenshot | trace | video — there is no console_log/network_log; W4: console + network live
 * INSIDE the trace). An unknown kind from the payload is dropped (honest, never a fabricated link).
 */
export function asArtifactKind(kind: string): ArtifactKind | null {
  return kind === "screenshot" || kind === "trace" || kind === "video"
    ? kind
    : null;
}
