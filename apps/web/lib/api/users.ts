/**
 * Users API surface (plan 10-06 — PLAT-04 admin role-assignment UI half).
 *
 * Mirrors the backend admin user-management router (Plan 01 — routers/users.py), router-level
 * `require_role("admin")`-gated server-side (the security boundary; the UI nav-hide is UX only):
 *
 *   GET  /api/users               -> UserSummary[] (id, email, role — no secrets)
 *   POST /api/users/{id}/role     -> the updated UserSummary (self-demote -> 400; invalid -> 422;
 *                                    unknown id -> 404; non-admin -> 403)
 *
 * zod parses every payload at the boundary; every role renders STRICTLY from the server (no
 * optimistic update — the role is server-authoritative, the badge repaints from the response). A 403
 * the page maps to the no-access state; the api wrapper handles 401 -> refresh -> /login.
 */

import { z } from "zod";

import { api } from "./client";

/** The four-role vocabulary (mirrors the backend RoleLiteral). */
export type Role = "admin" | "qa_lead" | "qa_engineer" | "developer";

export const ROLES: { value: Role; label: string }[] = [
  { value: "admin", label: "Admin" },
  { value: "qa_lead", label: "QA Lead" },
  { value: "qa_engineer", label: "QA Engineer" },
  { value: "developer", label: "Developer" },
];

/** One row in the admin user list (GET /api/users) — id/email/role only. */
export const userSummarySchema = z.object({
  id: z.number().int(),
  email: z.string(),
  role: z.string(),
});
export type UserSummary = z.infer<typeof userSummarySchema>;

export const userListSchema = z.array(userSummarySchema);

/** GET /api/users (Admin only). 403 -> ApiError the page maps to no-access. */
export async function getUsers(): Promise<UserSummary[]> {
  return userListSchema.parse(await api.get("/api/users"));
}

/**
 * POST /api/users/{id}/role — assign a role to the target user (Admin only). Returns the updated
 * UserSummary (the badge repaints from THIS, never an optimistic guess). A self-demote -> 400; an
 * invalid role -> 422; an unknown id -> 404 — all bubble as ApiError the page renders inline.
 */
export async function setRole(id: number, role: Role): Promise<UserSummary> {
  return userSummarySchema.parse(await api.post(`/api/users/${id}/role`, { role }));
}
