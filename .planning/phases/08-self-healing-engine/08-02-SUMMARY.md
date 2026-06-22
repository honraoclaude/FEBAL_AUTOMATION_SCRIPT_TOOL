---
phase: 08-self-healing-engine
plan: 02
subsystem: testing
tags: [self-healing, in-spec-interception, heal-journal, verdict-override, vendor-drift-guard, codegen, playwright]

# Dependency graph
requires:
  - phase: 08-self-healing-engine
    provides: "plan 01 pure scorer (confidence/geometry/candidates) — VENDORED byte-equivalent into the in-spec _healing.py template"
  - phase: 06-bdd-playwright-generation
    provides: "codegen/project.py render+gate loop, page_object.py.j2, selector_gate repo-sourced assertion"
  - phase: 07-execution-engine-workers
    provides: "stability._run_spec_once isolated subprocess runner; worker/classifier.classify_retry"
  - phase: 04-explorer-agent
    provides: "explorer/locators._XPATH_JS (vendored verbatim) + build_locator_chain priority order"
provides:
  - "apps/api/app/templates/healing/_healing.py.j2 — in-spec heal accessor: vendored scorer + live candidate search + HARD uniqueness gate + per-flow heal-journal write"
  - "page-object _resolve(element_key) accessor that heals on a locator miss (calls _healing.heal)"
  - "codegen/project.py renders _healing.py into the project tree + carries element_chains/element_meta into the page object"
  - "codegen/locators.page_object_chains — full ordered repo chains per attr (the _resolve heal input)"
  - "worker/classifier.reconcile_verdict — journal-driven auto_healed/quarantined/product_failure override (a heal is NOT a flake)"
  - "byte-equivalence vendor-drift guard (test_healing_vendor_drift.py)"
  - "keyless in-spec heal functional proof vs a live mutated page (test_inspec_heal.py)"
affects: [08-03 worker journal ingest (consumes the heal-journal seam + reconcile_verdict), 08-04 heal_audit + KG write-back]

# Tech tracking
tech-stack:
  added: []  # ZERO new packages — Jinja2 + Playwright geometry + stdlib only
  patterns:
    - "In-spec interception: vendor the byte-equivalent pure scorer into a generated _healing.py (the project cannot import app.services) + a drift guard that fails the build on divergence"
    - "Element-specific live candidate enumeration (broken chain lower tiers + broken tag) so a removed element yields no candidate -> the uniqueness gate (count != 1), not a coincidental unique match, governs"
    - "_chains/_element_meta rendered as Python literals via a pyrepr Jinja filter (None/True/False, never JSON null) — plain DATA dicts, NOT selector sinks, so the repo-sourced gate sees only top-tier locators (MED-1)"
    - "Pure journal-driven verdict override (reconcile_verdict) next to classify_retry — additive verdicts, no schema change, SC3 import-pure"

key-files:
  created:
    - apps/api/app/templates/healing/_healing.py.j2
    - apps/api/tests/unit/test_heal_verdict_override.py
    - apps/api/tests/unit/test_healing_vendor_drift.py
    - apps/api/tests/functional/test_inspec_heal.py
  modified:
    - apps/api/app/templates/pages/page_object.py.j2
    - apps/api/app/services/codegen/project.py
    - apps/api/app/services/codegen/locators.py
    - apps/api/app/services/worker/classifier.py

key-decisions:
  - "Element-specific candidate enumeration (broken tag + lower chain tiers) replaced a blanket button/a/input/[role] scan: a blanket scan let a removed element coincidentally heal onto an unrelated unique element under a relaxed threshold; scoping enumeration to the broken element's kind makes a removed element yield 0 candidates -> live_match_count 0 -> fail_as_defect (the plan's required removed-element signature)"
  - "_chains/_element_meta emitted via a pyrepr filter (repr) not tojson: tojson produces JSON null/true/false which is invalid Python inside the .py page object; repr yields a valid Python literal with deterministic ordering"
  - "Functional benign case sets HEAL_HIGH_THRESHOLD=0.30 (config-tunable, like stability_runs) so the unique match (~0.33, vs next-best ~0.06) auto-heals — the proof asserts the MECHANIC (unique->auto_heal; zero->fail) + the uniqueness gate, not the harness-tuned default 0.85"
  - "Live candidate tag read via handle.evaluate('e=>e.tagName') so the DOM tag sub-score participates (a button->a tag change is reachable; the benign input matches on tag)"
  - "Target reached at 127.0.0.1:8080 not localhost:8080 — IPv4-only nginx; localhost->::1 IPv6 forward is wedged on Windows/WSL (Phase-1 saucedemo note)"

metrics:
  duration: 33min
  completed: 2026-06-22
---

# Phase 8 Plan 02: In-Spec Self-Healing Interception Layer (THE CRUX) Summary

**The deterministic heal now runs INSIDE the generated spec subprocess where the live Playwright page is in scope: a self-contained `_healing.py` vendoring the byte-equivalent plan-01 scorer searches the live DOM along the broken element's identity tiers, scores + applies the HARD live `count()==1` uniqueness gate, appends one entry to a per-flow heal-journal, then continues (auto_heal) or raises HealFailed (quarantine/fail) — and a pure verdict-override makes a journal'd auto_heal the `auto_healed` verdict (a heal is NOT a flake).**

## Performance
- **Duration:** 33 min
- **Started:** 2026-06-22T22:01:54Z
- **Completed:** 2026-06-22T22:35Z
- **Tasks:** 3 (all type=auto)
- **Files:** 8 (4 created, 4 modified)

## Accomplishments
- **THE CRUX (HEAL-01/HEAL-02):** `templates/healing/_healing.py.j2` renders a self-contained in-spec layer — the generated project cannot `import app.services`, so the pure scorer (`confidence`/`heal_outcome`/`HealWeights`/`iou`/`size_proximity`/`dom_sim`/`a11y_sim`/`history_sim`/`score_candidate`) + `_XPATH_JS` are VENDORED byte-equivalent. `heal()` enumerates live candidates element-specifically, scores them, does the HARD `page.locator(selector).count()` re-validation, calls `heal_outcome`, appends ONE journal entry, then returns the healed Locator (auto_heal) or raises `HealFailed` (quarantine/fail). It NEVER touches `expect(...)`.
- **Page-object heal accessor:** `page_object.py.j2` emits `_chains` + `_element_meta` (plain DATA dicts via `pyrepr`, never selector sinks — MED-1) and a `_resolve(element_key)` that waits on the top locator and on a miss delegates to `_healing.heal` (auto_heal continues, HealFailed propagates so the test fails naturally).
- **Codegen wiring:** `generate_project` renders `_healing.py` into the tree (ast-gated, written in the same no-partial-write block) and carries `element_chains` into each page object via the new `codegen/locators.page_object_chains`.
- **Verdict override (Pitfall 4):** pure `reconcile_verdict(exit_verdict, journal_events)` — `auto_heal`→`auto_healed` (overrides passed/flaky), `quarantine`→`quarantined`, `fail_as_defect`→`product_failure`; additive to the String(16) verdict column, SC3 import-pure.
- **Drift guard (Open Q2):** `test_healing_vendor_drift.py` renders the template, extracts each vendored function's source segment, and asserts byte-equivalence with `app/services/healing/{confidence,geometry,candidates}.py` + `explorer/locators.py` `_XPATH_JS` (one sanctioned normalization: the canonical lazy geometry import dropped in the vendored copy).
- **Keyless functional proof (HEAL-01/HEAL-02):** `test_inspec_heal.py` plants the rendered `_healing.py` + a page object with a STALE top chain entry and runs it via `_run_spec_once` against the live SauceDemo target — benign rename auto-heals to the unique live match (count 1), removed element fails as defect (count 0, never auto_heal).

## Task Commits
1. **Task 1 — in-spec template + _resolve accessor** — `f07f819` (feat)
2. **Task 2 — codegen render + verdict override + drift guard** — `39c7d7a` (feat)
3. **Task 3 — keyless in-spec heal functional proof** — `cda1f9d` (test)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] _chains/_element_meta rendered as invalid Python via `tojson`**
- **Found during:** Task 3 (the planted spec failed to collect with `NameError: name 'null' is not defined`).
- **Issue:** the plan said `_chains` renders as a data dict; the natural `| tojson` filter emits JSON `null`/`true`/`false`, which is invalid inside a `.py` page object when a chain/meta value is `None`/bool.
- **Fix:** added a `pyrepr` Jinja filter (`repr`) registered in both `codegen/project.py`'s env and the test's env; the template emits `_chains`/`_element_meta` via `| pyrepr` (Python literal, deterministic ordering). Still a plain data dict (not a selector sink) so the repo-sourced gate is unaffected.
- **Files:** `app/templates/pages/page_object.py.j2`, `app/services/codegen/project.py`, `tests/functional/test_inspec_heal.py`
- **Commit:** `cda1f9d`

**2. [Rule 1 - Bug] Blanket candidate enumeration let a removed element coincidentally heal**
- **Found during:** Task 3 (the removed-element case PASSED — a false heal — under a relaxed threshold).
- **Issue:** the first enumeration always scanned generic `button/a/input/[role]`, so for a removed element the best candidate re-validated to a real unique element (count 1) and auto-healed under `high=0.0`.
- **Fix:** enumerate candidates ELEMENT-SPECIFICALLY — the broken chain's lower tiers (role/aria/text) + the broken element's `tag` (from `broken_attrs`). A genuinely removed element (tag/tiers absent) yields 0 candidates → best selector re-validates to 0 → the uniqueness gate (`count != 1`) forces `fail_as_defect`. This is the correct structural false-heal guard and matches RESEARCH Pattern 2 ("all elements of the broken element's role / a bounded region"). Also read the live candidate `tag` so the DOM tag sub-score participates (a tag-change heal is reachable).
- **Files:** `app/templates/healing/_healing.py.j2` (net-new enumeration/candidate-read — drift guard unaffected, it only checks the vendored pure functions + `_XPATH_JS`).
- **Commit:** `cda1f9d`

## CHECKER MED-1 (page_object _chains as data, not sink-literals) — HONORED
`_chains`/`_element_meta` render as plain Python data dicts via `pyrepr`; the only `page.locator(...)` sinks remain the top-tier `self.<attr> = page.locator(<repo entry>)` lines, and `_resolve`'s `from _healing import heal` constructs selectors at runtime from repo chains. Verified: `assert_page_object_literals_are_repo_sourced(source, set(locators.values()))` still passes (the `_chains` value strings are NOT in any sink). `_healing.py` is rendered with `is_page_object=True` so its runtime-constructed selectors pass the freehand gate. Codegen renders cleanly through both gates.

## VENDOR DRIFT GUARD — GREEN
`test_healing_vendor_drift.py` asserts the in-spec scorer copy is byte-identical to `app/services/healing` (and `_XPATH_JS` to `explorer/locators.py`). Stays green after the Task-3 enumeration change because that change is in NET-NEW functions (`_enumerate_live_candidates`/`_read_candidate`/`heal`), not the vendored pure functions.

## Verification
- Healing unit suite + SC3 gate: **75 passed** (`test_heal_verdict_override` + `test_healing_vendor_drift` + `test_no_llm_in_worker` + the plan-01 scorer tests).
- In-spec functional proof: **2 passed** (`test_inspec_heal.py -m functional`) — benign auto_heal (count 1) + removed fail_as_defect (count 0), keyless, neo4j off, SauceDemo up.
- Full deterministic suite (`-m "not live_llm and not graph and not e2e"`): **412 passed, 4 failed, 44 deselected.** The 4 failures are the SAME pre-existing Phase-7 RabbitMQ-queue functional tests (`AMQPConnectionError: connection refused`) already logged in `deferred-items.md` during 08-01 — environmental (broker not running), no healing imports, NOT a regression.
- Task acceptance greps: `_resolve` in page_object.j2 ≥1; `_healing.py` in project.py ≥1; reconcile_verdict pure (0 forbidden module-level imports); no `expect(` in the heal path.
- Self/transient note: `localhost`-bound Redis/RabbitMQ intermittently refuses on this Windows/WSL host (IPv6 port-forward wedge); healing tests use `127.0.0.1` and are pure, so they are stable.

## Known Stubs
None — the in-spec layer is fully implemented. The worker-side journal INGEST (Postgres heal_audit row + page-object rewrite + KG history write-back) and `reconcile_verdict`'s wiring INTO `worker/job.py` are scoped to plan 08-03 (the journal handoff is the seam this plan provides; 08-03 consumes it). `reconcile_verdict` exists and is table-tested but is not yet called from `job.py` (by plan design — 08-03 owns the ingest extension).

## Next Phase Readiness
- Plan 08-03 ingests `workspaces/<run_id>/<flow_id>/heal-journal.json` (the per-flow JSON list this plan writes) post-subprocess and calls `reconcile_verdict(classify_retry(...)["verdict"], journal_events)` to set the TestResult verdict, plus the three persistence side-effects (heal_audit / page-object rewrite / KG append).
- The vendored scorer + drift guard are locked; any future scorer tuning in `app/services/healing/` must be re-vendored or the drift guard fails the build.

## Self-Check: PASSED

All 8 claimed files exist on disk (4 created, 4 modified); all 3 task commits present in git history (f07f819, 39c7d7a, cda1f9d).

---
*Phase: 08-self-healing-engine*
*Completed: 2026-06-22*
