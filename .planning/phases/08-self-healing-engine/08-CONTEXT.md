# Phase 8: Self-Healing Engine - Context

**Gathered:** 2026-06-22
**Status:** Ready for planning (needs --research-phase — the deterministic candidate-scoring blend, the live re-validation gate, the confidence→outcome bands, and the benign-vs-breaking mutation catalog have no canonical reference)

<domain>
## Phase Boundary

UI changes stop breaking the suite: when a locator fails during execution because the UI shifted (not because of a real defect), a DETERMINISTIC healing engine finds an alternative via DOM similarity + visual similarity + accessibility attributes + historical locator mapping (along the priority chain data-testid → aria-label → role → text → xpath), re-validates the candidate against the LIVE page, and resolves to exactly one of three outcomes — auto-heal (high confidence + unique live match), quarantine for review (medium), fail-as-potential-defect (low). Assertions are NEVER weakened to make a test pass. Every heal is an auditable before/after diff with a confidence score that rewrites the generated page-object locator (heal-as-commit), appends to the knowledge graph's Element history, and records per-element heal-success / false-heal stats. A benign-vs-breaking mutation harness proves >90% heal success on benign UI changes AND a false-heal rate near zero on breaking changes (seeded bugs still fail). Delivers HEAL-01..04 + QUAL-02. UI hint: minor (quarantine review surface + per-element heal stats — likely a small UI-SPEC or fold into Phase-10 dashboards; confirm at plan time).

**In scope:** the deterministic healing engine (4 candidate strategies + blended confidence + live re-validation) INLINE in the Phase-7 worker (HEAL-01); the 3-outcome resolution with conservative banding + the never-weaken-assertions invariant (HEAL-02); heal-as-commit = page-object locator rewrite + Postgres heal-audit row (before/after + confidence + outcome) + KG Element-history write-back via the single writer (HEAL-03); per-element heal-success/false-heal tracking exposed for reporting (HEAL-04); the benign-vs-breaking mutation harness measuring >90% benign-heal + ~0 false-heal, keyless via planted specs + the SEED_BUG build (QUAL-02).
**Out of scope (own phases):** failure CLASSIFICATION into product/test-bug/infra + calibrated confidence + Jira filing (Phase 9 — healing's fail-as-defect outcome FEEDS Phase 9 but does not classify/file); the dashboards that VISUALIZE heal-success/false-heal trends (Phase 10 — this phase persists + exposes the per-element stats; the rich dashboard is Phase 10); K8s/Prometheus heal metrics (Phase 11). The quarantine REVIEW UI is minimal here (a queue + apply/reject) — rich review analytics defer to Phase 10. No LLM-assisted healing (explicitly rejected — see D-02).

</domain>

<decisions>
## Implementation Decisions

### Where healing runs (HEAL-01)
- **D-01:** Healing runs INLINE in the Phase-7 worker. When a locator fails mid-run, the engine attempts a deterministic heal + re-validates against the LIVE page (the worker already has the browser/page context) BEFORE the attempt is finally scored: a high-confidence auto-heal lets the test proceed; medium → quarantine; low → fail-as-potential-defect. Fastest path to a green suite, reuses the live page, and HONORS the Phase-7 SC3 "NO LLM in the execution loop" invariant precisely because the engine is deterministic (D-02). The Phase-7 retry loop and the healing attempt are reconciled in research (a locator-failure heal is distinct from the flaky-retry; a heal that re-validates is not a "flake").

### Healing engine — deterministic (HEAL-01)
- **D-02:** The engine is PURELY DETERMINISTIC — NO LLM. Candidate-finding + confidence scoring blend DOM similarity + visual similarity + accessibility-attribute match + historical-locator mapping (from the Element Repository `history_json`), each candidate re-validated to a UNIQUE hit on the live page; the result is a confidence number in [0,1]. Keyless, auditable, reproducible, cannot hallucinate a false heal, and lets the mutation harness (QUAL-02) run WITHOUT provider keys — consistent with the platform's deterministic-gate ethos and the never-weaken-assertions rule. (Research: the exact similarity metrics + the blend weights; visual similarity must be a cheap deterministic measure, e.g. bounding-box/screenshot-region compare, not an LLM vision call.)

### Heal-as-commit (HEAL-03)
- **D-03:** "heal-as-commit" = NOT a literal git commit. A heal (a) rewrites the generated page-object locator by element key (the new chain), (b) writes a Postgres heal-audit row (element key, before chain, after chain, confidence, outcome, run_id, timestamp), and (c) appends to the KG Element history via the kg/writer SINGLE writer (managed execute_write + read-back + parameterized Cypher). The auditable before/after DIFF is rendered from the audit record. No git plumbing inside the ephemeral `workspaces/<run_id>/` tree — consistent with how Phase-7 artifacts/history already persist (filesystem + paths/rows in Postgres, structure in the KG). (Research: the heal-audit table shape + migration 0008 after 0007; how the page-object rewrite is applied safely to the generated file.)

### Confidence banding → 3 outcomes (HEAL-02 / QUAL-02)
- **D-04:** CONSERVATIVE banding with a hard LIVE RE-VALIDATION gate. Auto-heal ONLY when confidence ≥ HIGH AND the chosen candidate re-validates to EXACTLY ONE element on the live page; medium → quarantine for review; low → fail-as-potential-defect. Tuned so breaking changes (the SEED_BUG/seeded-defect set) fall to fail-as-defect — false-heal rate near zero (QUAL-02) at the cost of more quarantines. Thresholds are CONFIG-tunable (env/settings, like the Phase-7 stability_runs); the exact HIGH/MED bands are derived from the mutation harness during research/tuning. Assertions are NEVER weakened — only the locator is healed; an assertion failure is never a heal target.

### Claude's Discretion / for research (--research-phase)
- The four similarity strategies' concrete metrics (DOM tree/attribute distance; deterministic visual similarity; a11y-name/role match; historical-chain match) and the blended-confidence formula + weights; the live re-validation uniqueness check.
- The benign-vs-breaking MUTATION CATALOG (QUAL-02): which benign mutations (rename data-testid/data-test, move element, change visible text, reorder siblings, change tag) SHOULD heal, and which breaking mutations (remove element, break the flow, change semantics — reuse/extend the SEED_BUG build) MUST still fail; how to measure >90% benign-heal + ~0 false-heal deterministically on planted specs without keys.
- The heal-audit data model + migration 0008; per-element heal-success/false-heal aggregation (mirror the Phase-7 execution-history queries) for HEAL-04 reporting.
- The inline worker hook: exactly where in the per-flow job a locator failure is intercepted, how the heal re-validation reuses the live page, and how the outcome maps to the TestResult verdict (auto-healed vs quarantined vs failed) + the Phase-7 retry/flaky reconciliation.
- The minimal quarantine review surface (queue + apply/reject) vs deferring all heal UI to Phase 10 — confirm whether Phase 8 needs its own small UI-SPEC.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — HEAL-01..HEAL-04, QUAL-02.
- `.planning/ROADMAP.md` (Phase 8 section) — the 5 success criteria (4-strategy priority-chain healing + live re-validate; 3 outcomes, never weaken assertions; auditable before/after diff + script-repo update + KG write-back; >90% benign-heal AND ~0 false-heal mutation harness; per-element heal/false-heal tracking).

### Locked stack & carried conventions
- `CLAUDE.md` — Playwright 1.60 (live page re-validation, screenshot regions for deterministic visual compare), the locator priority chain, kg/writer single-writer, SQLAlchemy/Alembic (heal-audit + migration 0008), init_chat_model gateway is NOT used here (deterministic engine). NO LLM in the execution loop (Phase-7 SC3) — healing is inline, so it MUST stay deterministic.

### Reusable seams (read the summaries + code)
- `apps/api/app/services/explorer/locators.py` + `.planning/phases/04-explorer-agent/04-*-SUMMARY.md` — the prioritized locator-chain extraction (data-testid/data-test → aria-label → role+name → text → xpath) + `locator_history`; the PURE build_locator_chain logic (unit-testable on fixture dicts) the healing engine mirrors.
- `apps/api/app/services/kg/reader.py` (`element_repository`/`element_detail` — `chain`/`history` deserialized) + `apps/api/app/services/kg/writer.py` (`upsert_element`, the single writer) + `.planning/phases/05-knowledge-graph-flow-learning/05-*-SUMMARY.md` — the candidate + history source AND the HEAL-03 write-back target.
- `apps/api/app/services/codegen/locators.py` + `apps/api/app/templates/pages/page_object.py.j2` + `.planning/phases/06-bdd-playwright-generation/06-03-SUMMARY.md` — how page-object locators are sourced by element key; what a heal-as-commit REWRITES.
- `apps/api/app/services/stability.py` + `apps/api/tests/functional/test_seeded_bug.py` + `infra/targets/saucedemo/Dockerfile` (SEED_BUG build-arg) + `.planning/phases/06-bdd-playwright-generation/06-04-SUMMARY.md` — the planted-spec + seeded-bug harness to extend into the benign-vs-breaking mutation harness (QUAL-02), keyless.
- `apps/api/app/services/worker/` (consumer/job) + `apps/api/app/services/execution.py` + `.planning/phases/07-execution-engine-workers/07-01-SUMMARY.md` + `07-03-SUMMARY.md` — the inline healing hook point; the retry/flaky classifier to reconcile; TestRun/TestResult/TestArtifact + execution-history queries the heal stats mirror.

### Known issues / project-wide
- `graph_mode down` leaves neo4j running (manual stop) — healing reads the Element Repository (Neo4j); keep the 3GB sequencing (neo4j availability vs the run phase) consistent with Phase-7.
- Provider keys empty → but healing has NO LLM, so the ENTIRE healing engine + the mutation harness are deterministic + keyless-testable. The only Manual-Only slice is a live end-to-end heal during a real LLM-generated-suite run (and any live-page-dependent functional test needs the target up).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `explorer/locators.py` — the priority-chain ordering + history merge (PURE, fixture-testable) the engine reuses for candidate ordering.
- `kg/reader.element_repository`/`element_detail` — candidates + `history_json`; `kg/writer.upsert_element` — the single-writer write-back (HEAL-03).
- `codegen/locators.py` + `page_object.py.j2` — the page-object locator the heal rewrites.
- `stability.py` + `test_seeded_bug.py` + the SEED_BUG Dockerfile — the keyless planted-spec/seeded-bug harness → the benign-vs-breaking mutation harness (QUAL-02).
- `worker/` (consumer/job) + `execution.py` — the inline hook; the TestResult verdict + retry/flaky classifier to reconcile.
- Postgres models + Alembic chain (latest 0007) — new heal-audit table + migration 0008.

### Established Patterns
- Pure logic split from async/IO + unit-tested on fixture dicts (explorer/locators, kg/risk, flaky classifier); deterministic gates over LLM judgment; single-writer + managed execute_write + read-back + parameterized Cypher for any KG write; subprocess (never in-process) runs; auth-gated routers; fresh SessionLocal per background task; artifacts/history on filesystem + Postgres paths/rows, structure in KG; keyless planted-spec proofs (Phase 6/7).
- Carry forward: NO LLM in the execution loop (healing inline ⇒ deterministic); never weaken assertions (heal ONLY locators); config-tunable thresholds (like stability_runs); the seeded-bug build as the breaking-change source.

### Integration Points
- A new healing service/package (deterministic engine: candidate strategies + blend + live re-validate) hooked INTO the worker per-flow job at locator-failure; a heal-audit Postgres model + migration 0008 + heal-stats queries; the page-object rewrite; the KG Element-history write-back via kg/writer; the mutation harness extending stability/seeded-bug; a minimal quarantine review surface (router + small UI or deferred to Phase 10).

</code_context>

<specifics>
## Specific Ideas

- The whole engine is deterministic so a heal can NEVER be a hallucination — the false-heal-near-zero target (QUAL-02) is enforced structurally by the live re-validation uniqueness gate + conservative banding, not by trusting a model.
- Healing touches ONLY locators; assertions are never weakened (a hard invariant, asserted in tests) — a real defect surfaces as fail-as-potential-defect, which feeds Phase 9.
- heal-as-commit is an audit row + file rewrite + KG write-back (not literal git), keeping the ephemeral workspaces model intact and consistent with how Phase-7 already persists evidence.
- The mutation harness is the trust gate (mirrors Phase-6's seeded-bug acceptance): benign mutations must heal (>90%), breaking mutations must still fail (~0 false-heal), proven keylessly on planted specs.

</specifics>

<deferred>
## Deferred Ideas

- Failure CLASSIFICATION (product / test-bug / infra) + calibrated confidence + Jira filing → Phase 9 (healing's fail-as-defect outcome is an INPUT to Phase 9).
- Rich heal-success/false-heal dashboards + trends visualization → Phase 10 (Phase 8 persists + exposes the per-element stats; the dashboard renders them).
- LLM-assisted heal ranking → REJECTED (deterministic engine; would add spend, non-determinism, false-heal hallucination risk, and break the keyless mutation harness + the Phase-7 no-LLM-in-loop invariant).
- Literal git-versioned generated workspaces → REJECTED for v1 (audit row + KG history is the durable record; git plumbing per ephemeral workspace adds cost without need).
- K8s/Prometheus heal metrics → Phase 11.

None of these block Phase 8 — discussion stayed within the self-healing scope.

</deferred>

---

*Phase: 8-self-healing-engine*
*Context gathered: 2026-06-22*
