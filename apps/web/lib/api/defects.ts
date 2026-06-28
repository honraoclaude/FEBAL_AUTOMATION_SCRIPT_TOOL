/**
 * Defect review-queue API client (JIRA-02 / JIRA-04 / D-04..D-06).
 *
 * zod schemas mirror the Pydantic response models in `apps/api/app/schemas/defect.py`
 * (boundary validation — Pydantic is the server-side authority, zod is the UX duplicate).
 * Every fetcher rides the same-origin `/api/*` rewrite via `./client`, so the httpOnly auth
 * cookie authenticates without any token handling (401 → refresh → /login centrally).
 *
 * Mutations (apply/reject) go through `api.post`; the caller invalidates the list + detail +
 * calibration queries on success (NO optimistic updates — the defect status, the Jira key, and
 * the create-vs-update dedup decision are server-authoritative, T-09-21). The class, the 0-100
 * confidence, the confidence band (vs the SERVER `confidence_threshold`), the status, the Jira
 * key, and the accuracy/precision numbers render STRICTLY from the server — the client never
 * fabricates a "Applied", a Jira key, a class, or a calibration number.
 *
 * Field names MUST stay aligned with schemas/defect.py.
 */

import { z } from "zod";

import { api } from "./client";

// --- Proposed Jira issue + evidence + attachments (the detail composites) ------------------

/** One artifact ref the UI turns into an auth-gated URL (NEVER a raw filesystem path, T-09-18). */
export const attachmentRefSchema = z.object({
  kind: z.string(),
  // The RUN-RELATIVE path (e.g. "flow-0/test/trace.zip") — never an absolute filesystem path.
  path: z.string(),
});

export type AttachmentRef = z.infer<typeof attachmentRefSchema>;

/** The proposed Jira issue body the reviewer reads before Apply. */
export const proposedIssueSchema = z.object({
  summary: z.string(),
  description: z.string(),
  // True only when an LLM wrote the prose; false → the honest "written without an LLM" caption.
  enriched: z.boolean(),
  steps: z.array(z.string()).default([]),
  expected: z.string(),
  actual: z.string(),
  severity: z.string(),
  priority: z.string(),
});

export type ProposedIssue = z.infer<typeof proposedIssueSchema>;

// --- Defect summary (queue row) + detail ---------------------------------------------------

export const defectSummarySchema = z.object({
  id: z.number().int(),
  run_id: z.string(),
  flow_id: z.string(),
  // infrastructure | automation | product_defect
  classification: z.string(),
  // 0-100 int
  confidence: z.number().int(),
  fingerprint: z.string(),
  // NULL until filed; the applied row shows the Jira-key link.
  jira_key: z.string().nullable(),
  // draft | applied | rejected
  status: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type DefectSummary = z.infer<typeof defectSummarySchema>;

export const defectDetailSchema = defectSummarySchema.extend({
  proposed_issue: proposedIssueSchema,
  // The cited-evidence snapshot (error type / DOM diff / heal history / infra health). Opaque
  // JSON the server decided on — rendered field-by-field but otherwise unstructured here.
  evidence: z.record(z.string(), z.unknown()).nullable(),
  attachments: z.array(attachmentRefSchema).default([]),
  // The calibrated floor the UI bands confidence against (SERVER value, never a client literal).
  confidence_threshold: z.number().int(),
  // The create-vs-update decision the apply path reports (null on a read; set after apply).
  last_action: z.string().nullable().optional(),
});

export type DefectDetail = z.infer<typeof defectDetailSchema>;

// --- Calibration (the read-only DEF-03/QUAL-03 numbers) ------------------------------------

export const calibrationSchema = z.object({
  // Nullable for the not-measured state (the UI renders the honest "not measured yet" copy).
  classification_accuracy: z.number().nullable(),
  draft_precision: z.number().nullable(),
  confidence_threshold: z.number().int(),
  autonomous_enabled: z.boolean(),
});

export type Calibration = z.infer<typeof calibrationSchema>;

const defectsListSchema = z.array(defectSummarySchema);

// --- Fetchers ------------------------------------------------------------------------------

/**
 * List review-queue defects filtered by status ("draft" | "applied" | "rejected" | "all") and an
 * optional class ("infrastructure" | "automation" | "product_defect"). Both ride the `?status=`
 * and `?class=` query params (the `class` alias the backend declares).
 */
export async function listDefects(status: string, klass?: string): Promise<DefectSummary[]> {
  let url = `/api/defects?status=${encodeURIComponent(status)}`;
  if (klass && klass !== "all") {
    url += `&class=${encodeURIComponent(klass)}`;
  }
  return defectsListSchema.parse(await api.get(url));
}

/** One defect for review: the proposed issue + cited evidence + attachment refs + the threshold. */
export async function defectDetail(id: number): Promise<DefectDetail> {
  return defectDetailSchema.parse(await api.get(`/api/defects/${id}`));
}

/** The read-only calibration numbers + the autonomy-flag state (honest nulls when not measured). */
export async function calibration(): Promise<Calibration> {
  return calibrationSchema.parse(await api.get(`/api/defects/calibration`));
}

/** Apply: file-or-update the defect to Jira; sets status=applied + jira_key on success. */
export async function applyDefect(id: number): Promise<DefectDetail> {
  return defectDetailSchema.parse(await api.post(`/api/defects/${id}/apply`));
}

/** Reject: sets status=rejected (nothing is filed). */
export async function rejectDefect(id: number): Promise<DefectDetail> {
  return defectDetailSchema.parse(await api.post(`/api/defects/${id}/reject`));
}
