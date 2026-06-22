---
phase: 08-self-healing-engine
plan: 01
subsystem: testing
tags: [self-healing, deterministic-scorer, iou, difflib, dataclasses, playwright-geometry, fastapi-settings]

# Dependency graph
requires:
  - phase: 05-knowledge-graph-flow-learning
    provides: "kg/risk.py (frozen-weights + clamped-blend + tier-fn discipline to clone)"
  - phase: 04-explorer-agent
    provides: "explorer/locators.build_locator_chain healing-priority chain order + merge_locator_history"
provides:
  - "app/services/healing/confidence.py — HealWeights(frozen) + confidence(signals) blend + heal_outcome resolver with the hard uniqueness gate"
  - "app/services/healing/geometry.py — pure bounding-box IoU + size_proximity visual sub-score"
  - "app/services/healing/candidates.py — pure dom_sim/a11y_sim/history_sim + score_candidate assembler"
  - "config: heal_enabled / heal_high_threshold / heal_med_threshold (config-tunable bands)"
affects: [08-02 in-spec _healing.py vendoring, 08-03 worker journal ingest, 08-04 heal_audit + KG write-back, 08-05 mutation harness]

# Tech tracking
tech-stack:
  added: []  # ZERO new packages — stdlib (dataclasses/difflib/re) + Playwright box geometry only
  patterns:
    - "Pure-logic split + fixture-table tests (mirrors kg/risk.py): stdlib-only scorer, no browser/DB/graph/LLM, byte-vendorable into the in-spec layer"
    - "Hard uniqueness gate applied BEFORE confidence bands as a structural (not score-based) false-heal guard"
    - "Bounding-box IoU geometry for deterministic visual similarity (no pixel decode, no image lib)"

key-files:
  created:
    - apps/api/app/services/healing/__init__.py
    - apps/api/app/services/healing/confidence.py
    - apps/api/app/services/healing/geometry.py
    - apps/api/app/services/healing/candidates.py
    - apps/api/tests/unit/test_heal_confidence.py
    - apps/api/tests/unit/test_heal_outcome.py
    - apps/api/tests/unit/test_geometry.py
    - apps/api/tests/unit/test_heal_candidates.py
  modified:
    - apps/api/app/core/config.py

key-decisions:
  - "dom_sim normalizes over only the APPLICABLE components (attr-set Jaccard / tag / xpath-ancestry) so two elements identical on the attributes they expose score 1.0 even with no xpath present"
  - "history_sim tier weight derived from a local _TIER_RANK mirroring build_locator_chain order — keeps candidates.py importing only stdlib while still encoding healing priority"
  - "score_candidate imports geometry lazily (function-local) so the module-level import gate stays at 0 while reusing the pure IoU"
  - "visual sub-score averages IoU with size_proximity so a moved-but-same-size element retains visual signal"

patterns-established:
  - "Pure deterministic scorer (HealWeights frozen + clamped blend + uniqueness-gated resolver) — the keyless Phase-8 core"
  - "test_assertion_never_healed: sweep the full band x count matrix asserting every verdict is in the three locator-resolution outcomes (D-04 invariant)"

requirements-completed: [HEAL-01, HEAL-02]

# Metrics
duration: 12min
completed: 2026-06-22
---

# Phase 8 Plan 01: Pure Deterministic Self-Healing Scorer Summary

**Keyless, stdlib-only heal core: four [0,1] similarity sub-scores (DOM Jaccard, bounding-box IoU, a11y difflib, tier-weighted history) blend through frozen tunable weights into a [0,1] confidence, resolved to auto_heal / quarantine / fail_as_defect through a hard live-match uniqueness gate applied BEFORE the bands.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-22T16:23:28Z
- **Completed:** 2026-06-22T16:35:45Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 9 (4 source created, 4 tests created, 1 config modified)

## Accomplishments
- HEAL-01 confidence core: `HealWeights(frozen, dom=0.30/visual=0.20/a11y=0.30/history=0.20)` + `confidence(signals, w)` — a normalized, clamped [0,1] weighted blend (all-max → 1.0, empty → 0.0, pathological weights/signals clamped).
- HEAL-02 resolver: `heal_outcome(conf, live_match_count, *, high, med)` with the HARD `live_match_count != 1` uniqueness gate applied FIRST, then the three bands — count=0/count=2 at conf=0.99 both return `fail_as_defect` (the structural false-heal guard, QUAL-02 core property).
- HEAL-01 visual sub-score: pure `iou` + `size_proximity` bounding-box geometry — zero new packages, no pixel decode, no Playwright import.
- HEAL-01 DOM/a11y/history sub-scores + `score_candidate` assembler producing the exact `{dom, visual, a11y, history}` signals dict `confidence()` consumes; higher-tier history matches outscore equal lower-tier matches (build_locator_chain priority).
- Config-tunable bands wired into `Settings` (`heal_enabled` / `heal_high_threshold=0.85` / `heal_med_threshold=0.60`), mirroring `stability_runs`.

## Task Commits

Each task was committed atomically (TDD: test → feat):

1. **Task 1 RED: failing confidence + heal_outcome tests** — `aaface9` (test)
2. **Task 1 GREEN: confidence.py + heal settings** — `ec78d8e` (feat)
3. **Task 2 RED: failing geometry + candidate sub-score tests** — `9868a33` (test)
4. **Task 2 GREEN: geometry.py + candidates.py** — `e32b8a4` (feat)

## Files Created/Modified
- `apps/api/app/services/healing/__init__.py` — healing package marker + module doc (D-02 pure-engine invariant)
- `apps/api/app/services/healing/confidence.py` — HealWeights + confidence blend + uniqueness-gated heal_outcome
- `apps/api/app/services/healing/geometry.py` — pure IoU + size_proximity visual geometry
- `apps/api/app/services/healing/candidates.py` — dom_sim / a11y_sim / history_sim + score_candidate
- `apps/api/app/core/config.py` — heal_enabled / heal_high_threshold / heal_med_threshold settings
- `apps/api/tests/unit/test_heal_confidence.py` — 12 confidence table tests + pure-import gate
- `apps/api/tests/unit/test_heal_outcome.py` — uniqueness-gate-first bands + test_assertion_never_healed
- `apps/api/tests/unit/test_geometry.py` — IoU/size_proximity boundary tests + no-playwright gate
- `apps/api/tests/unit/test_heal_candidates.py` — sub-score tests + higher-tier-outscores-lower + pure-import gate

## Decisions Made
- **dom_sim applicable-component normalization:** the Jaccard / tag-bonus / xpath-ancestry components are blended over only the components that have data on at least one side, so two elements identical on the attributes they DO expose score 1.0 even when neither carries an xpath (xpath present on either side activates the ancestry component). This made `test_dom_sim_identical_attrs_is_high` pass without inflating scores for partial matches.
- **Local tier-rank for history_sim:** instead of importing `build_locator_chain` at module level (which the grep allowlist permits but is unnecessary), `_TIER_RANK` mirrors the chain priority order locally — candidates.py stays stdlib-only and the module-level import gate returns 0.
- **Lazy geometry import in score_candidate:** the `from app.services.healing.geometry import` lives inside the function, so the module-level `^(import|from)` gate is unaffected while still reusing the pure IoU.

## Deviations from Plan

None — plan executed exactly as written. The only implementation refinement (dom_sim applicable-component normalization) was within the planned `score_candidate`/`dom_sim` design and is documented under Decisions Made; it is not a deviation from any plan instruction.

## Issues Encountered
- Initial `dom_sim` blended fixed weights (Jaccard 0.5 / tag 0.2 / xpath 0.3), so identical attrs with no xpath scored 0.7 instead of 1.0. Resolved by normalizing over only the applicable components. Verified by re-running the unit suite (28 passed).

## Verification

- All four new unit files pass: **58 passed** (`test_heal_confidence.py` + `test_heal_outcome.py` + `test_geometry.py` + `test_heal_candidates.py`), sub-second per file, no browser/DB/keys.
- Grep gates green:
  - `confidence.py` non-stdlib module-level imports: **0**
  - `geometry.py` playwright references: **0**
  - `candidates.py` non-allowlisted module-level imports: **0**
- `test_assertion_never_healed` passes — heal_outcome only ever returns one of the three locator-resolution outcomes across the full band/count matrix.
- Settings `heal_enabled` / `heal_high_threshold` / `heal_med_threshold` present and defaulted (True / 0.85 / 0.60).
- Full deterministic suite (`-m "not live_llm and not graph and not e2e"`): **394 passed, 4 failed, 44 deselected.** The 4 failures are PRE-EXISTING Phase-7 functional tests that require the RabbitMQ queue profile (`AMQPConnectionError: connection refused`) — unrelated to this plan (no healing imports). Logged to `deferred-items.md`; not a code defect.

## Known Stubs
None — every function in this plan is fully implemented pure logic. (The in-spec `_healing.py` template, worker ingest, heal_audit model/migration, KG write-back, router, and mutation harness are scoped to plans 08-02..08-05, not stubs of this plan.)

## Next Phase Readiness
- The pure scorer is the keyless core every other Phase-8 plan consumes. Plan 08-02 can vendor `confidence`/`heal_outcome`/`iou`/sub-scores byte-for-byte into the in-spec `_healing.py` template (they are stdlib-only). The config bands are ready for the in-spec/worker callers to pass as `high`/`med`.
- Carry forward: a byte-equivalence drift-guard test (RESEARCH Open Q2) between `app/services/healing/` and the vendored `_healing.py` belongs in plan 08-02.

---
*Phase: 08-self-healing-engine*
*Completed: 2026-06-22*
