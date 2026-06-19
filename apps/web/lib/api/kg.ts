/**
 * Knowledge-graph read-API client (KG-02 / D-05 / D-06).
 *
 * zod schemas mirror the Pydantic response models in `apps/api/app/schemas/kg.py`
 * (boundary validation — Pydantic is the server-side authority, zod is the UX duplicate,
 * threat T-01-23). Every fetcher rides the same-origin `/api/*` rewrite via `./client`, so
 * the httpOnly auth cookie authenticates without any token handling (401 → refresh → /login
 * is handled centrally in client.ts). These are READ-only GETs — no mutations.
 *
 * Field names MUST stay aligned with schemas/kg.py.
 */

import { z } from "zod";

import { api } from "./client";

// --- Flows (KG-04) -----------------------------------------------------------------------

export const flowSchema = z.object({
  flow_id: z.string(),
  name: z.string(),
  category: z.string().nullable(),
  risk_score: z.number().int(),
  risk_tier: z.string(),
  step_count: z.number().int(),
  bounded: z.boolean(),
  signals: z.record(z.string(), z.unknown()).default({}),
});

export type Flow = z.infer<typeof flowSchema>;

const flowsResponseSchema = z.object({ flows: z.array(flowSchema) });

export const flowStepSchema = z.object({
  order: z.number().int(),
  fingerprint: z.string(),
  title: z.string().nullable(),
  url: z.string().nullable(),
});

export const flowDetailSchema = z.object({
  flow_id: z.string(),
  name: z.string(),
  category: z.string().nullable(),
  risk_score: z.number().int(),
  risk_tier: z.string(),
  step_count: z.number().int(),
  bounded: z.boolean(),
  steps: z.array(flowStepSchema),
  signals: z.record(z.string(), z.unknown()).default({}),
});

export type FlowDetail = z.infer<typeof flowDetailSchema>;

export async function listFlows(): Promise<Flow[]> {
  return flowsResponseSchema.parse(await api.get("/api/flows")).flows;
}

export async function flowDetail(flowId: string): Promise<FlowDetail> {
  return flowDetailSchema.parse(
    await api.get(`/api/flows/${encodeURIComponent(flowId)}`),
  );
}

// --- Coverage (QUAL-01 / D-08) -----------------------------------------------------------

export const coverageSchema = z.object({
  screens_total: z.number().int(),
  screens_covered: z.number().int(),
  flows_total: z.number().int(),
  flows_covered: z.number().int(),
  coverage_percent: z.number(),
  measured: z.boolean(),
});

export type Coverage = z.infer<typeof coverageSchema>;

export async function getCoverage(): Promise<Coverage> {
  return coverageSchema.parse(await api.get("/api/coverage"));
}

// --- Pages (KG-01) -----------------------------------------------------------------------

export const pageSchema = z.object({
  fingerprint: z.string(),
  url: z.string().nullable(),
  title: z.string().nullable(),
  first_seen: z.string().nullable(),
  last_verified: z.string().nullable(),
  element_count: z.number().int(),
});

export type Page = z.infer<typeof pageSchema>;

const pagesResponseSchema = z.object({ pages: z.array(pageSchema) });

export const pageDetailSchema = z.object({
  fingerprint: z.string(),
  url: z.string().nullable(),
  title: z.string().nullable(),
  first_seen: z.string().nullable(),
  last_verified: z.string().nullable(),
  elements: z.array(
    z.object({
      key: z.string(),
      role: z.string().nullable(),
      label: z.string().nullable(),
    }),
  ),
  forms: z.array(z.object({ key: z.string() })),
  navigates_to: z.array(
    z.object({
      to: z.string(),
      url: z.string().nullable(),
      via: z.string().nullable(),
    }),
  ),
});

export type PageDetail = z.infer<typeof pageDetailSchema>;

export async function listPages(): Promise<Page[]> {
  return pagesResponseSchema.parse(await api.get("/api/pages")).pages;
}

export async function pageDetail(fingerprint: string): Promise<PageDetail> {
  return pageDetailSchema.parse(
    await api.get(`/api/pages/${encodeURIComponent(fingerprint)}`),
  );
}

// --- Element Repository (KG-05) ----------------------------------------------------------

export const locatorEntrySchema = z.object({
  strategy: z.string(),
  value: z.string().nullable().optional(),
  name: z.string().nullable().optional(),
});

export const locatorHistoryEntrySchema = z.object({
  step: z.number().int().nullable().optional(),
  chain: z.array(locatorEntrySchema).default([]),
});

export const elementSchema = z.object({
  key: z.string(),
  role: z.string().nullable(),
  label: z.string().nullable(),
  page_fingerprint: z.string().nullable(),
  page_url: z.string().nullable(),
  locator_chain: z.array(locatorEntrySchema).default([]),
  locator_history: z.array(locatorHistoryEntrySchema).default([]),
  first_seen: z.string().nullable(),
  last_verified: z.string().nullable(),
});

export type Element = z.infer<typeof elementSchema>;

const elementsResponseSchema = z.object({ elements: z.array(elementSchema) });

export async function listElements(): Promise<Element[]> {
  return elementsResponseSchema.parse(await api.get("/api/elements")).elements;
}

export async function elementDetail(key: string): Promise<Element> {
  return elementSchema.parse(
    await api.get(`/api/elements/${encodeURIComponent(key)}`),
  );
}

// --- Graph summary (KG-01) ---------------------------------------------------------------

export const graphSummarySchema = z.object({
  counts: z.record(z.string(), z.number().int()).default({}),
  discovered: z.boolean(),
});

export type GraphSummary = z.infer<typeof graphSummarySchema>;

export async function getGraphSummary(): Promise<GraphSummary> {
  return graphSummarySchema.parse(await api.get("/api/graph"));
}
