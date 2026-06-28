---
phase: 09-defect-intelligence-jira-agent
verified: 2026-06-28T03:30:00Z
status: human_needed
score: 5/5 must-haves verified (deterministic contract); 3 Manual-Only items pending live Jira/LLM
re_verification:
  previous_status: none
  note: "Initial verification. A prior run was interrupted before writing VERIFICATION.md."
human_verification:
  - test: "Live classify -> draft -> human-flip -> autonomous file -> dedup against a real Jira Cloud"
    expected: "Above-threshold product defects file with full evidence/attachments + test/flow/execution links; a re-run UPDATES the same issue (JQL dedup); the per-run cap holds; flag is human-flipped, not auto-enabled"
    why_human: "No real Jira Cloud instance + token in dev; empty JIRA_* keys. The full create/attach/JQL/comment/link contract is proven keyless via FakeJira, but live filing cannot run in CI."
  - test: "Live LLM Jira description enrichment"
    expected: "With provider keys set, the Jira description prose is LLM-enriched (enriched=true); without keys the deterministic fallback prose is used and the UI shows the honest 'written without an LLM' caption"
    why_human: "Empty provider keys in dev; describe() short-circuits to the deterministic fallback keyless (asserted), so the enriched path is unobservable without keys."
  - test: ">90% draft-precision measurement before flipping jira_autonomous_enabled"
    expected: "A human reviews the draft queue, measures draft precision >=90% (and accuracy >=85%, already proven), then deliberately flips JIRA_AUTONOMOUS_ENABLED=true in config"
    why_human: "Draft precision is a human-review measurement over real drafts; the phase persists no runtime precision store (honest null). The autonomy flag is OFF by default and human-gated by design (D-04)."
---

# Phase 9: Defect Intelligence & Jira Agent — Verification Report

**Phase Goal:** Failures triage themselves — classified with calibrated confidence and evidence, and high-confidence product defects become deduplicated, fully-evidenced Jira issues.
**Verified:** 2026-06-28
**Status:** human_needed (deterministic contract PASSES 5/5; 3 Manual-Only items require a live Jira instance + provider keys + a human draft-precision review)
**Re-verification:** No — initial verification (a prior run was interrupted before writing this file).

## MVP-mode note

The phase carries `mode: mvp` in ROADMAP.md, but the goal is NOT in user-story format
(`gsd-sdk user-story.validate` returned `valid=false`). Per `references/verify-mvp-mode.md`,
the verifier surfaces this discrepancy: to get a User-Flow-Coverage report, run
`/gsd mvp-phase 9` to reformat the goal as "As a [role], I want to [capability], so that
[outcome]." This verification proceeds with standard goal-backward verification against the
5 ROADMAP Success Criteria (the roadmap contract), which is sound regardless of mode framing.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth (SC) | Status | Evidence |
|---|-----------|--------|----------|
| 1 | SC1 (DEF-01/02): every failure retried then labeled Infra/Automation/Product with 0-100 confidence citing evidence (error type, DOM diff, healing history, infra health) | ✓ VERIFIED | `classifier.py` is pure stdlib (re/dataclasses) + sibling `infra_health` — NO LLM/DB/browser imports; precedence rules infra→automation→product with a clamped 0-100 confidence + `cited[]`. `evidence.py:gather_evidence` ORM-joins `TestResult.error_text` + `HealAudit` (before/after chains + outcome = DOM diff/healing history) + `TestArtifact` + derived `infra_health`. `pipeline.run_defect_pipeline` is called for `verdict=='product_failure'` only (post-retry). Unit tests green (test_classifier, test_classifier_evidence, test_no_llm_in_classifier). |
| 2 | SC2 (DEF-03/QUAL-03): accuracy >85% vs hand-labeled set, calibrating the Jira threshold before autonomous filing | ✓ VERIFIED (live) | `test_classifier_accuracy.py` ran LIVE (SEED_BUG@8081 + BREAK_REMOVE@8086 up): **accuracy 10/10 = 1.00 (>=0.85)**, separation window (0, 80], shipped `settings.jira_confidence_threshold=70` asserted in-window via `_THRESHOLD = _settings.jira_confidence_threshold` (line 74/409) — never a literal. |
| 3 | SC3 (JIRA-01/02): Jira issues with full evidence/attachments, starting in a draft/review queue; autonomous only above threshold + after >90% draft precision | ✓ VERIFIED (contract) / ⚠ live MANUAL | `client.py` JiraGateway Protocol + AtlassianJira (anyio.to_thread, `cloud=True, api_version=3`, token never logged) + `fake.py` FakeJira; `adf.py build_adf`→ADF v3 doc DICT; `description.py describe`→(prose, enriched) with keyless deterministic fallback. `autonomy.may_autofile = jira_autonomous_enabled AND conf>=threshold` (OFF by default). `run_defect_pipeline` ALWAYS persists a draft Defect row first. Draft queue UI + read-only calibration panel shipped. **Live filing + >90% draft precision are Manual-Only (no real Jira/keys).** |
| 4 | SC4 (JIRA-03): duplicates update the existing issue (fingerprint + JQL), capped per run | ✓ VERIFIED (contract) | `fingerprint.py` = sha1[:16] over class+normalize(msg)+flow+step (uuids/ts/hex/digits stripped → stable). `pipeline._dedup_jql` = server-built `labels="fp-<hash>" AND statusCategory != Done` (no user text). HIT→add_comment+re-attach (UPDATE, no cap consumption); MISS→create+attach+link (consumes 1 cap slot); MISS at cap→action='none', draft persists. Proven keyless over FakeJira (test_jira_dedup, 10 passed). |
| 5 | SC5 (JIRA-04): every issue links test↔flow↔execution in the traceability chain | ✓ VERIFIED | Defect row carries `run_id` + `flow_id` + `jira_key` + `jira_label` (migration 0009); `run_defect_pipeline` commits the link before any filing; best-effort `create_issue_link`; UI detail surfaces run_id/flow_id/Jira key (every list row + detail). |

**Score:** 5/5 ROADMAP success criteria verified for the deterministic, keyless contract.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apps/api/app/services/defects/classifier.py` | Pure deterministic 3-way + 0-100 conf, no LLM | ✓ VERIFIED | stdlib-only; frozen weights; clamped |
| `apps/api/app/services/defects/evidence.py` | ORM evidence join + classify_failure | ✓ VERIFIED | error_text + HealAudit + TestArtifact + infra_health; passed-in session |
| `apps/api/app/services/defects/fingerprint.py` | Stable normalized hash | ✓ VERIFIED | sha1[:16], instance-data stripped |
| `apps/api/app/services/defects/infra_health.py` | Pure error-pattern signal | ✓ VERIFIED | up/down/unknown |
| `apps/api/app/services/defects/autonomy.py` | flag AND threshold gate | ✓ VERIFIED | reads shipped settings, never literal |
| `apps/api/app/services/defects/pipeline.py` | dedup+cap+draft+traceability+gated autofile | ✓ VERIFIED | substantive, wired into router |
| `apps/api/app/services/jira/{client,fake,adf,description}.py` | Gateway+Fake+ADF+prose | ✓ VERIFIED | anyio offload; token never logged; ADF dict |
| `apps/api/app/models/defects.py` + `0009_defects.py` | Classification+Defect+error_text | ✓ VERIFIED | migration up/down/up round-trips, head=0009 |
| `apps/api/app/routers/defects.py` | Auth-gated list/detail/calibration/apply/reject | ✓ VERIFIED | router-level get_current_user; registered in main.py |
| `apps/api/tests/functional/test_classifier_accuracy.py` | QUAL-03 harness | ✓ VERIFIED | live 10/10=1.00 |
| `apps/web/.../defects/` + `components/defects/` + `lib/api/defects.ts` | Review UI | ✓ VERIFIED | tsc clean; 14/14 e2e pass; read-only calibration; one sidebar item |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| pipeline | classifier | `classify_failure` → pure `classify()` | ✓ WIRED | deterministic decision, post-retry |
| pipeline | Jira | `gateway.search_jql/create_issue/add_comment/add_attachment` | ✓ WIRED | dedup+cap+attach over Protocol |
| router | pipeline | `file_or_update` + `_severity_priority` (apply path == autonomous path) | ✓ WIRED | byte-identical filing |
| router | main.py | `app.include_router(defects_router)` | ✓ WIRED | line 128 |
| worker job.py | TestResult.error_text | `error_text=last_output` | ✓ WIRED | no new imports (no-llm-in-worker green) |
| UI | /api/defects | zod client `lib/api/defects.ts` | ✓ WIRED | mirrors schemas/defect.py; 14 e2e |
| describe() | llm_gateway | prose only, keyless fallback | ✓ WIRED (prose-only) | D-01: LLM never touches class/confidence |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full deterministic backend suite | `pytest -m "not live_llm and not e2e and not graph and not functional" -q` | 408 passed, 142 deselected | ✓ PASS |
| Jira/autonomy/dedup/no-llm units | `pytest test_jira_create test_adf test_jira_description test_autonomy_gate test_jira_dedup test_no_llm_in_classifier` | 31 passed | ✓ PASS |
| Pipeline + router integration | `pytest test_defect_pipeline test_defects_router` | 13 passed | ✓ PASS |
| No-LLM gates + classifier/fingerprint/evidence units | `pytest test_no_llm_in_worker test_classifier test_fingerprint test_classifier_evidence` | 22 passed | ✓ PASS |
| QUAL-03 accuracy harness (live) | `pytest test_classifier_accuracy -m functional -s` | 2 passed; accuracy 10/10=1.00; threshold 70 in (0,80] | ✓ PASS |
| Frontend typecheck | `npx tsc --noEmit` | exit 0 | ✓ PASS |
| Defects e2e (mocked API) | `npx playwright test defects.spec.ts --workers=1` | 14 passed | ✓ PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes declared for this phase; verification used the pytest/playwright suites above (the phase's declared validation commands).

### Migration Round-Trip

| Step | Result |
|------|--------|
| `alembic upgrade head` | 0008 → 0009 |
| `alembic downgrade -1` | 0009 → 0008 (reverses error_text + both tables + indexes) |
| `alembic upgrade head` | 0008 → 0009 |
| `alembic current` | **0009 (head)** ✓ down_revision='0008' |

### Package Gate

| Check | Result | Status |
|-------|--------|--------|
| Exactly ONE new backend dep | `atlassian-python-api==4.0.*` added in commit `1260e5c` | ✓ |
| anyio NOT added | not present in pyproject (transitive via FastAPI) | ✓ |
| Zero new frontend deps | `git diff HEAD package.json package-lock.json` clean; recharts present but not newly used | ✓ |
| Zero new shadcn | UI is plain compositions over vendored badge/button | ✓ |

### Requirements Coverage

| Requirement | Source Plan | Status | Evidence |
|-------------|-------------|--------|----------|
| DEF-01 | 09-01 | ✓ SATISFIED | pure 3-way classifier + 0-100 confidence |
| DEF-02 | 09-01 | ✓ SATISFIED | retry-before-classify; evidence joins cite error/DOM-diff/heal-history/infra-health |
| DEF-03 | 09-02 | ✓ SATISFIED | QUAL-03 harness live 100% (>85%) calibrates threshold |
| JIRA-01 | 09-03 | ✓ SATISFIED (contract) / live MANUAL | gateway+ADF+attachments contract via FakeJira |
| JIRA-02 | 09-04/05 | ✓ SATISFIED (contract) / live MANUAL | draft queue + autonomy gate OFF by default + read-only calibration panel |
| JIRA-03 | 09-04 | ✓ SATISFIED (contract) | fingerprint + JQL dedup + per-run cap |
| JIRA-04 | 09-04/05 | ✓ SATISFIED | run_id/flow_id/jira_key links persisted + surfaced |
| QUAL-03 | 09-02 | ✓ SATISFIED | labeled set (SEED_BUG/un-healed mutation/dead-port) measured keylessly |

No orphaned requirements (all 8 phase requirements claimed by plans and verified).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No TBD/FIXME/XXX/stub markers in phase source | ℹ️ Info | "placeholder" matches are fingerprint normalization tokens + ADF prose, not stubs |

### Human Verification Required

1. **Live classify → draft → human-flip → autonomous file → dedup (real Jira Cloud).**
   - Configure JIRA_URL/EMAIL/API_TOKEN/PROJECT_KEY; run a tier with real failures; review the draft queue + calibration panel; flip `JIRA_AUTONOMOUS_ENABLED=true`; confirm above-threshold defects file with full evidence/attachments + test/flow/execution links; re-run → the duplicate UPDATES the same issue (JQL); the per-run cap holds.
   - Why human: no real Jira instance/token in dev; the full contract is proven keyless via FakeJira.

2. **Live LLM Jira description enrichment.**
   - With provider keys set, confirm the description prose is LLM-enriched (enriched=true); without keys the deterministic fallback writes the prose and the UI shows the honest "written without an LLM" caption.
   - Why human: empty provider keys; describe() short-circuits to the keyless fallback.

3. **>90% draft-precision measurement before flipping the autonomy flag.**
   - Review real drafts, measure draft precision ≥90% (accuracy ≥85% already proven), then deliberately flip the config flag.
   - Why human: precision is a human-review measurement; the phase persists no runtime precision store (honest null), and the flag is OFF-by-default by design (D-04).

### Gaps Summary

No deterministic gaps. The keyless contract for all 5 success criteria is fully implemented and
verified in code (not just claimed): the classifier is provably deterministic (NO-LLM grep gate +
stdlib-only imports), the QUAL-03 accuracy harness ran LIVE at 100% and calibrates the threshold
against the shipped settings value, the Jira create/attach/JQL-dedup/cap/link/traceability contract
passes keyless over FakeJira, the autonomy gate is OFF by default and proven to read the calibrated
setting (not a literal), migration 0009 round-trips reversibly, the package gate holds (one backend
dep, no anyio, zero frontend deps), and the review UI passes tsc + a 14-test mocked-API e2e with a
read-only calibration panel + one sidebar item.

The three pending items are inherently Manual-Only (live Jira Cloud filing/dedup, live LLM prose
enrichment, the human draft-precision review that unlocks autonomy) — they are EXPECTED gaps by the
phase's own design (human-in-the-loop autonomy gate, no real Jira/keys in dev), not implementation
failures. Per the decision tree, the presence of non-empty human-verification items makes the
overall status `human_needed` rather than `passed`.

---

_Verified: 2026-06-28_
_Verifier: Claude (gsd-verifier)_
