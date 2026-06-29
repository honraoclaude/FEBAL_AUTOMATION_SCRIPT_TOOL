/**
 * Search API surface (plan 10-06 — DASH-06 search UI half).
 *
 * Mirrors the backend Elasticsearch-backed search (Plan 04 — services/search/query.py +
 * schemas/search.py), role-gated by `require_role` for all authenticated roles:
 *
 *   GET /api/search?q=&index=  -> SearchResponse { query, count, hits[] }
 *
 * Each hit carries its index + id (the drill keys), the optional score, the _source doc, and the
 * per-field `highlight` fragments (the ES server emphasizes the matched term with <em>…</em>; the UI
 * renders THAT fragment as safe emphasized text — it does NOT re-highlight client-side, T-10-29).
 *
 * GRACEFUL DEGRADE (T-10-30): an ES outage bubbles to an honest 503 on the READ path — NEVER a fake
 * empty-results 200. The api client throws an ApiError with status 503; the page distinguishes that
 * (the honest "search unavailable" state) from an empty-results 200 (the "No results" state). zod
 * parses every payload at the boundary — hits render STRICTLY from the server, never a fabricated hit.
 */

import { z } from "zod";

import { api } from "./client";

/** The optional index scope the picker offers (default "all" = search every index). */
export type SearchIndex = "all" | "executions" | "failures" | "logs";

/** One ES hit — index + id are the drill keys; highlight carries the emphasized fragments. */
export const searchHitSchema = z.object({
  index: z.string(),
  id: z.string(),
  score: z.number().nullable().optional(),
  source: z.record(z.string(), z.unknown()).default({}),
  highlight: z.record(z.string(), z.array(z.string())).default({}),
});
export type SearchHit = z.infer<typeof searchHitSchema>;

/** The ranked hit list + the echoed query + the count (the UI's "N results for q" header). */
export const searchResponseSchema = z.object({
  query: z.string(),
  count: z.number().int(),
  hits: z.array(searchHitSchema),
});
export type SearchResponse = z.infer<typeof searchResponseSchema>;

/**
 * GET /api/search?q=&index= (all authenticated roles). An ES-down bubbles to an ApiError with
 * status 503 (the page renders the honest "search unavailable" state, distinct from no-results); a
 * 403 the page maps to no-access. `index="all"` is omitted from the query so the backend searches
 * every index by default.
 */
export async function search(
  q: string,
  index: SearchIndex = "all",
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q });
  if (index !== "all") params.set("index", index);
  return searchResponseSchema.parse(await api.get(`/api/search?${params.toString()}`));
}

/**
 * Pull the first highlight fragment from a hit (any field) — the ES server already emphasized the
 * matched term. Returns null when the hit carries no highlight (the UI falls back to a source title).
 */
export function firstHighlight(hit: SearchHit): string | null {
  for (const fragments of Object.values(hit.highlight)) {
    if (fragments.length > 0) return fragments[0];
  }
  return null;
}

/** A best-effort human title for a hit from its _source (honest: only what the server returned). */
export function hitTitle(hit: SearchHit): string {
  const src = hit.source;
  for (const key of ["title", "flow_id", "run_id", "name", "message", "event"]) {
    const v = src[key];
    if (typeof v === "string" && v.length > 0) return v;
  }
  return hit.id;
}
