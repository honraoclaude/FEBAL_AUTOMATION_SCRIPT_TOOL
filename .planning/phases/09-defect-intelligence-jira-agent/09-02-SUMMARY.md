---
phase: 09-defect-intelligence-jira-agent
plan: 02
subsystem: testing
tags: [classifier, calibration, qual-03, accuracy-harness, keyless, deterministic, no-llm, threshold]

# Dependency graph
requires:
  - phase: 09-defect-intelligence-jira-agent
    plan: 01
    provides: "pure classify() + gather_evidence/classify_failure + jira_confidence_threshold setting"
  - phase: 08-self-healing
    provides: "test_healing_mutations.py harness scaffolding (BREAK_REMOVE @8086) + the _MUTATION_HIGH calibrate-against-shipped-default discipline"
  - phase: 06-bdd-generation
    provides: "test_stability/test_seeded_bug planted-spec plant + SEED_BUG build @8081"
provides:
  - "QUAL-03 keyless three-class accuracy harness (test_classifier_accuracy.py): product_defect=SEED_BUG, automation=un-healed BREAK_REMOVE, infrastructure=NET-NEW dead-port/forced-timeout fault"
  - "Measured classification accuracy 10/10 = 1.00 (>= 0.85) over real-run evidence"
  - "Calibrated autonomous-filing separation window (0, 80] proven against the SHIPPED settings.jira_confidence_threshold (=70) — never a test-local literal"
  - "A NET-NEW keyless dead-port/forced-timeout infra-fault generator (the _port_open inverse, no Docker build)"
affects: [09-03-jira-client, 09-04-defect-pipeline, 09-05-review-queue-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Keyless accuracy harness cloned from test_healing_mutations.py: pytestmark functional, _port_open, _require_targets, inner `uv run python -m pytest` runner"
    - "Calibrate-against-shipped-default: `_THRESHOLD = _settings.jira_confidence_threshold` (the 08-04 `_MUTATION_HIGH = str(_settings.heal_high_threshold)` discipline)"
    - "Dead-port/forced-timeout infra fault = the _port_open inverse + a sub-second Chromium nav timeout (no build)"

key-files:
  created:
    - apps/api/tests/functional/test_classifier_accuracy.py
  modified: []

key-decisions:
  - "The shipped jira_confidence_threshold default (=70) already sits in the measured empirical separation window (0, 80] -> NO retune required; config.py is UNTOUCHED (the 08-04 retune precedent applied only IF the window demands it — here it does not)"
  - "classifier.py frozen weights (60/20/-15) UNTOUCHED — accuracy is 100%, no taxonomy/weight re-cut forced"
  - "The automation case reuses the QUAL-02 heal-wired plant/journal helpers VERBATIM so it exercises the SHIPPED heal path (fail_as_defect, never auto_heal), not a re-implementation"
  - "The infrastructure label is generated KEYLESSLY with no Docker build: a dead port (connection refused) + a non-routable host with a sub-second forced timeout (timeout-never-loaded)"

requirements-completed: [DEF-03, QUAL-03]

# Metrics
duration: ~40min
completed: 2026-06-27
---

# Phase 9 Plan 02: QUAL-03 Classifier Accuracy + Threshold Calibration Summary

**A keyless, deterministic three-class accuracy harness (Product Defect = SEED_BUG build, Automation = un-healed BREAK_REMOVE mutation, Infrastructure = a NET-NEW dead-port/forced-timeout fault) runs the production pure classifier over REAL-run evidence, proves accuracy 10/10 = 1.00 (>= 0.85), and calibrates the autonomous-filing floor into the measured separation window (0, 80] — asserted against the SHIPPED `settings.jira_confidence_threshold` (=70), never a literal.**

## Performance
- **Duration:** ~40 min
- **Completed:** 2026-06-27
- **Tasks:** 2 of 2
- **Files modified:** 1 (1 created, 0 modified)

## Accomplishments
- Cloned the QUAL-02 harness scaffolding (`test_healing_mutations.py`): `pytestmark = [functional]`, `_port_open`, `_require_targets`, and the inner `["uv","run","python","-m","pytest", ...]` runner (the 08-04 Windows Application Control deviation).
- Built the keyless three-class labeled set spanning all three classes with several instances each:
  - **product_defect** (3) — the SEED_BUG build (saucedemo-bug @8081): the planted login spec loads the post-login page and the `.inventory_list` success assertion FAILS.
  - **automation** (3) — the un-healed BREAK_REMOVE mutation (@8086): the deleted login button -> the heal-journal records `fail_as_defect` (never `auto_heal`) and the spec fails with a locator miss on a loaded page.
  - **infrastructure** (4) — a NET-NEW dead-port fault (connection refused @ a non-listening port) + a forced sub-second timeout against a non-routable host (TEST-NET-1) -> never-reached-target signature. No Docker build.
- Each generator returns the Plan-01 evidence dict (`error_text`, `page_loaded`, `heal_outcome`, `infra_health`) built from the REAL spec-subprocess output (and, for automation, the REAL heal-journal outcome), so the harness exercises the PRODUCTION `classify()` over real-run evidence — not a stub.
- Asserted accuracy >= 0.85 (measured 10/10 = 1.00 live), accumulated per-class confidences, derived the separating threshold, and asserted the SHIPPED `settings.jira_confidence_threshold` sits in the window via `_THRESHOLD = _settings.jira_confidence_threshold` (the `_MUTATION_HIGH` discipline) — proving the runtime default, never a literal (T-09-05).
- Emitted the per-class confidence matrix for auditability (the 08-04 measured-matrix precedent).

## Measured Per-Class Confidence Matrix (live, deterministic)

```
accuracy = 10/10 = 1.00
  product_defect  n=3 confidences=[80, 80, 80]   cited=[product:assertion-or-api, product:page-loaded]
  automation      n=3 confidences=[100,100,100]  cited=[automation:heal-fail_as_defect, automation:locator-miss, automation:page-loaded]
  infrastructure  n=4 confidences=[80,80,80,60]  cited=[infra:error-signature, infra:health-down] (60 = forced-timeout variant: infra:health-down only)
separation window for the autonomous-filing floor: (0, 80]
```

- The autonomous-filing floor is gated to **Product Defects** (the only class that becomes a ticket), so the separating window is `(max(misclassified_tail)=0, min(product_defect confidences)=80]`.
- The shipped default **`jira_confidence_threshold = 70` sits in `(0, 80]`** -> every correctly-classified product defect (conf 80) clears the autonomy gate, and the conservative starting point is preserved. **No retune required; `config.py` is untouched.**

## Task Commits
1. **Task 1: three-class labeled-set generators + dead-port infra fault** - `aecfcba` (test)
2. **Task 2: accuracy >= 85% + threshold calibration vs the shipped default** - `f8b8f2b` (test)

**Plan metadata:** see final docs commit.

## Files Created/Modified
- `apps/api/tests/functional/test_classifier_accuracy.py` - the QUAL-03 keyless accuracy harness + the calibration proof + the NET-NEW dead-port/forced-timeout infra-fault generator.

## Decisions Made
- **Config default already in the empirical window -> no retune.** The plan permitted retuning the `jira_confidence_threshold` DEFAULT into the measured window (the 08-04 0.85->0.15 precedent) *only if the window demanded it*. The measured window is `(0, 80]` and the shipped default is `70`, which is already inside it, so `config.py` is **untouched** — the conservative starting point validated empirically. This is the cleanest outcome the discipline allows (only the harness moves).
- **Classifier weights untouched.** Accuracy is 100%, so no taxonomy/weight re-cut was forced; `classifier.py` is not edited (it would have been a documented decision had accuracy < 85%).
- **Infrastructure label is fully keyless, no build.** A dead port (connection refused) + a non-routable host with a sub-second forced timeout cover both infra signatures (error-signature and timeout-never-loaded) without a Docker fault build.

## Deviations from Plan
**1. [Rule 3 — Blocking issue] `config.py` listed in `files_modified` was NOT edited.**
- **Found during:** Task 2 calibration.
- **Issue:** The plan's frontmatter and Task-2 `<files>` list `apps/api/app/core/config.py` as a modified file (in case the measured window required retuning the `jira_confidence_threshold` default).
- **Resolution:** The measured separation window `(0, 80]` already contains the shipped default `70`, so retuning is unnecessary and editing the default would only move it off its conservative starting point without empirical justification. Per the plan's own rule ("If the measured window demands it, retune ... only the config default + the harness proof move") and the QUAL-02 discipline (never special-case the test, never silently re-cut), the correct action is to leave `config.py` unchanged and prove the shipped default. The harness asserts the default sits in the window, so the config can never drift from the proof.
- **Files modified:** none (config.py intentionally untouched).
- **Commit:** n/a (a documented non-edit).

**2. [Rule 3 — Blocking issue] BREAK_REMOVE compose service name.**
- The compose service for the BREAK_REMOVE mutation is `saucedemo-break-remove` (not a bare profile name); the harness reaches it by host port `8086` regardless, and the builds were brought up with `docker compose --profile bugbuild --profile mutation up -d --wait saucedemo-bug saucedemo-break-remove`. No code impact.

## Issues Encountered
- The seeded-bug/mutation targets were down at execution start; brought up the `saucedemo-bug` (8081) and `saucedemo-break-remove` (8086) builds with neo4j OFF (3GB cap), ran the harness green, then proceeded. Full live run took ~3 min (10 Chromium subprocess spec runs).

## Verification
- `uv run python -m pytest tests/functional/test_classifier_accuracy.py -m functional -q --collect-only` -> 1 test collected (Task 1) / 2 tests after Task 2.
- `uv run python -m pytest tests/functional/test_classifier_accuracy.py -m functional -q -s` (SEED_BUG @8081 + BREAK_REMOVE @8086 up, neo4j OFF) -> **2 passed in 181s**; accuracy 10/10 = 1.00; separation window (0, 80]; shipped threshold 70 in-window.
- `uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional" -q` -> **365 passed, 142 deselected** (the deterministic suite stays green).
- Skips cleanly when builds are down: `_require_targets()` -> `pytest.skip` with the bring-up command (verified by the down-state probe at start).

## Known Stubs
None — the harness drives the production classifier over real spec-subprocess evidence; no placeholder/empty data paths.

## Threat Flags
None — no new network endpoints, auth paths, or schema changes. The harness is keyless (no provider keys, no real Jira), neo4j-OFF, and asserts against the shipped settings default (T-09-05 mitigated: config can never drift from the proof).

## User Setup Required
To re-run the QUAL-03 harness locally:
```
cd infra && docker compose --profile bugbuild up -d --wait saucedemo-bug
cd infra && docker compose --profile mutation up -d --wait
# neo4j OFF during the run phase (3GB WSL cap)
cd apps/api && uv run python -m pytest tests/functional/test_classifier_accuracy.py -m functional -q -s
```
The harness skips cleanly when the builds are down.

## Next Phase Readiness
- DEF-03 / QUAL-03 complete: classification accuracy proven >= 85% on the keyless hand-labeled set, and the autonomous-filing threshold calibrated + locked to the shipped config default. The autonomy gate (Plan 04) can now read `settings.jira_confidence_threshold` with empirical backing.
- Ready for Plan 03 (Jira client, gated `atlassian-python-api` install) and Plan 04 (defect pipeline consuming `classify_failure` post-retry, gated by the calibrated threshold).

## Self-Check: PASSED

The created artifact (test_classifier_accuracy.py, 09-02-SUMMARY.md) exists on disk; both task commits (aecfcba, f8b8f2b) exist in git history.

---
*Phase: 09-defect-intelligence-jira-agent*
*Completed: 2026-06-27*
