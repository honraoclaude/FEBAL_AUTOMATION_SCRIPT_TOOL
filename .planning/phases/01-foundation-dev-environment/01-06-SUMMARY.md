---
phase: 01-foundation-dev-environment
plan: 06
subsystem: web
tags: [targets-ui, nextjs-16, react-19, tanstack-query, zod, react-hook-form, shadcn, sonner, playwright-e2e, write-only-credentials]

# Dependency graph
requires:
  - phase: 01-foundation-dev-environment (plan 01-04)
    provides: Next 16 web shell, /api rewrite, client.ts fetch wrapper, shadcn components, /targets stub
  - phase: 01-foundation-dev-environment (plan 01-05)
    provides: /api/targets CRUD (credential-free TargetResponse, include_inactive, soft-delete/reactivate)
provides:
  - /targets fully functional — table (4 states) + register/edit dialog + deactivate/reactivate flow
  - lib/api/targets.ts — zod-parsed credential-free target client (list/create/update/deactivate/reactivate)
  - components/targets/* — targets-table, target-dialog (write-only masked credentials), deactivate-dialog
  - client.ts PATCH method (was missing; targets PATCH needed it)
  - Toaster mounted in the dashboard layout (success-only toasts, bottom-right)
  - tests/e2e/test_targets_ui.py — 4 green Playwright tests (VALIDATION row PLAT-01/e2e)
affects: ["Phase 4 Explorer (targets are its input surface)", "later dashboard phases reuse the table/dialog patterns"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    [
      "zod-parse-at-the-boundary for API responses (UX duplicate of Pydantic authority)",
      "write-only credentials in the UI — never prefilled, masked placeholder, omitted from PATCH when untouched (D-06)",
      "TanStack mutations all invalidate the shared query key; success-only sonner toasts, errors inline never toasted",
      "dialog owns the form + payload-building; page owns the query/mutations and passes async onCreate/onUpdate that throw on failure so the dialog renders its inline error and stays open",
    ]

key-files:
  created:
    - apps/web/lib/api/targets.ts
    - apps/web/components/targets/targets-table.tsx
    - apps/web/components/targets/target-dialog.tsx
    - apps/web/components/targets/deactivate-dialog.tsx
    - apps/api/tests/e2e/test_targets_ui.py
  modified:
    - apps/web/app/(dashboard)/targets/page.tsx
    - apps/web/app/(dashboard)/layout.tsx
    - apps/web/lib/api/client.ts

key-decisions:
  - "Added api.patch to client.ts — the targets contract uses PATCH and the 01-04 wrapper only had get/post/put/delete (Rule 3 blocking)"
  - "Mounted <Toaster> in the dashboard layout — sonner was installed in 01-04 but never hosted, so no toast could render (Rule 3 blocking); placed bottom-right per UI-SPEC interaction defaults"
  - "Reactivate fires PATCH is_active=true directly from the row menu with no confirmation (UI-SPEC: only deactivate confirms)"

patterns-established:
  - "Status/sandbox badges read the --status-pass/--status-neutral/--status-quarantine tokens defined in 01-04 globals.css"
  - "e2e label getters use exact=True (substring matching collided 'Name' with 'Username')"

requirements-completed: [PLAT-01]

# Metrics
duration: ~35min
completed: 2026-06-13
---

# Phase 01 Plan 06: Target Registry UI Summary

**/targets ships the full register/edit/deactivate/reactivate story in the browser — write-only masked credentials (D-06), all four table states from live API data, and 4 Playwright e2e tests proving credentials never reach the DOM (PLAT-01 UI half closes the phase goal)**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-06-13
- **Tasks:** 3 (all auto)
- **Files modified:** 8

## Accomplishments

- PLAT-01 UI half complete: a human with a mouse can now log in and register/edit/deactivate/reactivate a target end-to-end against the live API — the phase goal is achievable in the browser
- Targets table renders all four UI-SPEC §3 states from live `GET /api/targets?include_inactive=true`: loading skeletons, empty-state (contract-exact copy + Register CTA), populated, and muted inactive rows with the Reactivate menu
- Register/edit dialog implements the write-only credential contract (D-06 / threat T-01-22): credentials are never prefilled in edit mode, both fields show the "••••••••" placeholder with the exact helper caption, and `credentials` is omitted from the PATCH body unless the user types new values
- Contract-exact copy throughout: empty-state strings, CTA labels ("Register target" / "Save changes"), masking helper, destructive confirmation ("Deactivate {name}?" / "Keep target"), inline request-error, and validation messages ("Name is required" / "Enter a valid URL (including http:// or https://)")
- All mutations go through TanStack Query and invalidate `["targets"]`; sonner toasts are success-only ("Target registered" / "Target updated" / "Target deactivated"), errors render inline in the dialog and never toast — no optimistic updates
- 4 Playwright e2e tests green against the live compose stack; test 2 asserts the registration password is absent from the entire page body during and after edit
- `npm run build` clean (TypeScript strict); login e2e still 5/5 green (no regression from the layout/Toaster change)

## Task Commits

1. **Task 1: Targets table + zod API module** - `205a11c` (feat)
2. **Task 2: Register/edit dialog, deactivate flow, mutations + toasts** - `0231b41` (feat)
3. **Task 3: Playwright e2e — registry UI flows** - `5e34e8e` (test)

## Files Created/Modified

- `apps/web/lib/api/targets.ts` - zod schemas mirroring the credential-free TargetResponse + typed list/create/update/deactivate/reactivate over client.ts; parses every response at the boundary
- `apps/web/components/targets/targets-table.tsx` - UI-SPEC §3 table: skeleton/empty/populated/inactive states, mono base URL, status + sandbox badges via the status tokens, row-actions dropdown with `aria-label="Actions for {name}"`
- `apps/web/components/targets/target-dialog.tsx` - UI-SPEC §4 dialog: Target / Credentials / Exploration-rules sections, write-only masked credentials, zod URL validation, allowlist textarea, sandbox switch, collapsible budget overrides, inline request-error alert
- `apps/web/components/targets/deactivate-dialog.tsx` - destructive confirmation with exact copy + Deactivate / Keep target CTAs
- `apps/web/app/(dashboard)/targets/page.tsx` - replaces the 01-04 stub body: TanStack query (include_inactive) + 4 mutations invalidating `["targets"]`, success-only toasts, dialog/confirmation orchestration
- `apps/web/app/(dashboard)/layout.tsx` - mounts `<Toaster>` bottom-right (sonner had no host)
- `apps/web/lib/api/client.ts` - adds the `patch` method
- `apps/api/tests/e2e/test_targets_ui.py` - 4 sync-Playwright tests (register / mask-on-edit / deactivate / inline-validation), uuid-unique names, UI login

## Decisions Made

- **api.patch added (Rule 3):** the 01-04 client wrapper exposed get/post/put/delete but not patch; the targets PATCH endpoint needs it. Added a one-method patch mirroring the existing wrappers (same refresh-once-then-retry path).
- **Toaster mounted (Rule 3):** sonner was installed in 01-04 but never rendered into the tree, so `toast.success(...)` would no-op. Mounted `<Toaster theme="dark" position="bottom-right" />` in the dashboard layout per the UI-SPEC interaction defaults — without it the e2e toast assertions (and the actual UX) would fail.
- **Reactivate is unconfirmed:** per UI-SPEC only deactivate is destructive and confirms; Reactivate fires `PATCH is_active=true` directly from the row menu.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] client.ts had no PATCH method**
- **Found during:** Task 1 (writing lib/api/targets.ts)
- **Issue:** the targets update endpoint is PATCH, but the 01-04 fetch wrapper only implemented get/post/put/delete
- **Fix:** added `api.patch` mirroring the existing methods (reuses the 401 refresh-once-then-retry path)
- **Files modified:** apps/web/lib/api/client.ts
- **Commit:** 205a11c

**2. [Rule 3 - Blocking] sonner Toaster was never mounted**
- **Found during:** Task 2 (wiring success toasts)
- **Issue:** sonner is installed (01-04) but no `<Toaster>` existed in the tree; `toast.success` would render nothing
- **Fix:** mounted `<Toaster theme="dark" position="bottom-right" />` in the dashboard layout
- **Files modified:** apps/web/app/(dashboard)/layout.tsx
- **Commit:** 0231b41

**3. [Rule 1 - Bug] e2e label collisions + URL normalization**
- **Found during:** Task 3 (running the e2e suite against the live stack)
- **Issue:** (a) `get_by_label("Name")` matched both "Name" and "Username" (substring); (b) the API normalizes base_url via Pydantic HttpUrl, appending a trailing slash, so the exact-match URL assertion failed
- **Fix:** used `exact=True` on label getters; matched the base URL by prefix (the rendered cell is `https://example.com/`)
- **Files modified:** apps/api/tests/e2e/test_targets_ui.py
- **Commit:** 5e34e8e

**Total deviations:** 3 auto-fixed (2 blocking infra gaps inherited from 01-04, 1 test-authoring bug). None changed scope or the UI contract.

## Issues Encountered

- The web container bind-mounts source and hot-reloads, but the Turbopack dev server served the stale (pre-edit) `/targets` route on first run — a `docker compose restart web` forced a clean recompile and the new enabled "Register target" button appeared. New deps were not added, so no image rebuild was needed.
- Pre-existing untracked runtime logs (alembic-run.log, uvicorn.log, verify-t2.log) and `.claude/` remain out of scope (logged for plan 01-08).

## Known Stubs

None — every surface is wired to the live API. The 01-04 `/targets` stub (disabled button, empty-state-only body) is fully replaced.

## User Setup Required

None — the stack self-builds; admin credentials already in `.env`.

## Next Phase Readiness

- PLAT-01 is now complete (API half in 01-05, UI half here) — ROADMAP criterion 3 (register target through UI and API, listed, credentials masked end-to-end) is proven by the e2e suite
- Phase 4 Explorer consumes the targets created here (schema + get_decrypted_credentials surface from 01-05)
- Exclusive-resource rule honored: no other plan's compose/build/test commands ran during this plan

## Self-Check: PASSED

All 6 key artifact files exist on disk; commits 205a11c, 0231b41, 5e34e8e verified in git log; no file deletions in any commit; targets UI e2e 4/4 green and login e2e 5/5 still green against the live stack; `npm run build` clean.

---
*Phase: 01-foundation-dev-environment*
*Completed: 2026-06-13*
