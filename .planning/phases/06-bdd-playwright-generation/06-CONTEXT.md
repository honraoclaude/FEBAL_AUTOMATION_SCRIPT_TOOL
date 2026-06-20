# Phase 6: BDD & Playwright Generation - Context

**Gathered:** 2026-06-20
**Status:** Ready for planning (needs --research-phase — the structured Then→KG-reference assertion schema + the seeded-bug/N-run acceptance harness have no canonical reference)

<domain>
## Phase Boundary

Turn Phase 5's discovered, risk-scored flows into REVIEWED, quality-gated Gherkin scenarios and STABLE Playwright automation the user owns. Upgrades Phase 3's minimal one-scenario/one-spec generation into the real thing: scenario outlines with data-driven Examples, a syntax + no-vacuous-assertion quality gate, an approve/edit review queue (only approved scenarios feed codegen), a full Playwright project structure with locators sourced ONLY from the Element Repository, and an N-run stability + seeded-bug-detection acceptance gate. Delivers GEN-01..GEN-05. UI hint: yes (review queue → needs a UI-SPEC).

**In scope:** scenario generation (outlines + Examples) via the gateway; the gherkin-29.x syntax lint + structured no-vacuous-assertion gate; the Postgres scenarios review queue (status lifecycle + edit-in-place) + its UI; full Playwright codegen (pages/specs/fixtures/utils/data/reports) with Element-Repository-sourced locators + freehand-selector enforcement; the N-consecutive-run stability check + the dedicated seeded-bug SauceDemo build for breakage detection.
**Out of scope (own phases):** the execution ENGINE (suite tiers, RabbitMQ workers, artifacts — Phase 7; this phase reuses the Phase-3 subprocess runner for stability only), healing (Phase 8), defect/Jira (Phase 9), dashboards (Phase 10). Live generation needs provider keys → Manual-Only (like Phases 4-5); gates/enforcement/stability mechanics are deterministically testable.

</domain>

<decisions>
## Implementation Decisions

### Review queue (GEN-02)
- **D-01:** Generated scenarios persist as Postgres `scenarios` rows (linked to flow/run) with a status lifecycle (draft → approved / rejected) + edited Gherkin content + timestamps. The review queue lists drafts; codegen reads ONLY status=approved. (Postgres, not Neo4j — Neo4j is the discovered-structure graph; review state is relational.)
- **D-02:** Edit-in-place — the reviewer can edit a scenario's Gherkin in the UI and approve; saving RE-RUNS the syntax + no-vacuous-assertion gates so an edited scenario cannot bypass quality. (Matches "approve/edit review queue" literally.)

### Quality gates (GEN-03)
- **D-03:** STRUCTURED no-vacuous-assertion gate — generation emits each Then step annotated with the KG node/edge it asserts (a page state / element / Creates-Updates-Deletes outcome). The gate DETERMINISTICALLY verifies EVERY Then resolves to an existing assertion in the graph; any Then with no graph-backed outcome is rejected as vacuous. NOT LLM judgment, NOT heuristic text-match.
- **D-04:** Gates enforce at generation AND on edit/approve — gherkin 29.x syntax lint (`from gherkin.parser import Parser`, the parser pytest-bdd uses — see the carried gherkin/pytest-bdd conflict) + the assertion gate run when a scenario is generated (malformed/vacuous → not a valid draft) AND again on edit-save/approve. Nothing malformed or vacuous can reach approved → codegen. Deterministic, unit-testable on fixtures.

### Locator sourcing + codegen (GEN-04/05)
- **D-05:** EVERY locator comes from the Phase-5 Element Repository — codegen pulls each element's locator chain by element key and emits page objects referencing them; the LLM/template fills ONLY non-locator slots (step wiring, test data). A STATIC gate scans generated specs/pages and REJECTS any raw selector literal (page.locator("..."), CSS/xpath strings) not sourced from the repo (the GEN-05 "never freehand LLM selectors" enforcement). Deterministic, unit-testable.
- **D-06:** Full Playwright project structure (GEN-04) — Jinja2-templated page objects (from KG pages), specs (from approved scenarios), fixtures/conftest, utils, data models (from scenario-outline Examples), reports dir — the tests/pages/fixtures/utils/data/reports layout, under a TARGET/run-scoped path in the gitignored workspaces/ tree (consistent with Phase 3/4 artifacts). Jinja2 owns structure; LLM fills narrow slots (Phase-3 pattern, scaled).
- **D (GEN-01):** Scenario OUTLINES with data-driven Examples tables; the Examples data derives from the KG (BusinessEntity / form fields / validation rules from Phase 5) — research to specify the derivation.

### Stability + seeded-bug acceptance (GEN-05, the trust gate)
- **D-07:** N-consecutive-run stability — reuse the Phase-3 subprocess runner to execute a generated spec N times; accept ONLY if all N pass (flaky → rejected). N is env-configurable, default 3.
- **D-08:** A DEDICATED seeded-bug SauceDemo build (a second image/compose profile with a deliberate injected defect — e.g. a renamed element id / broken flow) is the "seeded-bug build of the target". Accepted tests run against it and MUST FAIL (proving real-breakage detection). The harness mechanics (run N times; run against the bug build; assert pass-then-fail) are DETERMINISTICALLY testable with a PLANTED template-rendered spec (no keys); the full live generate→stabilize→bug-detect is Manual-Only (needs keys).

### Claude's Discretion / for research (--research-phase)
- **The structured Then→KG-reference schema** (D-03): how the LLM emits the assertion target per Then (a step annotation / a sidecar mapping), how it resolves against the Neo4j graph, and the gate's exact resolution check. THE novel gate.
- **Examples-table data derivation** (GEN-01) from the KG (BusinessEntity, form fields, validation rules).
- **Page-object template structure + naming conventions**; how approved scenarios map to spec files; pytest-bdd step-def generation (the gherkin .feature → step defs → page objects wiring) vs plain pytest-playwright specs (reconcile with Phase-3's plain-spec choice and the pytest-bdd dependency).
- **The seeded-bug build mechanism** (build-arg/sed/modified image or compose profile) + the N-run + bug-build harness wiring; the seeded defect specifics on SauceDemo.
- **Regenerate-vs-approved reconciliation**: what happens to already-approved scenarios when the underlying flow/graph changes (stale-marking vs regenerate) — keep minimal this phase.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — GEN-01..GEN-05.
- `.planning/ROADMAP.md` (Phase 6 section) — the 5 success criteria (generate outlines+Examples; lint + no-vacuous gate; approve/edit review queue gates codegen; full Playwright structure + repo-sourced locators; N-run stability + seeded-bug detection).

### Locked stack & carried conflicts
- `CLAUDE.md` — pytest-bdd 8.1.x, gherkin-official, Jinja2 codegen, pytest-playwright, init_chat_model via the Phase-2 gateway only, Recharts (charts only) — confirms no extra viz lib for the review UI.
- **MEMORY `gherkin-pytest-bdd-conflict` (CRITICAL this phase):** a direct `gherkin-official==40.*` pin is INCOMPATIBLE with pytest-bdd 8.1 (hard-pins <30); gherkin-official is 29.x TRANSITIVE. Validate with `from gherkin.parser import Parser` (the parser pytest-bdd uses). Do NOT add a gherkin-official pin. CLAUDE.md's stack table is wrong here.
- `.planning/phases/03-tracer-bullet-minimal-end-to-end-loop/03-03-SUMMARY.md` + `03-04-SUMMARY.md` — the Phase-3 generation seam to UPGRADE: gateway-routed generate-bdd/generate-scripts, gherkin-validate-before-write, Jinja2 skeleton owns structure (LLM fills narrow slots), workspaces/<run_id>/ artifacts, the subprocess /execute runner (reused for N-run stability).
- `.planning/phases/05-knowledge-graph-flow-learning/05-02-SUMMARY.md` + `05-03-SUMMARY.md` — the Element Repository (locator chain + history per element, the GEN-05 locator source) + flows/risk (the GEN-01 generation input) + kg/reader read surface.
- `.planning/phases/02-llm-gateway/02-01-SUMMARY.md` — llm_gateway.complete(operation_type, run_id) for generation.
- `.planning/phases/01-foundation-dev-environment/01-04-SUMMARY.md` + the prior UI-SPECs — the locked design system the review-queue UI reuses; targets/explore/graph page patterns.

### Known issues
- `graph_mode down` leaves neo4j running (manual stop) — relevant since codegen reads the Element Repository (Neo4j) under graph_mode.
- Provider keys empty → live generation + live stability/seeded-bug are Manual-Only (project-wide note in STATE.md).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase-3 generation (`generate-bdd`/`generate-scripts` routers + services, gherkin validate, Jinja2 spec render, workspaces artifacts) — the seam to UPGRADE into outlines+Examples + the gates + full project codegen.
- Phase-3 `/execute` subprocess runner — reused for the N-run stability check (run a spec N times) and the seeded-bug run.
- Phase-5 Element Repository (kg/reader element_repository + locator chain/history) — the GEN-05 locator source; flows/risk (kg/reader flows) — the GEN-01 input.
- llm_gateway.complete — generation (operation_type e.g. generate.bdd / generate.scripts, run_id); deterministic no-key fallback pattern (Phase 5) applies.
- run_service / Postgres models + Alembic chain (latest 0005) — new `scenarios` table + migration 0006 chains after 0005.
- apps/web shell + targets/explore/graph pages + locked design system — the review-queue UI is new authenticated pages reusing shadcn table/card/badge/textarea/dialog.
- SauceDemo compose service + graph_mode — the seeded-bug build is a sibling image/profile; codegen reads Neo4j under graph_mode.

### Established Patterns
- Functional tests hit the live stack; graph-marked under graph_mode. Deterministic logic (lint gate, structured assertion gate on a fixture graph, freehand-selector static gate, review status transitions, N-run harness on a planted spec, seeded-bug pass/fail) unit-tested with fixtures + mocked gateway (no keys). Live generate→review→codegen→stabilize is live_llm/manual.
- Carry forward: gateway-only LLM; Jinja2-owns-structure / LLM-fills-slots; workspaces artifacts; subprocess (never in-process pytest) for runs; managed execute_write+read-back + parameterized Cypher for any Neo4j read (reads only here — no KG writes; the single-writer is Phase 5's kg/writer); auth-gated routers; fresh SessionLocal.

### Integration Points
- Upgraded generation service + new gate modules (lint/assertion/freehand-selector); new scenarios model + migration 0006 + review router; codegen module + Jinja2 templates; the N-run stability + seeded-bug harness; the seeded-bug SauceDemo compose addition; new web review-queue pages + sidebar nav.

</code_context>

<specifics>
## Specific Ideas

- The no-vacuous-assertion gate is the novel deterministic trust mechanism — a Then with no graph-backed outcome is rejected; this is checked against Neo4j, never by LLM judgment.
- GEN-05 has TWO enforcement teeth, both deterministic: the static freehand-selector gate (no raw selectors in generated code) AND the seeded-bug detection (accepted tests must fail on the bug build). Neither relies on the LLM.
- gherkin is 29.x transitive — do NOT pin gherkin-official 40.x (the recurring conflict). Reuse Phase-3's `from gherkin.parser import Parser`.
- Stability/seeded-bug mechanics are provable WITHOUT keys via a planted (template-rendered) spec — same trick as Phase 3's deterministic execute proof; only the live generate→stabilize chain needs keys.

</specifics>

<deferred>
## Deferred Ideas

- Execution ENGINE (suite tiers, RabbitMQ-distributed parallel runs, per-step artifacts, live run view) → Phase 7. This phase reuses the Phase-3 subprocess runner for stability only.
- Healing of generated tests when locators drift → Phase 8.
- Regenerate-vs-approved deep reconciliation (re-derive scenarios when the graph changes, merge with edits) → keep minimal this phase (stale-mark at most); richer reconciliation deferred.
- A node/edge graph visualization of scenario↔flow↔element links → out of scope (tabular as in Phase 5).
- LLM-based risk/quality scoring of scenarios → rejected; gates are deterministic.

None of these block Phase 6 — discussion stayed within the generation scope.

</deferred>

---

*Phase: 6-BDD & Playwright Generation*
*Context gathered: 2026-06-20*
