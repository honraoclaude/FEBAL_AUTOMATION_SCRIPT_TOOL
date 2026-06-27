---
phase: 09-defect-intelligence-jira-agent
plan: 01
subsystem: testing
tags: [classifier, fingerprint, defect-intelligence, alembic, sqlalchemy, deterministic, no-llm]

# Dependency graph
requires:
  - phase: 07-execution-engine
    provides: TestResult/TestArtifact ledger + worker retry loop + reconcile_verdict product_failure feed
  - phase: 08-self-healing
    provides: HealAudit ledger (before/after chains + outcome = the healing-history evidence)
provides:
  - "Migration 0009: classifications + defects tables + test_results.error_text column"
  - "Persisted last-attempt error_text on every TestResult (closes the Phase-7 persistence gap)"
  - "Classification + Defect ORM models (the Plan-04 pipeline + traceability link)"
  - "Pure deterministic 3-way classifier {infrastructure, automation, product_defect} + clamped 0-100 confidence + cited signals (DEF-01)"
  - "Stable failure fingerprint (sha1[:16] over class + normalized error + flow + step)"
  - "Pure infra-health error-pattern signal"
  - "Evidence gather (read joins over test_results/heal_audit/test_artifacts) + classify_failure helper (DEF-02)"
  - "Jira/defect settings block in config (autonomy OFF by default)"
  - "NO-LLM grep gate over the defects package (D-01)"
affects: [09-02-calibration-harness, 09-03-jira-client, 09-04-defect-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure deterministic decision module cloned from kg/risk.py: @dataclass(frozen=True) starting-point weights + clamped max(0,min(100,raw))"
    - "NO-LLM import grep gate (test_no_llm_in_classifier) cloned from test_no_llm_in_worker, retargeted at app/services/defects/"
    - "gather_evidence reads via the ORM on a PASSED-IN session (caller owns SessionLocal — the worker/job discipline)"

key-files:
  created:
    - apps/api/alembic/versions/0009_defects.py
    - apps/api/app/models/defects.py
    - apps/api/app/services/defects/__init__.py
    - apps/api/app/services/defects/classifier.py
    - apps/api/app/services/defects/fingerprint.py
    - apps/api/app/services/defects/infra_health.py
    - apps/api/app/services/defects/evidence.py
    - apps/api/tests/unit/test_classifier.py
    - apps/api/tests/unit/test_fingerprint.py
    - apps/api/tests/unit/test_no_llm_in_classifier.py
    - apps/api/tests/unit/test_classifier_evidence.py
    - apps/api/tests/functional/test_migration_0009.py
  modified:
    - apps/api/app/models/execution_history.py
    - apps/api/app/services/worker/job.py
    - apps/api/app/core/config.py

key-decisions:
  - "Class/confidence DECISION is deterministic + keyless (D-01); the LLM enriches Jira prose only, never the decision"
  - "infra_health is a PURE error-pattern signal (RESEARCH Open-Q2 option b), no live Docker probe (deferred to Phase 11)"
  - "Classifier weights are FROZEN STARTING POINTS (60/20/-15); the QUAL-03 harness calibrates them in Plan 02"
  - "evidence.py uses a passed-in AsyncSession (never opens its own); the pipeline/caller owns the SessionLocal"

patterns-established:
  - "Pure frozen-weights clamped decision module (kg/risk clone) for any auditable, keyless score"
  - "Per-package NO-LLM grep gate to keep a decision plane off the LLM"

requirements-completed: [DEF-01, DEF-02]

# Metrics
duration: ~25min (continuation; Tasks 1-2 in prior stream)
completed: 2026-06-27
---

# Phase 9 Plan 01: Defect Evidence + Pure Classifier Foundation Summary

**Deterministic keyless 3-way failure classifier ({infrastructure, automation, product_defect}) + clamped 0-100 confidence + stable fingerprint, fed by an ORM evidence-join over test_results.error_text / heal_audit / test_artifacts, with migration 0009 persisting the error text the classifier reads — no LLM ever on the decision path.**

## Performance

- **Duration:** ~25 min (continuation stream; Tasks 1-2 committed in the prior stream that timed out)
- **Completed:** 2026-06-27
- **Tasks:** 3 of 3
- **Files modified:** 15 (12 created, 3 modified)

## Accomplishments
- Migration 0009 creates `classifications` + `defects` tables and adds `test_results.error_text` (Text, nullable); round-trips up/down/up clean
- `job.py` now persists the last attempt's output as `error_text` on the TestResult with NO new imports (no-llm-in-worker gate green) — closes the Phase-7 persistence gap
- Pure `classify(evidence)` maps the RESEARCH Pattern-1 taxonomy to a class + a clamped 0-100 confidence + cited signals (DEF-01)
- `fingerprint(cls, msg, flow_id, step)` = sha1[:16] over the normalized error (uuids/timestamps/hex/digits stripped) — stable under instance-data noise
- `gather_evidence(db, run_id, flow_id)` ORM-joins error_text + HealAudit (DOM diff + healing history) + TestArtifact paths, derives infra_health, returns the classify() input + the cited snapshot for classifications.evidence (DEF-02)
- `classify_failure(db, run_id, flow_id)` gathers -> pure classify -> fingerprint -> {classification, confidence, cited, evidence, fingerprint}
- NO-LLM grep gate over the whole defects package stays green with evidence.py present

## Task Commits

1. **Task 1: Migration 0009 + error_text persistence + Jira/defect settings** - `1c24c2b` (feat) — prior stream
2. **Task 2: Pure classifier + fingerprint + infra-health signal + NO-LLM gate** - `05e377b` (feat) — prior stream
3. **Task 3: Evidence gather (read joins) + classifier-over-evidence wiring** - `15932ff` (feat) — this stream

**Plan metadata:** see final docs commit.

_Note: this plan was executed across two streams; the first stream stream-timed-out after committing Tasks 1-2 but before creating this SUMMARY / updating STATE. This continuation completed, verified, and committed Task 3, then wrote this summary._

## Files Created/Modified
- `apps/api/alembic/versions/0009_defects.py` - classifications + defects tables + test_results.error_text; reversible downgrade
- `apps/api/app/models/defects.py` - Classification + Defect ORM models (the Plan-04 pipeline + JIRA-04 traceability link)
- `apps/api/app/models/execution_history.py` - TestResult gains `error_text: Mapped[str | None]`
- `apps/api/app/services/worker/job.py` - persists `error_text=result["output"]`, no new imports
- `apps/api/app/core/config.py` - Jira/defect settings (autonomy OFF; jira_confidence_threshold tuned by QUAL-03)
- `apps/api/app/services/defects/classifier.py` - pure 3-way classify + frozen-weight clamped confidence
- `apps/api/app/services/defects/fingerprint.py` - normalize() + sha1[:16] fingerprint
- `apps/api/app/services/defects/infra_health.py` - pure error-pattern down/up/unknown signal
- `apps/api/app/services/defects/evidence.py` - gather_evidence + classify_failure (ORM joins, passed-in session)
- `apps/api/tests/unit/test_classifier.py`, `test_fingerprint.py`, `test_no_llm_in_classifier.py`, `test_classifier_evidence.py` - unit/integration coverage
- `apps/api/tests/functional/test_migration_0009.py` - up/down/up round-trip + error_text presence

## Decisions Made
None new in this stream — followed the plan as specified. (Plan-level decisions captured in frontmatter key-decisions: keyless deterministic decision, pure infra_health, frozen starting-point weights, passed-in session.)

## Deviations from Plan

None - plan executed exactly as written. Task 3's `evidence.py` and `test_classifier_evidence.py` (authored in the prior stream but left uncommitted/unverified) were reviewed against the committed Task-1/Task-2 interfaces (TestResult.error_text, TestArtifact.kind/path, HealAudit.element_key/outcome/chains, classifier.classify keys, fingerprint signature) — all matched; no fix was required.

## Issues Encountered
- The prior stream stream-timed-out mid-plan: Tasks 1-2 were committed (`1c24c2b`, `05e377b`) but Task 3 files were left untracked + unverified and no SUMMARY/STATE update was made. Resolved by reviewing the untracked Task-3 work, running its test against the live Postgres (migration 0009 already at head), running the full deterministic suite + both NO-LLM gates, then committing Task 3 atomically and completing the metadata.

## Verification
- `uv run python -m pytest tests/unit/test_classifier_evidence.py -q` → 2 passed (seeded product-failure -> product_defect; un-healed-locator -> automation)
- `uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional" -q` → 365 passed, 140 deselected
- `uv run python -m pytest tests/unit/test_no_llm_in_worker.py tests/unit/test_no_llm_in_classifier.py -q` → 2 passed (both gates green)
- `uv run alembic current` → 0009 (head)

## User Setup Required
None - no external service configuration required. (Jira settings exist but autonomy is OFF by default; the gated atlassian-python-api install is isolated to Plan 03.)

## Next Phase Readiness
- DEF-01/DEF-02 foundation complete: a fixture/seeded evidence dict deterministically yields a cited class + confidence + fingerprint, and a real product-failure run now stores its error text.
- Ready for Plan 02 (QUAL-03 calibration harness — tunes the frozen ClassifierWeights), Plan 03 (Jira client, gated install), Plan 04 (defect pipeline consuming classify_failure post-retry).

## Self-Check: PASSED

All 3 created artifacts (evidence.py, test_classifier_evidence.py, 09-01-SUMMARY.md) exist on disk; all 3 task commits (1c24c2b, 05e377b, 15932ff) exist in git history.

---
*Phase: 09-defect-intelligence-jira-agent*
*Completed: 2026-06-27*
