/**
 * Executions API surface (plan 07-04 Task 3 — EXEC-05/06 UI half).
 *
 * Mirrors the backend /api/executions seam (routers/executions.py — the single owner, B1):
 *   - POST /api/executions {tier}            -> 202 + run_id (the launcher start mutation)
 *   - GET  /api/executions                   -> the test_runs history (TestRunResponse[])
 *   - GET  /api/executions/{run_id}          -> run status + per-flow results (404 unknown)
 *   - POST /api/executions/{run_id}/kill     -> graceful cooperative kill (sets the flag + purge)
 *   - GET  /api/executions/{run_id}/events   -> the SSE stream of ExecutionProgressEvent frames
 *   - GET  /api/executions/{run_id}/artifacts/{flow_id}/{name} -> auth-gated artifact files
 *
 * zod parses every payload at the boundary (the per-test verdict/run status render strictly from
 * the server — no fabricated/optimistic status, T-07-17). The SSE stream is opened by the page via
 * `new EventSource` over the same-origin /api/* rewrite (cookie auth); this module owns the JSON
 * contract + the start/kill POSTs + the artifact-URL builder, consistent with lib/api/client.ts.
 *
 * Trends note: the backend exposes no dedicated trends route — pass-rate/duration trends are
 * DERIVED here from the server-authoritative runs list (each run carries total/passed/failed +
 * started_at/finished_at). The runs table remains the source of truth; the chart is supplementary.
 */

import { z } from "zod";

import { api } from "./client";

/**
 * The per-test live-progress event the worker publishes (shared/events.ExecutionProgressEvent).
 * Run counters are ABSOLUTE values (not deltas); the per-test delta fields are null on a
 * counters-only snapshot frame (the reconnect snapshot, W3). 1:1 with the Pydantic model.
 */
export const executionProgressEventSchema = z.object({
  run_id: z.string(),
  completed: z.number().int(),
  total: z.number().int(),
  passed: z.number().int(),
  failed: z.number().int(),
  flaky: z.number().int(),
  elapsed_s: z.number(),
  // queued | running | stopping | passed | failed | killed
  status: z.string(),
  // The per-test delta this frame is about (null on a counters-only snapshot).
  flow_id: z.string().nullable().optional(),
  test_id: z.string().nullable().optional(),
  test_name: z.string().nullable().optional(),
  // queued | running | passed | flaky | product_failure | aborted
  test_status: z.string().nullable().optional(),
  attempt: z.number().int().default(0),
  duration_ms: z.number().int().nullable().optional(),
});

export type ExecutionProgressEvent = z.infer<typeof executionProgressEventSchema>;

/** A history row (GET /api/executions — TestRunResponse). */
export const testRunSchema = z.object({
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

export type TestRun = z.infer<typeof testRunSchema>;

/** A per-flow result on the run-detail payload (GET /api/executions/{run_id}). */
export const testResultSchema = z.object({
  flow_id: z.string(),
  // passed | flaky | product_failure | aborted | failed
  verdict: z.string(),
  attempts: z.number().int(),
  duration_ms: z.number().int().nullable(),
});

export type TestResult = z.infer<typeof testResultSchema>;

/** The run-detail payload (GET /api/executions/{run_id}). */
export const runDetailSchema = z.object({
  run_id: z.string(),
  tier: z.string(),
  status: z.string(),
  total: z.number().int(),
  passed: z.number().int(),
  failed: z.number().int(),
  flaky: z.number().int(),
  results: z.array(testResultSchema),
});

export type RunDetail = z.infer<typeof runDetailSchema>;

const startRunSchema = z.object({ run_id: z.string(), status: z.string() });

/** The tiers the launcher offers (sentence case, default Smoke — 07-UI-SPEC Copywriting). */
export const TIERS = [
  { value: "smoke", label: "Smoke" },
  { value: "sanity", label: "Sanity" },
  { value: "regression", label: "Regression" },
  { value: "full", label: "Full" },
  { value: "risk-based", label: "Risk-based" },
] as const;

export type Tier = (typeof TIERS)[number]["value"];

/** The history list, newest-first (the GET /api/executions surface). */
export async function listRuns(): Promise<TestRun[]> {
  return z.array(testRunSchema).parse(await api.get("/api/executions"));
}

/** A single run's status + per-flow results (404 -> ApiError 404 the caller maps to not-found). */
export async function getRun(runId: string): Promise<RunDetail> {
  return runDetailSchema.parse(await api.get(`/api/executions/${runId}`));
}

/** Start a tier run; returns the threading run_id (202 from POST /api/executions). */
export async function startRun(tier: string): Promise<{ run_id: string }> {
  return startRunSchema.parse(await api.post("/api/executions", { tier }));
}

/** Graceful cooperative kill: set the Redis flag + purge the queue (no optimistic state). */
export async function killRun(runId: string): Promise<void> {
  await api.post(`/api/executions/${runId}/kill`);
}

/** The artifact kinds rendered on the run detail (W4: console + network live INSIDE the trace). */
export type ArtifactKind = "screenshot" | "trace" | "video";

/** The conventional run-relative basename per kind (Playwright per-test capture layout). */
const ARTIFACT_BASENAME: Record<ArtifactKind, string> = {
  screenshot: "test-failed-1.png",
  trace: "trace.zip",
  video: "video.webm",
};

/** The mono basename shown beneath each artifact link (07-UI-SPEC Typography). */
export function artifactBasename(kind: ArtifactKind): string {
  return ARTIFACT_BASENAME[kind];
}

/**
 * Build the auth-gated artifact URL from RUN-RELATIVE segments (mirrors screenshotUrl; M-1).
 * Targets /api/executions/{runId}/artifacts/{flowId}/{name} — the {flowId} segment participates
 * in the server-side realpath containment guard. NEVER a raw absolute filesystem path.
 */
export function artifactUrl(
  runId: string,
  flowId: string,
  kind: ArtifactKind,
): string {
  return `/api/executions/${runId}/artifacts/${flowId}/${ARTIFACT_BASENAME[kind]}`;
}

/** A point on the derived pass-rate / duration trends (server-authoritative runs are the source). */
export interface TrendPoint {
  label: string;
  passRate: number;
  durationMs: number | null;
}

/**
 * Derive the trend series from the server's runs list (terminal runs only — a running run has no
 * final duration). Pass-rate = passed/total per run; duration from started_at..finished_at.
 * Oldest-first so the chart reads left-to-right. The runs table stays the source of truth.
 */
export function deriveTrends(runs: TestRun[]): TrendPoint[] {
  const terminal = runs.filter(
    (r) => r.status !== "running" && r.status !== "queued",
  );
  return [...terminal]
    .reverse()
    .map((r) => {
      const durationMs =
        r.started_at && r.finished_at
          ? Math.max(0, Date.parse(r.finished_at) - Date.parse(r.started_at))
          : null;
      return {
        label: r.run_id.slice(0, 8),
        passRate: r.total > 0 ? r.passed / r.total : 0,
        durationMs,
      };
    });
}
