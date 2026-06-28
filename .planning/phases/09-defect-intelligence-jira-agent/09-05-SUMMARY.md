---
phase: 09-defect-intelligence-jira-agent
plan: 05
subsystem: web
tags: [defects-ui, review-queue, calibration-panel, class-badge, confidence-meter, auth-gated-artifacts, honest-states, zero-new-deps, mocked-e2e]

# Dependency graph
requires:
  - phase: 09-defect-intelligence-jira-agent (09-04)
    provides: "/api/defects list/detail/calibration/apply/reject payloads (DefectSummaryResponse/DefectDetailResponse/CalibrationResponse) the zod client mirrors"
  - phase: 07-execution-engine-workers
    provides: "the auth-gated /api/executions/{run_id}/artifacts/{flow_id}/{name} route the attachment links target (run_id-derived containment guard)"
  - phase: 06-scenario-generation
    provides: "the scenarios list+detail+apply/reject UI pattern (TanStack Query, filter segments, confirm Dialog, invalidate+toast, inline errors) this clones"
provides:
  - "apps/web/lib/api/defects.ts: the zod client mirroring schemas/defect.py (summary/detail/calibration + apply/reject) over the cookie-riding api wrapper"
  - "the /defects review-queue list (status+class filter segments, six-column drafts-first table, calibration panel atop)"
  - "the /defects/[id] detail/review (proposed issue + cited evidence + auth-gated attachments + apply create-vs-update + reject confirm)"
  - "components/defects/: class-badge (word+icon+hue), confidence-meter (token-styled native progressbar banded off the server threshold), calibration-panel (read-only), defect-states (status badge + inline error)"
  - "one Defects sidebar item (Bug icon) appended after Executions"
affects: [10 (the rich traceability-chain viz + classification/defect dashboards consume the same /api/defects payloads)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Token-styled native role=progressbar confidence meter banded off the SERVER confidence_threshold (never a client literal) — the Phase-7 styled-native progress precedent; zero new deps (recharts present but intentionally NOT used)"
    - "Class/status conveyed by WORD + lucide icon + hue, never color alone (WCAG 1.4.1) — the Phase-7 verdict-badge precedent"
    - "Auth-gated artifact URL built client-side from the run-relative basename (per-segment encodeURIComponent) via the Phase-7 route — never a raw filesystem path (T-09-18)"
    - "No optimistic updates: status/Jira-key/create-vs-update render strictly from the server response after each mutation; Apply is an honest pending->result (Filing…) transition (T-09-21)"
    - "Mocked-API e2e (page.route over every /api/defects* call) — no real Jira, no provider keys, every UI-SPEC state mockable (the scenarios/executions e2e precedent)"

key-files:
  created:
    - apps/web/lib/api/defects.ts
    - apps/web/app/(dashboard)/defects/page.tsx
    - apps/web/app/(dashboard)/defects/[id]/page.tsx
    - apps/web/components/defects/calibration-panel.tsx
    - apps/web/components/defects/class-badge.tsx
    - apps/web/components/defects/confidence-meter.tsx
    - apps/web/components/defects/defect-states.tsx
    - apps/web/tests/e2e/defects.spec.ts
  modified:
    - apps/web/components/app-sidebar.tsx

key-decisions:
  - "A small components/defects/defect-states.tsx holds the defect status badge + the inline error state (the scenarios/status-badge + scenario-states split) — keeps the badge/error reusable across list+detail; not a new shadcn block (a plain composition over the vendored badge/button)"
  - "The attachment URL is built per-segment-encoded from the backend's run-relative AttachmentRef.path joined under /api/executions/{run_id}/artifacts/... so a multi-segment relative path (e.g. flow-0/test/trace.zip) targets the Phase-7 containment-guarded route and can never become an absolute path"
  - "The Apply label honors the server dedup honestly: a draft already carrying a jira_key reads 'Apply — update {key}', otherwise 'Apply — create Jira issue' — the create-vs-update decision is never fabricated"
  - "Evidence is opaque JSON (schemas/defect.py types it dict|None); the detail reads the documented fields (error_type/dom_diff/healing_history/infra_health) with honest fallbacks, falling back to error_text for the error type"

requirements-completed: [JIRA-02, JIRA-04]

# Metrics
duration: ~40min
completed: 2026-06-28
---

# Phase 9 Plan 05: Defects Review-Queue UI Summary

**The minimal Defects review-queue UI shipped EXACTLY to 09-UI-SPEC over the Plan-04 /api/defects API: a review-queue list (status+class filter segments, a drafts-first six-column table with the class badge [word+icon+hue], the token-styled confidence meter banded off the SERVER threshold, the source test↔flow↔execution refs, the status, the optional Jira key) atop a READ-ONLY calibration panel (accuracy/precision vs the ≥85%/≥90% gates, the calibrated threshold, the autonomy-flag state), plus a detail/review surface (the proposed Jira issue + cited evidence + auth-gated artifact links from run-relative basenames + Apply [honest pending→result, create-vs-update from the server dedup] + Reject confirm) — all honest (Jira-not-configured/empty/error-with-path-forward), all server-authoritative (no fabricated class/confidence/status/Jira-key/accuracy), with ZERO new shadcn and ZERO new frontend deps, proven by a 14-test mocked-API e2e suite.**

## Performance
- **Duration:** ~40 min
- **Completed:** 2026-06-28
- **Tasks:** 3 of 3
- **Files:** 9 (8 created, 1 modified)

## Accomplishments
- `lib/api/defects.ts` mirrors `schemas/defect.py` field-for-field: `defectSummarySchema` (id/run_id/flow_id/classification/confidence/fingerprint/jira_key/status/created_at/updated_at), `defectDetailSchema` (the summary + `proposed_issue` {summary/description/enriched/steps/expected/actual/severity/priority} + `evidence` + `attachments` + `confidence_threshold` + `last_action`), `calibrationSchema` (nullable accuracy/precision + threshold + autonomous_enabled). Fetchers `listDefects(status, klass)`/`defectDetail(id)`/`calibration()`/`applyDefect(id)`/`rejectDefect(id)` ride the cookie-bearing `api` wrapper (no token handling); the list URL adds `&class=` only when a class is set.
- The **class badge** maps the three classes to their UI-SPEC word+icon+token — infrastructure→ServerCog+`--status-neutral`, automation→Wrench+`--status-quarantine`, product_defect→Bug+`--status-fail` — the WORD + an aria-hidden icon always render (never color alone, WCAG 1.4.1).
- The **confidence meter** is a token-styled native `role="progressbar"` (bg-secondary track + green fill ≥ the threshold else amber) with the mono numeral always present and an accessible name combining the value and whether it clears the threshold — the band edge is the SERVER `confidence_threshold`, never a client literal. No recharts, no new dep.
- The **/defects list** renders the calibration panel atop, the two accent-underlined styled-native filter segment groups (`?status=` default Drafts, `?class=` default All — both deep-linkable), and the six-column drafts-first→confidence-desc→updated-desc queue with the class badge / confidence meter / source refs / status badge (+ the mono Jira-key link on an applied row) / mono timestamp; every empty/loading/inline-error state with the exact UI-SPEC copy (errors inline, never a toast).
- The **calibration panel** is read-only: accuracy vs ≥85% + precision vs ≥90% (each a met/"Not met yet"/"—" indicator with its WORD), the calibrated threshold, and the autonomy-flag display (On/Off + the gate caption) — no write toggle (D-04); honest nulls render the "not measured yet" copy; every tile value carries the UI-SPEC aria-label; the flag is `role="status"` text.
- The **/defects/[id] detail** renders the breadcrumb + header (summary + class badge + status badge + mono "Defect {id}" + the confidence meter), the Proposed Jira issue card (the seven fields + the honest "written without an LLM" caption gated on `enriched`), the Evidence card (error type / DOM diff / healing history / infra health + the cited-signals caption + the mono Fingerprint caption), the Attachments card (five kinds, each an auth-gated URL built client-side from the run-relative basename via `/api/executions/{run_id}/artifacts/...` — never a raw path; honest absent-artifact captions), and the action bar — Apply (the create-vs-update label from the server, the "Filing…" pending state, the success toast, the inline apply-failed+Retry keeping it a draft, the disabled not-configured 400 caption) + the Reject destructive confirm Dialog. `invalidate()` covers detail+list+calibration; no optimistic updates.
- One **Defects sidebar item** (Bug icon, `/defects`) appended after Executions; active via the existing `pathname.startsWith`.

## Task Commits
1. **Task 1: zod client + class badge + confidence meter** — `4021191` (feat)
2. **Task 2: list page + read-only calibration panel + sidebar item** — `86b8973` (feat)
3. **Task 3: detail/review page + mocked-API e2e** — `6327894` (feat)

(Plan metadata: see the final docs commit.)

## Files Created/Modified
- `apps/web/lib/api/defects.ts` - the zod client mirroring schemas/defect.py (summary/detail/calibration + apply/reject)
- `apps/web/app/(dashboard)/defects/page.tsx` - the review-queue list + two filter segment groups + the calibration panel atop
- `apps/web/app/(dashboard)/defects/[id]/page.tsx` - the detail/review (proposed issue + evidence + auth-gated attachments + apply/reject)
- `apps/web/components/defects/calibration-panel.tsx` - the read-only four-tile calibration display (met/unmet/not-measured + autonomy-flag, no write toggle)
- `apps/web/components/defects/class-badge.tsx` - the class badge (word+icon+hue per UI-SPEC, never color alone)
- `apps/web/components/defects/confidence-meter.tsx` - the token-styled native progressbar banded off the server threshold
- `apps/web/components/defects/defect-states.tsx` - the defect status badge + the inline error state (never a toast)
- `apps/web/tests/e2e/defects.spec.ts` - the 14-test mocked-API e2e (list/calibration/detail/apply/update/reject/404)
- `apps/web/components/app-sidebar.tsx` - appends the one Defects nav item (Bug icon) after Executions

## Decisions Made
- **A `components/defects/defect-states.tsx`** holds the status badge + the inline error state — mirrors the scenarios `status-badge.tsx` + `scenario-states.tsx` split so both are reusable across the list and the detail. A plain composition over the vendored `badge`/`button` (not a new shadcn block).
- **The attachment URL is per-segment `encodeURIComponent`-encoded** from the backend's run-relative `AttachmentRef.path` joined under `/api/executions/{run_id}/artifacts/...`, so a multi-segment relative path (e.g. `flow-0/test/trace.zip`) targets the Phase-7 containment-guarded route and can never escape into an absolute path (T-09-18).
- **The Apply label honors the server dedup honestly:** a draft already carrying a `jira_key` reads "Apply — update {key}"; otherwise "Apply — create Jira issue". The success toast picks "Issue updated — {key}" vs "Issue filed — {key}" off the `last_action` the server reports. Never fabricated.
- **Evidence is rendered from the opaque `evidence` JSON** (schemas/defect.py types it `dict | None`): the detail reads the documented `error_type`/`dom_diff`/`healing_history`/`infra_health` fields with honest "Not recorded."/absent fallbacks, falling back to `error_text` for the error type.

## Deviations from Plan
None - plan executed exactly as written. Two test-only adjustments during the e2e (not behavioural): (1) the class-badge assertions were targeted via the badge `aria-label` ("Class: Product defect") because the class-filter segment buttons legitimately duplicate the class WORDS — a strict-mode ambiguity in the test, not a page bug; (2) the class-filter empty-state mock registers the general `?status=draft*` route BEFORE the specific `?status=draft&class=infrastructure` route so Playwright's reverse-registration matching returns the empty result for the filtered request.

## Issues Encountered
- The first full e2e run cold-compiled the new `/defects` and `/defects/[id]` routes under `next dev`, which exceeded the 30s navigation timeout on the list tests; once warm they pass in ~2-3s each. A second transient failure was a `browserContext.newPage` spawn timeout under parallel load (infra flake) — the test passes in isolation (3.4s) and on the clean re-run all 14 pass.

## Verification
- `cd apps/web && npx tsc --noEmit` → clean (the whole web app typechecks against the new client + pages).
- `cd apps/web && npx eslint "app/(dashboard)/defects" components/defects components/app-sidebar.tsx lib/api/defects.ts tests/e2e/defects.spec.ts` → clean.
- `cd apps/web && npx playwright test tests/e2e/defects.spec.ts` → 14 passed (every UI-SPEC state green against the MOCKED API; no real Jira, no keys).
- `cd apps/web && git diff --exit-code package.json package-lock.json` → clean (ZERO new frontend deps; recharts not newly used; no new shadcn add).
- Live classify→draft→apply→dedup against a real Jira Cloud is Manual-Only (the UI is proven against a mocked API).

## User Setup Required
None for this UI plan. Live Jira filing/dedup remains Manual-Only (a real Jira Cloud instance + `JIRA_URL`/`JIRA_EMAIL`/`JIRA_API_TOKEN`/`JIRA_PROJECT_KEY`, and `JIRA_AUTONOMOUS_ENABLED=true` only after a human confirms accuracy ≥85% + draft precision ≥90% — see 09-04-SUMMARY). Without a provider key the proposed-issue description shows the honest "written without an LLM" caption.

## Next Phase Readiness
- The Defects section is the human-in-the-loop review surface D-04's autonomy gate requires — a human can now read the calibration numbers and apply/reject each draft before the autonomy flag is flipped in config.
- Phase 10's rich traceability-chain visualization + classification/defect dashboards consume the same `/api/defects` payloads this plan renders; the source refs (run_id/flow_id/Jira key) are already surfaced on every row + the detail (JIRA-04).
- No blockers. No new package. tsc + eslint + the 14-test e2e are green; the package.json/lock diff is clean.

## Known Stubs
None. The calibration accuracy/precision render as the honest "not measured yet" state because Plan 04 persists no runtime accuracy store (QUAL-03 is a Manual-Only harness, documented in 09-04-SUMMARY) — this is the server-authoritative honest null, not a UI stub. Every other value (class/confidence/status/Jira-key/threshold/autonomy-flag) renders strictly from the server.

## Self-Check: PASSED
All 8 created files + the modified app-sidebar.tsx + this SUMMARY exist on disk; all 3 task commits (4021191, 86b8973, 6327894) exist in git history.

---
*Phase: 09-defect-intelligence-jira-agent*
*Completed: 2026-06-28*
