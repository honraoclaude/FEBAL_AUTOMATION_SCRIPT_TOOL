# Phase 9: Defect Intelligence & Jira Agent - Context

**Gathered:** 2026-06-27
**Status:** Ready for planning (needs --research-phase — the deterministic classification rule/evidence taxonomy + 0-100 confidence formula, the QUAL-03 hand-labeled failure set, the atlassian-python-api v3 create/attach/JQL/link shapes, and the failure-fingerprint normalization have no canonical reference)

<domain>
## Phase Boundary

Failures triage themselves. Every failure is RETRIED (Phase-7 retry loop) then CLASSIFIED — Infrastructure (browser crash, network, environment) / Automation (locator, test data) / Product Defect (functional, validation, performance, API) — with a 0–100 confidence citing evidence (error type, DOM diff, healing history, infra health). Classification accuracy is MEASURED against a hand-labeled failure set (>85%) which calibrates the Jira confidence threshold BEFORE any autonomous filing. High-confidence product defects become Jira Cloud issues (summary, description, steps-to-reproduce, expected/actual, severity, priority, screenshots, video, logs) that START in a DRAFT/review queue; autonomous creation activates ONLY above the threshold AND after measured >90% draft precision. Duplicate failures UPDATE the existing issue (failure fingerprint + JQL search) instead of creating new ones, capped per run. Every created issue links test↔flow↔execution in the traceability chain. Delivers DEF-01/02/03, JIRA-01/02/03/04, QUAL-03. UI hint: yes (the draft/review queue + traceability — see the open UI-scope question).

**In scope:** the deterministic 3-way classifier + 0-100 confidence over the evidence signals (DEF-01/02); the QUAL-03 hand-labeled-failure-set accuracy harness (>85%) that calibrates the threshold (DEF-03); the Jira Agent — create Jira Cloud issues with full evidence/attachments via atlassian-python-api (JIRA-01); the draft/review queue + the human-gated autonomous-filing flag (JIRA-02); failure-fingerprint + JQL dedup (update-not-duplicate) + per-run cap (JIRA-03); test↔flow↔execution links surfaced in the traceability chain (JIRA-04).
**Out of scope (own phases):** the dashboards that VISUALIZE classification trends / defect analytics + the rich traceability-chain RENDERING + RBAC + Elasticsearch search (Phase 10 — this phase PERSISTS the classification + defect + link data and exposes a minimal review-queue + API; Phase 10 renders the analytics/traceability views); K8s/Prometheus defect metrics (Phase 11). Self-healing (Phase 8 — its fail-as-defect outcome + heal_audit FEED classification here). The execution engine/retry loop (Phase 7 — reused, not rebuilt).

</domain>

<decisions>
## Implementation Decisions

### Classifier engine (DEF-01/02)
- **D-01:** DETERMINISTIC-FIRST classifier. Rules over the evidence signals produce the class + a 0–100 confidence: error-type taxonomy + signal heuristics (a locator failure after a failed/quarantined heal → Automation; a browser-crash/network/timeout/env error → Infrastructure; an assertion failure on a successfully-loaded page, or a seeded-bug-style functional/validation/API error → Product Defect). The gateway LLM is used ONLY to enrich the Jira issue DESCRIPTION prose (operation_type e.g. defect.describe, run_id), with the deterministic no-key fallback — NEVER for the class/confidence decision. Keyless, calibratable, reproducible; the QUAL-03 accuracy measurement is deterministic and runs without provider keys; no spend in the classification loop. (Research: the concrete evidence taxonomy → class mapping + the confidence formula/weights, tuned by the QUAL-03 labeled set.)
- **D-02 (DEF-02):** Classification runs AFTER the Phase-7 retry loop (a failure is retried first; a pass-on-retry is flaky/infra, an all-fail is a real failure to classify) and CITES evidence: error type (from the TestResult output), DOM diff + healing history (from heal_audit), infra health (research the source — container/healthcheck state and/or an error-pattern signal). The Phase-7 binary retry/flaky classifier (worker/classifier.py) is an INPUT; DEF-01 is the richer 3-way + confidence built on top, not a replacement.

### Jira client (JIRA-01/03)
- **D-03:** atlassian-python-api 4.x — the CLAUDE.md-recommended client once JQL search + issue links + attachments are all in scope (exactly Phase 9): native enhanced_jql (nextPageToken) pagination + v3/ADF + attachments + issue links. It is SYNC (requests) → call via `anyio.to_thread.run_sync` from the FastAPI/async paths. ONE gated new dependency (checkpoint:human-verify install task). Auth = Jira Cloud email + API token (config, never logged). (Research: the exact create-issue ADF body, add-attachment, transition, JQL-search, and create-issue-link calls in 4.x.)

### Autonomous-filing gate (JIRA-02 / DEF-03 / QUAL-03)
- **D-04:** Autonomous filing is OFF by default — a config/settings flag (e.g. `jira_autonomous_enabled = False`), per target. The QUAL-03 labeled-set harness measures classification accuracy and the draft queue measures draft precision; the USER reviews those numbers and EXPLICITLY flips the flag on (human-in-the-loop). Until then ALL issues stay in the draft/review queue (apply/reject by a human). Even with the flag on, autonomous creation requires confidence ≥ the calibrated threshold. No autonomous Jira ticket can ever be filed before a human confirms accuracy ≥85% AND draft precision ≥90%. Conservative + auditable.

### Fingerprint, dedup & cap (JIRA-03)
- **D-05:** Failure fingerprint = a stable hash of (class + NORMALIZED error message [strip numbers/ids/timestamps/uuids] + flow id + failing step). Stored as a Jira LABEL (`fp-<hash>`) on the created issue AND on the local defect row. Dedup = JQL `labels = "fp-<hash>" AND statusCategory != Done` — a hit UPDATES that issue (add a comment + re-attach the new evidence), a miss CREATES one. Per-run ticket-creation cap via a config'd counter (`jira_max_tickets_per_run`). The local defect row also stores the Jira issue key for the traceability chain.

### Claude's Discretion / for research (--research-phase)
- The concrete evidence-taxonomy → class rules + the 0-100 confidence formula/weights (tuned by the labeled set).
- The QUAL-03 HAND-LABELED failure set: reuse the seeded-bug (Phase 6) + benign/breaking mutation builds (Phase 8) + simulated infra errors to generate KNOWN-class failures (Product = seeded bug; Automation = un-healed locator drift; Infrastructure = injected network/crash), measured KEYLESSLY; how accuracy + the threshold calibration are computed + stored.
- The defect/classification data model (a `defects` / `classifications` table + the test↔flow↔execution links; migration 0009 after 0008) + the heal_audit/execution_history evidence joins.
- The atlassian-python-api v3 call shapes (create + ADF description, add-attachment for screenshots/video/logs, transitions, JQL, issue links); the anyio.to_thread wrapping; the draft-queue model + apply/reject flow.
- The infra-health evidence source.
- The traceability-chain representation (Postgres FKs + Jira key, and/or KG links) exposed for Phase 10.

### UI scope (RESOLVED — D-06)
- **D-06:** Phase 9 SHIPS a MINIMAL draft-review-queue UI (it has its own UI-SPEC). Scope: a review-queue screen — list draft Jira issues + the rendered classification (class + 0-100 confidence + cited evidence) + the before/after / steps-to-reproduce / attachment links + apply (file/update to Jira) / reject, and a calibration panel surfacing the QUAL-03 accuracy + draft-precision numbers the human reviews before flipping the autonomy flag (D-04). The RICH traceability-chain VISUALIZATION + classification/defect DASHBOARDS + RBAC defer to Phase 10. JIRA-02 names the review queue as a success-criterion behavior and D-04's human gate needs this surface, so it is built here, minimally, to the locked design system (zero new shadcn / native-styled, like Phase 6/7).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — DEF-01/02/03, JIRA-01/02/03/04, QUAL-03.
- `.planning/ROADMAP.md` (Phase 9 section) — the 5 success criteria.

### Locked stack & carried conventions
- `CLAUDE.md` — atlassian-python-api 4.x (Jira Cloud REST v3: create/attach/transition/JQL/links; enhanced_jql pagination; sync → anyio.to_thread); httpx 0.28 (already a dep, the v3 fallback); init_chat_model gateway (DESCRIPTION prose only here, no-key fallback); PyJWT auth-gated routers; SQLAlchemy/Alembic (defects + migration 0009). NOTE: the CLAUDE.md "create_agent tool-loop classifier" pattern is NOT adopted for the class/confidence decision (D-01 deterministic) — the LLM is description-only.

### Reusable seams (read the summaries + code)
- `apps/api/app/models/execution_history.py` (TestRun/TestResult/TestArtifact — verdict, error/output, artifact paths) + `.planning/phases/07-execution-engine-workers/07-03-SUMMARY.md` — the failure + evidence + artifact source.
- `apps/api/app/services/worker/classifier.py` + `07-03-SUMMARY.md` — the Phase-7 binary retry/flaky classifier (the DEF-02 retry-before-classify input).
- `apps/api/app/models/heal_audit.py` + `apps/api/app/services/healing/` + `.planning/phases/08-self-healing-engine/08-03-SUMMARY.md` + `08-05-SUMMARY.md` — healing history + DOM before/after diff (classification evidence); the fail-as-defect outcome that feeds classification; the per-element heal stats + the auth-gated `/api/heals` router pattern (the draft-queue router analog).
- `apps/api/app/services/llm_gateway.py` + `.planning/phases/02-llm-gateway/02-01-SUMMARY.md` — the gateway (operation_type, run_id, deterministic no-key fallback) for the description prose.
- `infra/targets/saucedemo/Dockerfile` (SEED_BUG + Phase-8 mutation build-args) + `apps/api/tests/functional/test_seeded_bug.py` + `test_healing_mutations.py` — the known-class failure generators for the QUAL-03 labeled set.
- `apps/api/alembic/versions/0008_*.py` — the migration chain (0009 chains down_revision='0008'; migrations live in apps/api/alembic/versions/, NOT app/alembic).
- `apps/api/app/routers/heals.py` + `executions.py` — the auth-gated router + get_current_user pattern for the draft-queue/defect API.

### Known issues / project-wide
- Empty provider keys → live classification ENRICHMENT (description prose) + live Jira filing are Manual-Only; the deterministic classifier + the QUAL-03 accuracy harness + fingerprint/dedup/cap + the draft queue are FULLY keyless-testable. A real Jira Cloud instance + API token is needed for live JIRA-01/03 (Manual-Only); the create/attach/JQL/link CONTRACT is testable against a mock/fake Jira client without a real instance.
- 3GB WSL cap + neo4j-off-during-runs sequencing carries forward.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- execution_history (TestResult error/verdict/artifacts) + worker/classifier.py — the failure signal + retry input.
- heal_audit + healing/ — DOM-diff + healing-history evidence; the fail-as-defect feed; the auth-gated /api/heals router as the draft-queue/defect-API analog.
- llm_gateway — description-prose enrichment (no-key fallback).
- seeded-bug + Phase-8 mutation builds + test_seeded_bug/test_healing_mutations — the known-class failure generators for the QUAL-03 labeled set.
- Postgres models + Alembic chain (latest 0008) — new defects/classifications table + migration 0009.
- atlassian-python-api (new gated dep) for Jira; httpx already present as the v3 fallback.
- apps/web shell + the Phase-5/6/7/8 table/card/list patterns + locked design system — the draft-review-queue UI (if Phase 9 ships one).

### Established Patterns
- Deterministic, pure-logic-split + fixture-unit-tested classifiers (kg/risk, healing/confidence, worker/classifier); gateway-only LLM with no-key fallback; keyless planted/seeded proofs for measurement harnesses; auth-gated routers; fresh SessionLocal; migrations in apps/api/alembic/versions/; gated new deps behind checkpoint:human-verify (aio-pika/recharts precedent).
- Carry forward: deterministic gates over LLM judgment for the decision (LLM is prose-only); human-in-the-loop safety gate (autonomous filing OFF by default, like the conservative heal banding); never fabricate (honest draft/empty states); secrets never logged (Jira token like the ci_token/encrypted-credentials pattern).

### Integration Points
- A classification service (deterministic engine over the evidence joins) hooked AFTER the Phase-7 retry/heal outcome; a defects/classifications model + migration 0009; the QUAL-03 labeled-set accuracy harness (reusing the seeded-bug/mutation builds); a Jira Agent service (atlassian-python-api via anyio.to_thread) + draft-queue + fingerprint/JQL dedup/cap; the autonomous-filing config flag; the traceability links; a minimal draft-review router/UI (UI gate decides scope).

</code_context>

<specifics>
## Specific Ideas

- The class/confidence DECISION is deterministic (keyless, calibratable, reproducible, QUAL-03-measurable without keys); the LLM only writes the human-readable Jira description (no-key fallback) — never the classification.
- Autonomous filing is structurally gated: OFF by default, unlocked only by an explicit human flip AFTER measured accuracy ≥85% + draft precision ≥90%, and even then only above the calibrated confidence threshold — the platform cannot file a real ticket on its own until a human confirms the numbers.
- Dedup is JQL-based on a fingerprint label (self-healing across the platform + external edits), not a local-table-only check — meeting the spec's "JQL search" requirement; per-run cap prevents ticket storms.
- The QUAL-03 labeled set is generated from KNOWN-class failures (seeded bug → Product; un-healed mutation → Automation; injected infra error → Infrastructure), so accuracy is measured deterministically.

</specifics>

<deferred>
## Deferred Ideas

- Classification/defect DASHBOARDS + trend analytics + the rich traceability-chain VISUALIZATION + RBAC + Elasticsearch-backed defect search → Phase 10 (this phase persists + exposes the data + a minimal review queue).
- An LLM create_agent tool-loop classifier → REJECTED for the class/confidence decision (deterministic, keyless, reproducible); the LLM is description-prose only.
- Local-DB-only dedup → REJECTED (JQL-based per the spec; the local row stores the Jira key for traceability but is not the dedup source of truth).
- K8s/Prometheus defect/classification metrics → Phase 11.
- Bi-directional Jira sync / webhooks (status flowing back from Jira) → not in v1 scope (out of phase).

None of these block Phase 9 — discussion stayed within the defect-intelligence + Jira scope.

</deferred>

---

*Phase: 9-defect-intelligence-jira-agent*
*Context gathered: 2026-06-27*
