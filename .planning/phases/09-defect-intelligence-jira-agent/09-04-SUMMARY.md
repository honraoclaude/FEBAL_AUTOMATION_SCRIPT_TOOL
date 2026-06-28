---
phase: 09-defect-intelligence-jira-agent
plan: 04
subsystem: api
tags: [defect-pipeline, autonomy-gate, jira-dedup, traceability, draft-queue, fakejira, auth-gated-router, keyless]

# Dependency graph
requires:
  - phase: 09-defect-intelligence-jira-agent (09-01)
    provides: "classify_failure + Classification/Defect models + jira_* settings (autonomy OFF, calibrated threshold, per-run cap)"
  - phase: 09-defect-intelligence-jira-agent (09-03)
    provides: "JiraGateway Protocol + FakeJira (keyless) + build_adf + describe (no-key fallback)"
  - phase: 08-self-healing
    provides: "heals.py auth-gated review-router shape (list/apply/reject) the defects router clones"
  - phase: 07-execution-engine
    provides: "executions.py run_id-derived multi-segment artifact containment guard (reused for attachment paths)"
provides:
  - "autonomy.may_autofile(conf): pure flag-AND-calibrated-threshold gate (JIRA-02/D-04 — the core safety property)"
  - "pipeline.file_or_update(gateway, defect, artifacts, *, run_counter): fingerprint-label JQL dedup (hit=update, miss=create) under the per-run create cap (JIRA-03)"
  - "pipeline.run_defect_pipeline(db, run_id, flow_id, *, gateway, run_counter): post-run orchestrator — draft Defect row + traceability links + (gated) auto-file (JIRA-04)"
  - "/api/defects auth-gated review API (list/detail/calibration/apply/reject) registered in main.py"
  - "schemas/defect.py: DefectSummaryResponse + DefectDetailResponse (+ ProposedIssue/AttachmentRef) + CalibrationResponse"
affects: [09-05 (the Defects review UI consumes these payloads), 10 (traceability-chain rendering)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure structural autonomy gate over SHIPPED settings (flag AND calibrated threshold, never a literal — the heal_high_threshold discipline)"
    - "file-or-update dedup core returning a frozen FileResult(action, jira_key, counter) so the cap counter threads across flows + the create-vs-update decision reaches the UI"
    - "run_id-derived multi-segment artifact containment guard reused from executions.py (reject '',.,..,backslash + realpath containment) — never a request-body path"
    - "Auth-gated review router cloned from heals.py: router-level Depends(get_current_user), ORM-parameterized filters, _get_*_or_404, commit+refresh+log"
    - "Gateway monkeypatched to FakeJira in the router test (keyless apply path); not-configured AtlassianJira path asserted honest"

key-files:
  created:
    - apps/api/app/services/defects/autonomy.py
    - apps/api/app/services/defects/pipeline.py
    - apps/api/app/schemas/defect.py
    - apps/api/app/routers/defects.py
    - apps/api/tests/unit/test_autonomy_gate.py
    - apps/api/tests/unit/test_jira_dedup.py
    - apps/api/tests/integration/test_defect_pipeline.py
    - apps/api/tests/integration/test_defects_router.py
  modified:
    - apps/api/app/main.py

key-decisions:
  - "may_autofile reads settings.jira_autonomous_enabled AND settings.jira_confidence_threshold — never a literal; flag-off OR below-threshold never files (proven across the truth table)"
  - "file_or_update returns FileResult(action, jira_key, counter): updates are free (no cap consumption), creates consume one cap slot, at the cap a MISS returns action='none' and the draft persists (Pitfall 5)"
  - "run_defect_pipeline ALWAYS persists the draft Defect row (traceability link) before any filing; auto-file only when class=='product_defect' AND may_autofile"
  - "The router reuses pipeline._severity_priority + file_or_update (internal imports) so the apply path is byte-identical to the autonomous path; the proposed-issue prose routes through describe() (keyless deterministic fallback)"
  - "create_issue_link is best-effort (try/except) so a gateway hiccup never fails the file (the heals.py best-effort KG-append precedent)"

patterns-established:
  - "Pure flag-AND-threshold autonomy gate as a standalone module (autonomy.py) — auditable, keyless, monkeypatch-testable"
  - "Dedup+cap core returning a threaded counter + a create-vs-update action enum"

requirements-completed: [JIRA-02, JIRA-03, JIRA-04]

# Metrics
duration: ~35min
completed: 2026-06-28
---

# Phase 9 Plan 04: Defect Pipeline + Autonomy Gate + Auth-Gated Review API Summary

**The defect draft-queue lifecycle wired end-to-end behind the keyless JiraGateway: every product-failure classification persists a draft Defect row with the run_id/flow_id test↔flow↔execution traceability links (JIRA-04), files-or-updates to Jira via server-built fingerprint-label JQL dedup under a per-run create cap (JIRA-03), all gated by the OFF-by-default autonomy flag + the QUAL-03-calibrated confidence threshold (JIRA-02) — exposed through the auth-gated /api/defects review router and proven keyless over FakeJira.**

## Performance

- **Duration:** ~35 min
- **Completed:** 2026-06-28
- **Tasks:** 3 of 3
- **Files modified:** 9 (8 created, 1 modified)

## Accomplishments
- `may_autofile(conf)` is a pure structural gate: `settings.jira_autonomous_enabled AND conf >= settings.jira_confidence_threshold` — flag-off never files (even at conf 100), below-threshold never files (even flag-on), both true may file. The cutoff tracks the calibrated setting, never a literal (proven by raising the threshold to 90 in a test).
- `file_or_update` builds the fixed server-side `labels = "fp-<hash>" AND statusCategory != Done` JQL (no user text — T-09-13): a HIT adds a comment + re-attaches each artifact (UPDATE, no cap consumption); a MISS creates an issue with the `fp-<hash>` label + ADF description + attachments + a best-effort issue-link, consuming one cap slot; at the cap a MISS returns `action='none'` and the draft persists (Pitfall 5).
- `run_defect_pipeline` ALWAYS persists a Classification + a draft Defect row (with the fingerprint + the run_id/flow_id JIRA-04 links) for a product-failure classification, regardless of cap/autonomy; auto-files only for an enabled, above-threshold `product_defect`.
- Artifact paths are resolved under `run_dir(run_id)` via the executions.py multi-segment containment guard (reject empty/`.`/`..`/backslash + realpath containment) — never a request-body path (T-09-15); the FakeJira attachment assertion confirms the absolute resolved path, not the raw run-relative string.
- `/api/defects` review router: list (status + class ORM-parameterized filters, drafts-first → confidence-desc → updated-desc sort), detail (proposed issue via `build_adf`/`describe` + cited evidence + run-relative attachment refs + the calibrated `confidence_threshold`), calibration (read-only numbers + autonomy flag, honest nulls), apply (honest not-configured 400 when no token; else file-or-update → persist jira_key + `applied` + report create-vs-update), reject (status flag flip). Router-level `Depends(get_current_user)` 401s every endpoint unauth.
- Registered in `main.py` after `heals_router` (before `stubs_router`) so its real routes win over any residual stub.

## Task Commits

1. **Task 1: Autonomy gate + fingerprint-label JQL dedup + per-run cap (TDD)**
   - RED: `1b8c145` (test) — failing autonomy-gate truth table + JQL dedup/cap specs
   - GREEN: `23616c6` (feat) — autonomy.py + pipeline.file_or_update
2. **Task 2: Pipeline draft-row + traceability + autonomy over FakeJira** - `0a54427` (test) — `run_defect_pipeline` integration proof (impl shipped in `23616c6`)
3. **Task 3: Auth-gated /api/defects router + registration**
   - `f48d906` (feat) — schemas/defect.py + routers/defects.py + main.py registration
   - `4890b67` (test) — the auth-gated list/detail/calibration/apply/reject proof over FakeJira

**Plan metadata:** see final docs commit.

## Files Created/Modified
- `apps/api/app/services/defects/autonomy.py` - `may_autofile(conf)` pure flag-AND-calibrated-threshold gate (JIRA-02/D-04, T-09-12)
- `apps/api/app/services/defects/pipeline.py` - `file_or_update` (dedup+cap+attach+link) + `run_defect_pipeline` (draft-row + traceability + gated auto-file) + the severity→priority map + the run_id-derived artifact containment guard
- `apps/api/app/schemas/defect.py` - `DefectSummaryResponse` + `DefectDetailResponse` (with `ProposedIssue`/`AttachmentRef`) + `CalibrationResponse`
- `apps/api/app/routers/defects.py` - the auth-gated review API (list/detail/calibration/apply/reject)
- `apps/api/app/main.py` - registers `defects_router` after `heals_router`
- `apps/api/tests/unit/test_autonomy_gate.py` - the autonomy truth table over monkeypatched settings
- `apps/api/tests/unit/test_jira_dedup.py` - the JQL dedup + cap + server-built-label proof over FakeJira
- `apps/api/tests/integration/test_defect_pipeline.py` - the draft-row + traceability + autonomy-on/off pipeline proof
- `apps/api/tests/integration/test_defects_router.py` - the auth-gate + apply-create/update + reject + not-configured proof

## Decisions Made
- **`file_or_update` returns a frozen `FileResult(action, jira_key, counter)`** so the per-run cap counter threads across flows and the create-vs-update decision reaches the UI (the apply path reports it via `last_action` on the detail payload).
- **The router reuses `pipeline.file_or_update` + `pipeline._severity_priority`** (internal imports) so the human-apply path is byte-identical to the autonomous-file path — one dedup/cap implementation, two callers.
- **`run_defect_pipeline` commits the draft FIRST, then auto-files** — the JIRA-04 traceability link is durable before any Jira interaction, so a cap/autonomy/gateway outcome can never lose the classification (Pitfall 5).
- **calibration accuracy/precision are honest nulls** — this phase persists no runtime accuracy store (QUAL-03 is a Manual-Only harness); the UI renders the "not measured yet" copy. confidence_threshold + autonomous_enabled are the shipped settings.

## Deviations from Plan
None - plan executed exactly as written. Two test-only adjustments during GREEN (not behavioural): (1) the dedup test asserted the run-relative artifact string but the implementation correctly resolves to an ABSOLUTE run_dir-derived path (the containment guard) — the assertion was corrected to verify the secure absolute path; (2) the router test's seed-lookup keyed on run_id returned a shared id when two defects shared a run_id — switched the lookup to the unique fingerprint. The unregistered `pytest.mark.unit` marker (a collection warning, not an error) was dropped from the two new unit tests to match the codebase convention.

## Issues Encountered
- `GET /api/defects/calibration` vs `GET /api/defects/{defect_id}`: the int-typed `{defect_id}` converter would 422 on the literal "calibration" — resolved by declaring `/calibration` BEFORE `/{defect_id}` in the router (FastAPI matches in declaration order).
- The `?class=` query param: `class` is a Python keyword, so the handler uses `class_` with `Query(alias="class")` to accept the spec's `?class=` query name.

## Verification
- `uv run python -m pytest tests/unit/test_autonomy_gate.py tests/unit/test_jira_dedup.py -q` → 10 passed (the gate truth table + the JQL dedup/cap over FakeJira)
- `uv run python -m pytest tests/integration/test_defect_pipeline.py -q` → 3 passed (draft-row + traceability + autonomy on/off + dedup)
- `uv run python -m pytest tests/integration/test_defects_router.py -q` → 10 passed (auth gate + apply create/update + reject + not-configured)
- `uv run python -m pytest tests/unit/test_no_llm_in_classifier.py -q` → 1 passed (the defects package stays off the LLM decision plane)
- `uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional" -q` → 408 passed, 142 deselected (the full deterministic suite green)

## User Setup Required
**Live Jira filing/dedup is Manual-Only** (no Jira instance/token in dev). The whole file-or-update/dedup/cap/autonomy/apply contract is proven keyless via FakeJira. To exercise the live path: set `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, and (for autonomous filing) flip `JIRA_AUTONOMOUS_ENABLED=true` once a human has confirmed accuracy (≥85%) + draft precision (≥90%). The description LLM enrichment additionally needs a provider key; without one the deterministic fallback writes the prose and the UI shows the honest "written without an LLM" caption.

## Next Phase Readiness
- The `/api/defects` list/detail/calibration/apply/reject payloads are the exact field set Plan 05's zod client + Defects review UI mirror (`DefectSummaryResponse`/`DefectDetailResponse`/`CalibrationResponse`).
- `run_defect_pipeline` is ready to be invoked from the post-retry product-failure path; the per-run counter threads across flows.
- No blockers. No new package. The deterministic suite is green.

## Self-Check: PASSED

All 8 created source/test files + this SUMMARY exist on disk; all 5 task commits (1b8c145, 23616c6, 0a54427, f48d906, 4890b67) exist in git history.

---
*Phase: 09-defect-intelligence-jira-agent*
*Completed: 2026-06-28*
