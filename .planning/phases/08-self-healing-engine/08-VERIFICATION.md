---
phase: 08-self-healing-engine
verified: 2026-06-27T00:05:00Z
status: human_needed
score: 5/5 must-haves verified (deterministic contract)
overrides_applied: 0
re_verification:
  previous_status: none
  note: "Initial verification — no prior VERIFICATION.md"
human_verification:
  - test: "Live heal during a real LLM-generated-suite run (end-to-end with provider keys)"
    expected: "Generate+approve+codegen a suite, benignly mutate the target UI, run a tier → an auto_healed verdict + a heal-audit before/after diff + a KG Element-history write-back; then a breaking change → fail-as-defect (no false heal)"
    why_human: "Needs real provider keys + a full explored graph + generated/approved suite; the deterministic engine + all its seams are proven keylessly, but the LIVE provider-keyed end-to-end path cannot run in the keyless gate (08-VALIDATION Manual-Only)"
  - test: "Memory fit under the 3GB WSL cap during the benign/breaking mutation matrix"
    expected: "docker stats stays under the 3GB Vmmem cap with neo4j OFF in the run phase (on only for the write-back)"
    why_human: "Host Vmmem observation — not programmatically assertable (08-VALIDATION Manual-Only)"
notes:
  - "Phase ROADMAP mode is `mvp` but the goal is a SYSTEM goal, NOT a User Story (gsd-sdk user-story.validate → valid:false). Phase D-05 explicitly ships NO heal UI (deferred to Phase 10), so MVP user-flow framing does not fit. Verified with standard goal-backward methodology against the 5 Success Criteria. Recommend reconciling the `mode: mvp` tag for this engine/infra phase (it has no user-facing slice to walk through)."
---

# Phase 8: Self-Healing Engine Verification Report

**Phase Goal:** UI changes stop breaking the suite — locator failures heal automatically with full auditability, and healing provably never masks real defects
**Verified:** 2026-06-27T00:05:00Z
**Status:** human_needed (all 5 deterministic Success Criteria VERIFIED; 2 Manual-Only items pending — expected, not failures)
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| #   | Truth (SC) | Status | Evidence |
| --- | ---------- | ------ | -------- |
| SC1 | On locator failure, find alternatives via DOM/visual/a11y/historical similarity, priority chain (data-testid→aria-label→role→text→xpath), re-validate against the live page | ✓ VERIFIED | `candidates.py` 4 pure sub-scores (dom_sim Jaccard+tag+xpath, geometry.py IoU+size, a11y_sim role+difflib name, history_sim tier-weighted); `confidence.py` clamped blend; `_healing.py.j2` heal() enumerates LIVE candidates element-specifically + HARD `page.locator(selector).count()` re-validation; priority chain via vendored `build_locator_chain` (xpath/text/role/aria-label/data-testid tier order). Functional proof `test_inspec_heal.py` 2 passed (live mutated page) |
| SC2 | Exactly 3 outcomes — auto-heal (high) / quarantine (medium) / fail-as-defect (low); assertions never weakened | ✓ VERIFIED | `heal_outcome()` returns exactly {auto_heal, quarantine, fail_as_defect}; `live_match_count != 1` uniqueness gate applied FIRST (before bands) — structural false-heal guard; heal() returns healed Locator only on auto_heal else raises HealFailed (test fails naturally); heal() NEVER touches expect()/assertions (only locators). `test_heal_outcome.py` + `test_heal_verdict_override.py` green |
| SC3 | Every heal = auditable before/after diff + confidence; updates the script repo (heal-as-commit); writes back to the KG | ✓ VERIFIED | `HealAudit` model (before/after chain, confidence, outcome, live_match_count, run/flow keys); migration 0008 (down_revision=0007, at head, applied); `ingest.py` ast-validated page-object rewrite (auto_heal only) + `kg/writer.append_element_history` SINGLE writer (parameterized MATCH + read-back guard); `HealAuditResponse` renders before/after diff. `test_heal_ingest.py`/`test_heal_stats.py`/`test_heals_router.py` 13 passed; `test_heal_kg_writeback.py` 2 passed (neo4j up) |
| SC4 | Mutation harness: >90% benign-heal AND ~0 false-heal (seeded bugs still fail) | ✓ VERIFIED | `test_healing_mutations.py` 3 passed against 4 benign + 2 breaking live builds (ports 8082-8087). Asserts `benign_heal_rate >= 0.90 AND false_heal_rate == 0` reading `settings.heal_high_threshold` (production 0.15, NOT a test override). BREAK_DUPLICATE blocked by uniqueness gate (count>1), BREAK_REMOVE by band (0.06<0.15) |
| SC5 | Heal-success + false-heal rate tracked per element and exposed for reporting | ✓ VERIFIED | `stats.per_element_heal_stats` (SQLAlchemy case/func aggregation, no raw SQL): heal_success_rate + false_heal_rate per element_key; auth-gated `GET /api/heals/stats` exposes it. `test_heal_stats.py` + `test_heals_router.py` green |

**Score:** 5/5 Success Criteria verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `app/services/healing/confidence.py` | frozen HealWeights + confidence blend + heal_outcome(uniqueness-first) | ✓ VERIFIED | Stdlib-only (dataclasses); pure clamped blend; uniqueness gate first |
| `app/services/healing/geometry.py` | pure IoU + size_proximity | ✓ VERIFIED | Stdlib-only math, no Playwright/image import |
| `app/services/healing/candidates.py` | dom/a11y/history sub-scores + score_candidate | ✓ VERIFIED | difflib + re + pure build_locator_chain only |
| `app/templates/healing/_healing.py.j2` | in-spec heal accessor, vendored scorer, live re-validation, journal | ✓ VERIFIED | Byte-equivalent vendored scorer (drift guard green); never touches assertions |
| `app/templates/pages/page_object.py.j2` | `_resolve(element_key)` heal accessor | ✓ VERIFIED | Calls `from _healing import heal` on locator miss |
| `app/services/codegen/project.py` | renders _healing.py into project tree | ✓ VERIFIED | `files["_healing.py"] = _render_checked_py("healing/_healing.py.j2"...)` |
| `app/services/worker/classifier.py` | reconcile_verdict (auto_heal overrides flaky) | ✓ VERIFIED | auto_heal→auto_healed precedence; stdlib-only |
| `app/services/worker/job.py` | post-subprocess journal ingest + verdict reconcile | ✓ VERIFIED | Calls ingest_heal_journal + reconcile_verdict inside fresh SessionLocal |
| `app/services/healing/ingest.py` | audit rows + ast-validated rewrite + KG write-back | ✓ VERIFIED | Tolerant bounded parse; rewrite only auto_heal; best-effort KG append |
| `app/services/kg/writer.py append_element_history` | single-writer parameterized + read-back | ✓ VERIFIED | Routes through `_write` (managed execute_write + read-back guard) |
| `app/models/heal_audit.py` | HealAudit model | ✓ VERIFIED | All fields incl. reviewed_outcome (HEAL-04), indexed keys |
| `alembic/versions/0008_heal_audit.py` | migration after 0007 | ✓ VERIFIED | down_revision='0007'; at head; applied (0008) |
| `app/routers/heals.py` | auth-gated list/apply/reject/stats | ✓ VERIFIED | router-level Depends(get_current_user); registered in main.py |
| `app/services/healing/stats.py` | per_element_heal_stats | ✓ VERIFIED | ORM aggregation, no divide-by-zero |
| `app/schemas/heal.py` | HealAuditResponse + HealStatsResponse | ✓ VERIFIED | Before/after diff + confidence + rates |
| `infra/targets/saucedemo/Dockerfile` | benign+breaking mutation build-args | ✓ VERIFIED | 4 BENIGN_ + 2 BREAK_ ARGs extending SEED_BUG |
| `infra/docker-compose.yml` | mutation profile services | ✓ VERIFIED | 6 services on 8082-8087 behind `mutation` profile |

### Key Link Verification

| From | To | Via | Status |
| ---- | -- | --- | ------ |
| confidence.py | settings.heal_high/med_threshold | thresholds passed as kwargs (config-tunable) | ✓ WIRED (defaults 0.15/0.10 confirmed in config.py) |
| page_object.py.j2 `_resolve` | _healing.heal | accessor calls heal() on locator miss | ✓ WIRED |
| classifier.reconcile_verdict | heal-journal events | overrides classify_retry when journal records a heal | ✓ WIRED |
| worker/job.py | ingest_heal_journal + reconcile_verdict | post-subprocess ingest | ✓ WIRED |
| ingest.py | kg/writer.append_element_history | single-writer KG append | ✓ WIRED |
| heals.py | get_current_user | router-level auth gate on every endpoint | ✓ WIRED |
| heals.py | per_element_heal_stats + HealAudit | /stats aggregates; apply/reject mutate | ✓ WIRED |
| test_healing_mutations.py | settings.heal_high_threshold | harness reads SHIPPED config, not local override | ✓ WIRED |

### Behavioral Spot-Checks (run individually per environment guidance)

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Deterministic unit/integration suite | `pytest -m "not live_llm and not e2e and not graph and not functional"` | 345 passed, 0 failed (110s) | ✓ PASS |
| Drift guard + no-LLM gate + outcome + verdict-override | `pytest test_healing_vendor_drift test_no_llm_in_worker test_heal_outcome test_heal_verdict_override` | 35 passed | ✓ PASS |
| In-spec heal (live mutated page) | `pytest test_inspec_heal.py -m functional` | 2 passed (45s) | ✓ PASS |
| QUAL-02 mutation harness (6 live builds) | `pytest test_healing_mutations.py -m functional` | 3 passed (127s) — >90% benign-heal / 0 false-heal | ✓ PASS |
| Heal ingest + stats + router (Postgres) | `pytest test_heal_ingest test_heal_stats test_heals_router` | 13 passed (97s) | ✓ PASS |
| KG Element-history write-back (neo4j) | `pytest test_heal_kg_writeback.py -m graph` | 2 passed (31s) | ✓ PASS |
| Worker round-trip | `pytest test_worker_consume.py -m functional` | 2 passed (27s) | ✓ PASS |
| Determinism | `pytest test_determinism.py -m functional` | 1 passed (31s) | ✓ PASS |
| Artifact capture | `pytest test_artifact_capture.py -m functional` | 2 passed (46s) | ✓ PASS |
| Migration reachability | `alembic current` / `alembic heads` | 0008 (head), single linear head | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
| ----------- | ----------- | ------ | -------- |
| HEAL-01 | 08-01, 08-02 | ✓ SATISFIED | 4-strategy blend + priority chain + live re-validation (SC1) |
| HEAL-02 | 08-01, 08-02 | ✓ SATISFIED | 3 outcomes + uniqueness gate + never-weaken-assertions (SC2) |
| HEAL-03 | 08-03, 08-05 | ✓ SATISFIED | audit row + page-object rewrite + KG write-back + before/after diff (SC3) |
| HEAL-04 | 08-05 | ✓ SATISFIED | per-element success/false-heal stats exposed via API (SC5) |
| QUAL-02 | 08-04 | ✓ SATISFIED | >90% benign-heal / 0 false-heal mutation harness, production thresholds (SC4) |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
| ---- | ------- | -------- | ------ |
| (none) | TBD/FIXME/XXX in healing services or phase-8 modified files | — | No debt markers found |
| (none) | stub/placeholder/not-implemented in healing engine | — | No stubs; the only `placeholder` literals are legitimate DOM attribute names being scored |

**No blocker or warning anti-patterns.** Zero new packages (only pyproject.toml change is registering the `integration` pytest marker — confirmed by `git diff`).

### Deterministic-vs-Manual Boundary

The ENTIRE healing engine is deterministic (NO LLM — D-02 verified: `confidence`/`geometry`/`candidates` import only dataclasses/difflib/re + the pure browser-free `build_locator_chain`; no init_chat_model/langchain/gateway anywhere in the worker plane). The whole deterministic contract — 4 sub-scores, blend, uniqueness gate, banding, in-spec heal, journal handoff, verdict override, heal-as-commit (audit + rewrite + KG write-back), per-element stats, quarantine API, AND the QUAL-02 mutation trust gate — is proven KEYLESSLY and PASSES. The two Manual-Only items below are the only pending verifications and are EXPECTED per 08-VALIDATION (they require provider keys / host memory observation), NOT failures.

### Human Verification Required

1. **Live heal during a real LLM-generated-suite run** — generate+approve+codegen a suite with provider keys, benignly mutate the target UI, run a tier → confirm an auto_healed verdict + heal-audit before/after diff + KG write-back; then a breaking change → fail-as-defect. *Why human: needs real provider keys + a full explored graph; the deterministic engine and every seam it uses are already proven keylessly.*
2. **Memory fit under 3GB during the mutation matrix** — `docker stats` observation during the benign/breaking matrix. *Why human: host Vmmem observation, not programmatically assertable.*

### Gaps Summary

No gaps. All 5 ROADMAP Success Criteria are observably true in the codebase and proven by passing deterministic + functional + integration + graph tests run in this verification session (deterministic 345/345; in-spec heal 2/2; QUAL-02 3/3; ingest/stats/router 13/13; KG write-back 2/2; worker/determinism/artifact 5/5). The structural false-heal guarantee (uniqueness gate first + conservative bands tuned into the empirical separation window) is verified in code and exercised live by the QUAL-02 harness. heal() provably never touches assertions. Zero new packages. No heal UI (D-05 — deferred to Phase 10, confirmed). The deterministic phase contract is ACHIEVED; status is `human_needed` solely because two Manual-Only verifications (live keyed end-to-end + memory observation) remain, as the validation strategy anticipated.

---

_Verified: 2026-06-27T00:05:00Z_
_Verifier: Claude (gsd-verifier)_
