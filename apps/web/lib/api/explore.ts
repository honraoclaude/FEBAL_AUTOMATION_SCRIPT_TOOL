/**
 * Live exploration API surface (plan 04-04 — EXPL-01 UI half).
 *
 * Mirrors the backend EXPL-01 seam: POST /api/explore starts a run (202 + run_id),
 * POST /api/explore/{run_id}/stop is the L-3 cooperative cancel the Stop button calls,
 * and the SSE stream (GET /api/explore/{run_id}/events) emits ExploreProgressEvent frames
 * the live page parses. zod parses every payload at the boundary (T-04-20: feed_line is
 * rendered as React text, never raw HTML — the schema is a UX/parse guard, Pydantic remains
 * the server authority). The stream itself is opened by the page via `new EventSource` over
 * the same-origin /api/* rewrite (cookie auth) — this module only owns the JSON contract +
 * the start/stop POSTs, consistent with lib/api/client.ts (no token handling).
 */

import { z } from "zod";

import { api } from "./client";

/**
 * The per-step live-progress event the explorer publishes (shared/events.ExploreProgressEvent).
 * Counters are ABSOLUTE values; stop_reason is null while running and a STOP_REASONS value on
 * the terminal event (L-2 maps it to a UI state).
 */
export const exploreProgressEventSchema = z.object({
  run_id: z.string(),
  step: z.number().int(),
  pages_found: z.number().int(),
  actions_taken: z.number().int(),
  current_url: z.string(),
  current_title: z.string(),
  screenshot_path: z.string().nullable(),
  feed_line: z.string(),
  cost_usd: z.number(),
  elapsed_s: z.number(),
  stop_reason: z.string().nullable(),
});

export type ExploreProgressEvent = z.infer<typeof exploreProgressEventSchema>;

const startExploreSchema = z.object({ run_id: z.string() });

/** Start an exploration of a target; returns the threading run_id (202 from POST /explore). */
export async function startExplore(targetId: number): Promise<{ run_id: string }> {
  return startExploreSchema.parse(
    await api.post("/api/explore", { target_id: targetId }),
  );
}

/**
 * L-3 cooperative Stop: ask the backend to cancel the run (sets the Redis cancel flag the
 * explorer loop honors at loop-top). The stream then emits the terminal `stopped` event.
 */
export async function stopExplore(runId: string): Promise<void> {
  await api.post(`/api/explore/${runId}/stop`);
}

/** Build the auth-gated screenshot URL from a run-relative basename (M-1). */
export function screenshotUrl(runId: string, name: string): string {
  return `/api/explore/${runId}/screenshot/${name}`;
}
