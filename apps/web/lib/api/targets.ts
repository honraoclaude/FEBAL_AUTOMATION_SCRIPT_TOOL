/**
 * Target registry API surface (plan 01-06 — PLAT-01 UI half).
 *
 * Mirrors the credential-free /api/targets contract from plan 01-05. zod parses
 * every API response at the boundary (threat T-01-23: client validation is a UX
 * duplicate; Pydantic remains the server-side authority). TargetResponse carries
 * NO credential fields by construction (D-06) — this module never reads, stores,
 * or echoes a password; credentials are write-only inputs on create/update.
 */

import { z } from "zod";

import { api } from "./client";

/** Optional per-target exploration budget overrides (Phase 4 contract). */
export const budgetOverridesSchema = z.object({
  max_steps: z.number().int().min(1).nullable().optional(),
  max_depth: z.number().int().min(1).nullable().optional(),
  wall_clock_seconds: z.number().int().min(1).nullable().optional(),
  token_budget: z.number().int().min(1).nullable().optional(),
});

export type BudgetOverrides = z.infer<typeof budgetOverridesSchema>;

/**
 * Public target shape returned by the API. Structurally credential-free:
 * `has_credentials` is a boolean only — the username/password never travel here.
 */
export const targetResponseSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  base_url: z.string(),
  has_credentials: z.boolean(),
  origin_allowlist: z.array(z.string()),
  sandbox: z.boolean(),
  budget_overrides: budgetOverridesSchema.nullable(),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type TargetResponse = z.infer<typeof targetResponseSchema>;

const targetListSchema = z.array(targetResponseSchema);

/** Write-only credential payload — accepted on create/update, never returned. */
export interface CredentialsIn {
  username: string;
  password: string;
}

/** POST body — credentials required on create. */
export interface TargetCreate {
  name: string;
  base_url: string;
  credentials: CredentialsIn;
  origin_allowlist?: string[];
  sandbox?: boolean;
  budget_overrides?: BudgetOverrides | null;
}

/**
 * PATCH body — every field optional. `credentials` is replace-if-present:
 * omit it entirely to leave the stored credentials untouched (write-only D-06).
 */
export interface TargetUpdate {
  name?: string;
  base_url?: string;
  credentials?: CredentialsIn;
  origin_allowlist?: string[];
  sandbox?: boolean;
  budget_overrides?: BudgetOverrides | null;
  is_active?: boolean;
}

/** List targets; pass true to include soft-deleted (inactive) rows. */
export async function listTargets(
  includeInactive = false,
): Promise<TargetResponse[]> {
  const path = includeInactive
    ? "/api/targets?include_inactive=true"
    : "/api/targets";
  return targetListSchema.parse(await api.get(path));
}

export async function createTarget(
  body: TargetCreate,
): Promise<TargetResponse> {
  return targetResponseSchema.parse(await api.post("/api/targets", body));
}

export async function updateTarget(
  id: number,
  body: TargetUpdate,
): Promise<TargetResponse> {
  return targetResponseSchema.parse(
    await api.patch(`/api/targets/${id}`, body),
  );
}

/** Soft-delete (DELETE -> 204). The row resurfaces under include_inactive. */
export async function deactivateTarget(id: number): Promise<void> {
  await api.delete(`/api/targets/${id}`);
}

/** Reactivate a soft-deleted target (PATCH is_active=true; no confirmation). */
export async function reactivateTarget(
  id: number,
): Promise<TargetResponse> {
  return updateTarget(id, { is_active: true });
}
