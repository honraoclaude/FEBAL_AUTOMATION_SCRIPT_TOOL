---
phase: 8
slug: self-healing-engine
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-22
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (pytest-asyncio 1.4, asyncio_mode=auto) + pytest-playwright + pytest-bdd |
| **Config file** | apps/api/pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd apps/api && uv run pytest -m "not live_llm and not graph and not e2e" -q` (the pure deterministic scorer: DOM/visual-IoU/a11y/historical sub-scores + blended confidence + banding; the live-match-uniqueness gate logic; the page-object rewrite (ast-validated); the heal-journal model; the never-weaken-assertions guard; the flaky↔auto_healed reconciliation — all on fixture dicts/rendered fixtures, NO keys, NO neo4j, NO browser) |
| **Full suite command** | `cd apps/api && uv run pytest -m "not live_llm" -q` (adds graph-marked + functional: the in-spec heal accessor against a LIVE mutated page, the worker journal ingest → heal-audit row + KG Element-history write-back, the benign-vs-breaking mutation harness keyless) |
| **Frontend command** | n/a this phase (heal UI deferred to Phase 10, D-05 — only a minimal auth-gated quarantine API) |
| **Estimated runtime** | ~4-6 min (live-page mutation runs + the benign/breaking mutation matrix add real wall time) |

---

## Sampling Rate

- **After every task commit:** `cd apps/api && uv run pytest -m "not live_llm and not graph and not e2e" -q`
- **After every plan wave:** full suite with the target up + neo4j as needed for the write-back (`graph_mode`); neo4j OFF during the pure run phase (3GB cap) — same sequencing as Phase 7
- **Before `/gsd:verify-work`:** full deterministic suite green; the mutation harness green (>90% benign-heal, ~0 false-heal on the breaking set, on planted specs — keyless); the never-weaken-assertions + uniqueness-gate guards green; a live heal during a real LLM-generated-suite run demonstrated with provider keys
- **Max feedback latency:** ~6 min

---

## Per-Task Verification Map

> Populated by the planner. Each task maps to HEAL-01..04 / QUAL-02, a test type (unit deterministic
> on fixtures / graph+functional against a live mutated page / live_llm-manual), a threat ref, and a
> keyless command. The deterministic scorer + banding, the uniqueness gate, the page-object rewrite,
> the heal-journal + audit model, the per-element stats, the quarantine API, and the benign-vs-breaking
> mutation harness are ALL deterministic WITHOUT keys; a live heal during a real LLM-generated suite is
> Manual-Only.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-T1 | 08-01 | 1 | HEAL-01, HEAL-02 | uniqueness gate + never-weaken-assertions | pure confidence blend + banding; uniqueness gate first; assertion never a heal target | unit (fixtures) | `cd apps/api && uv run pytest tests/unit/test_heal_confidence.py tests/unit/test_heal_outcome.py -q` | ❌ W0 | ⬜ pending |
| 08-01-T2 | 08-01 | 1 | HEAL-01 | deterministic scoring (no LLM) | DOM/visual-IoU/a11y/historical sub-scores, keyless | unit (fixtures) | `cd apps/api && uv run pytest tests/unit/test_geometry.py tests/unit/test_heal_candidates.py -q` | ❌ W0 | ⬜ pending |
| 08-02-T1 | 08-02 | 2 | HEAL-01 | vendored scorer integrity | _healing.py.j2 renders, ast-parses, vendors heal()/scorer | unit (render+ast) | `cd apps/api && uv run python -c "...render+ast.parse _healing.py.j2..."` | ❌ W0 | ⬜ pending |
| 08-02-T2 | 08-02 | 2 | HEAL-02 | verdict override + vendor drift + SC3 no-LLM | auto_healed overrides flaky; in-spec copy byte-equiv to source; no LLM | unit | `cd apps/api && uv run pytest tests/unit/test_heal_verdict_override.py tests/unit/test_healing_vendor_drift.py tests/unit/test_no_llm_in_worker.py -q` | ❌ W0 | ⬜ pending |
| 08-02-T3 | 08-02 | 2 | HEAL-01, HEAL-02 | live re-validation gate | in-spec heal against a live mutated page (target up, neo4j off) | functional | `cd apps/api && uv run pytest tests/functional/test_inspec_heal.py -m functional -q` | ❌ W0 | ⬜ pending |
| 08-03-T1 | 08-03 | 3 | HEAL-03 | ast-validated rewrite + migration | page-object rewrite by attr (ast-validated) + heal_audit migration 0008 | unit + migration | `cd apps/api && uv run pytest tests/unit/test_page_object_rewrite.py -q && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` | ❌ W0 | ⬜ pending |
| 08-03-T2 | 08-03 | 3 | HEAL-03 | journal validate-on-ingest + SC3 | worker ingests journal → heal_audit rows + rewrite for auto_heal only; no LLM | integration | `cd apps/api && uv run pytest tests/integration/test_heal_ingest.py tests/unit/test_no_llm_in_worker.py -q` | ❌ W0 | ⬜ pending |
| 08-03-T3 | 08-03 | 3 | HEAL-03 | single-writer Cypher write-back | KG Element-history append (parameterized, read-back guard) | integration + graph | `cd apps/api && uv run pytest tests/integration/test_heal_ingest.py -q && uv run pytest tests/integration/test_heal_kg_writeback.py -m graph -q` | ❌ W0 | ⬜ pending |
| 08-04-T1 | 08-04 | 3 | QUAL-02 | mutation build (benign/breaking) | SEED_BUG-style build-arg mutation profile + compose | infra | `cd infra && docker compose --profile mutation config >/dev/null && grep -cE 'ARG (BENIGN_\|BREAK_)' targets/saucedemo/Dockerfile` | ❌ W0 | ⬜ pending |
| 08-04-T2 | 08-04 | 3 | QUAL-02 | >90% benign-heal AND ~0 false-heal | benign mutations heal, breaking still fail (keyless, planted spec) | functional | `cd apps/api && uv run pytest tests/functional/test_healing_mutations.py -m functional -q` | ❌ W0 | ⬜ pending |
| 08-05-T1 | 08-05 | 4 | HEAL-04 | per-element stats aggregation | heal-success/false-heal per element (mirror exec-history queries) | integration | `cd apps/api && uv run pytest tests/integration/test_heal_stats.py -q` | ❌ W0 | ⬜ pending |
| 08-05-T2 | 08-05 | 4 | HEAL-03, HEAL-04 | auth-gated quarantine API | list/apply/reject returns before/after diff + confidence; get_current_user | integration | `cd apps/api && uv run pytest tests/integration/test_heals_router.py -q` | ❌ W0 | ⬜ pending |
| Manual | — | — | HEAL-01..03 | — | live heal during a real LLM-generated-suite run | live_llm/manual | (documented manual steps; needs provider key) | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Every non-manual task has an `<automated>` command (no install gates this phase — zero new packages). No 3 consecutive tasks lack an automated verify. The live LLM-generated-suite heal is the only Manual-Only item.

---

## Wave 0 Requirements

- [ ] A planted template-rendered spec with the in-spec heal accessor wired (reuse the Phase-3/6/7 test_login.py.j2 path + the new `_healing.py.j2`) for the deterministic in-spec/journal proofs — no keys
- [ ] A benign-vs-breaking MUTATION build/catalog extending the SEED_BUG Dockerfile build-arg + test_seeded_bug.py (benign: rename data-testid/data-test, change text, move/reorder, change tag; breaking: remove element, break flow, change semantics) — the QUAL-02 harness, keyless
- [ ] heal-audit fixtures + migration 0008 (chains after 0007); the additive TestResult verdicts (auto_healed, quarantined)
- [ ] Fixture KG (reuse Phase-5 fixtures) with element chain_json/history_json for the historical-mapping sub-score + the write-back target — fake-driver unit-testable, no neo4j
- [ ] Mocked/fixture live-page DOM snippets for the DOM/visual-IoU/a11y sub-scores (no real browser at unit level)
- [ ] Existing functional infra (live-HTTP client, authed_client, the subprocess runner, kg/writer single writer, reset_target.py, graph_mode) carries forward

*Existing infrastructure (asyncio_mode=auto, the kg/risk pure-logic + fixture-unit-test pattern, the explorer/locators chain builder, the stability planted-spec + SEED_BUG harness, the worker output-dir walk) covers most of the phase; the in-spec heal accessor + journal + the mutation catalog are the new Wave-0 pieces.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live heal during a real LLM-generated-suite run | HEAL-01..03 | Needs provider keys (a real generated/approved suite + explored graph) | Set keys, generate+approve+codegen a suite, mutate the target UI benignly, run a tier, confirm an auto_healed verdict + a heal-audit before/after diff + the KG Element-history write-back; then a breaking change → fail-as-defect (no false heal) |
| Memory fit during the mutation matrix under 3GB | (infra) | host Vmmem observation | `docker stats` during the benign/breaking matrix with neo4j OFF in the run phase, on for the write-back |

*Deterministic logic (the four similarity sub-scores, blended confidence + banding, the uniqueness gate, the page-object rewrite, the heal-journal + audit + KG write-back, per-element stats, the quarantine API, and the benign-vs-breaking mutation harness on planted specs) is automated WITHOUT keys.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (planted heal spec, mutation catalog, heal-audit migration, fixture KG/DOM)
- [ ] No watch-mode flags
- [ ] Feedback latency < 6 min
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
