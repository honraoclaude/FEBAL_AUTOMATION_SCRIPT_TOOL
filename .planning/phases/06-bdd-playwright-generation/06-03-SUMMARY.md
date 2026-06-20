---
phase: 06-bdd-playwright-generation
plan: 03
subsystem: api
tags: [codegen, jinja2, pytest-bdd, playwright, element-repository, selector-gate, ast, neo4j]

# Dependency graph
requires:
  - phase: 06-bdd-playwright-generation
    provides: "scenario_service.list_approved (approved-only), Scenario model + then_refs sidecar (06-01); GenerateScriptsRequest schema + auth-gated generate router (06-02); codegen.examples.derive_examples (06-01)"
  - phase: 05-knowledge-graph-flow-learning
    provides: "kg/reader.element_repository (deserialized locator chain), page_detail, flows_source; kg/flows.build_flows; kg/writer (graph-test seeding)"
  - phase: 03-tracer-bullet-minimal-end-to-end-loop
    provides: "generation.py Jinja2 render→ast.parse→write seam, templates/test_login.py.j2 header contract, core/workspaces.run_dir (gitignored)"
provides:
  - "gates/selector_gate.scan_for_freehand_selectors / assert_no_freehand_selectors / assert_page_object_literals_are_repo_sourced (static AST freehand-selector gate with page-object allowlist + raw CSS/XPath regex fallback)"
  - "codegen/locators.page_object_locators (Element-Repository top-priority chain entry per element → deterministic snake_case page-object attr; read-only, fake-driver unit-testable)"
  - "codegen/project.generate_project (approved-only Jinja2 project tree: pages/steps/features/conftest/fixtures/utils/data/reports under workspaces/<run_id>/target/; ast.parse + selector gate EVERY .py before any write)"
  - "Jinja2 template set (pages/page_object, steps/steps [pytest-bdd bound to .feature], conftest, fixtures, utils, data_model)"
  - "POST /generate-scripts rewired to the project codegen (GenerateScriptsRequest; GenerationError/SelectorGateError → 422)"
affects: [06-04-stability-seeded-bug]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Static freehand-selector AST gate: walk Call nodes for selector sinks (page.locator/fill/click/...; get_by_role/_text/_test_id/_label/_placeholder) with a Constant str first arg → violation in spec/step modules; page objects are the single sanctioned literal home (allowlist); regex fallback for raw CSS/XPath/attr string constants"
    - "Page-object literals asserted repo-traceable: every literal locator in a page-object module must equal a supplied Element-Repository chain entry"
    - "Render-all-in-memory then write-only-after-all-gates-pass: no partial project tree on a parse failure or a selector violation"
    - "Locators are TEMPLATE LOOKUPS from the KG Element Repository (top-priority chain entry by element key), never LLM/template slots"

key-files:
  created:
    - apps/api/app/services/gates/selector_gate.py
    - apps/api/app/services/codegen/locators.py
    - apps/api/app/services/codegen/project.py
    - apps/api/app/templates/pages/page_object.py.j2
    - apps/api/app/templates/steps/steps.py.j2
    - apps/api/app/templates/conftest.py.j2
    - apps/api/app/templates/fixtures.py.j2
    - apps/api/app/templates/utils.py.j2
    - apps/api/app/templates/data_model.py.j2
    - apps/api/tests/unit/test_selector_gate.py
    - apps/api/tests/functional/test_codegen.py
  modified:
    - apps/api/app/routers/generate.py
    - apps/api/tests/functional/test_generation.py
    - apps/api/tests/functional/test_run_thread.py

key-decisions:
  - "selector_gate detects via ast.walk over Call nodes (selector-sink method + Constant str first arg) PLUS a regex fallback for raw CSS/XPath/attr string constants (^#, ^., ^//, [attr=); page-object modules pass unconditionally (is_page_object=True) and are separately asserted repo-sourced"
  - "page_object_locators derives a deterministic snake_case attr name from role+label and takes the TOP-priority chain entry (chain is already prioritized data-testid→aria-label→role→text→xpath by kg/reader); elements with no usable chain entry are skipped (never a fabricated locator)"
  - "generate_project renders the WHOLE tree in memory, ast.parse + selector-gates every .py, and writes ONLY after all pass (no partial write on a violation); reports/ created empty for the runner"
  - "POST /generate-scripts rewired from the Phase-3 plain-spec to the approved-scenario project codegen; the plain-spec generation.generate_scripts + test_login.py.j2 are RETAINED for the planted-spec/execute proofs (the live thread test uses the retained plain spec for its execute leg — execution-engine integration with the codegen tree is Phase 7)"

patterns-established:
  - "Fake element-repository driver (yields deserialized chain rows) for unit-testing locator mapping with no neo4j/keys"
  - "Codegen functional test seeds Neo4j via kg/writer over a host Bolt driver + the approved/draft scenario over a host SQLAlchemy engine (mirrors test_assertion_gate_graph + test_scenarios_router)"

requirements-completed: [GEN-04, GEN-05]

# Metrics
duration: ~12min
completed: 2026-06-20
---

# Phase 6 Plan 03: Element-Repository Codegen + Freehand-Selector Gate Summary

**The approved-scenario → full Playwright project codegen (GEN-04) where every page-object locator is pulled from the Phase-5 Element Repository by element key (never a freehand LLM selector), plus the static freehand-selector AST gate (GEN-05a) that rejects any inline selector literal in a spec/step module while allowing repo-traceable literals only in page-object modules — Jinja2 owns all structure, ast.parse + the gate run on every rendered .py before any write, and codegen reads status=approved only (D-01).**

## Performance
- **Duration:** ~12 min
- **Completed:** 2026-06-20
- **Tasks:** 2 (Task 1 TDD: RED→GREEN)
- **Files modified:** 14 (11 created, 3 modified)

## Accomplishments
- **Freehand-selector AST gate (`gates/selector_gate.py`, GEN-05a / D-05):** `scan_for_freehand_selectors` walks `ast` Call nodes for selector sinks (`page.locator/fill/click/...`, `get_by_role/_text/_test_id/_label/_placeholder`) with a `Constant` str first arg → violation in spec/step modules; a regex fallback catches raw CSS/XPath/attr string constants (`^#`, `^.`, `^//`, `[attr=`). Page-object modules are the single sanctioned literal home (`is_page_object=True` → no violation). `assert_no_freehand_selectors` (the codegen caller) raises `SelectorGateError`; `assert_page_object_literals_are_repo_sourced` proves every page-object literal equals a supplied repo chain entry. The AST cousin of the Phase-4 single-write-path grep gate — pure, unit-tested on rendered fixtures with no keys/neo4j.
- **Element-Repository locator lookup (`codegen/locators.py`, D-05):** `page_object_locators(page_fp)` reads `kg/reader.element_repository` (read-only), filters to the page, and maps each element to `{deterministic snake_case attr: top-priority chain entry}` — the repo (not the LLM) owns every locator; an element with no usable chain entry is skipped (never fabricated). This is the Phase-3 `OBSERVED_SELECTORS` tuple generalized to a KG query.
- **Project codegen (`codegen/project.py`, GEN-04 / D-01/D-06):** `generate_project(db, run_id)` reads `scenario_service.list_approved` (approved-only), mines the run's flows to find KG pages, renders repo-sourced page objects + pytest-bdd step-defs bound to each approved `.feature` + conftest/fixtures/utils/data, and creates `reports/` — all under `workspaces/<run_id>/target/`. EVERY rendered `.py` is `ast.parse`d (a non-importable render → `GenerationError`) and run through the freehand-selector gate BEFORE any write; the whole tree is rendered in memory and written only after all gates pass (no partial write). Page-object literals are additionally asserted repo-sourced.
- **Jinja2 template set:** `pages/page_object.py.j2` (repo-locator attributes + `@then` assertion helpers), `steps/steps.py.j2` (pytest-bdd `@given/@when/@then` + `scenarios("<feature>")` binding; each `@then` calls a page-object assertion — no literal selector), `conftest.py.j2` (env-overridable base URL via `TARGET_BASE_URL` so Slice 4 can point at the seeded-bug build), `fixtures.py.j2`, `utils.py.j2`, `data_model.py.j2` (dataclass fields = KG-derived Examples columns). Each carries the `test_login.py.j2` header contract; selectors are template lookups, never slots.
- **`POST /generate-scripts` rewired** to the project codegen (`GenerateScriptsRequest`; `GenerationError`/`SelectorGateError` → 422); the Phase-3 plain-spec path + `test_login.py.j2` are retained for the planted-spec/execute proofs.

## Task Commits
1. **Task 1 (TDD): freehand-selector AST gate + Element-Repository locator lookup** — `40130c0` (test, RED) → `d3fd4cc` (feat, GREEN)
2. **Task 2: Jinja2 templates + codegen/project.py + generate-scripts entrypoint** — `d3425f8` (feat)

## Files Created/Modified
- `apps/api/app/services/gates/selector_gate.py` — static AST freehand-selector gate (page-object allowlist + regex fallback + repo-traceability assertion)
- `apps/api/app/services/codegen/locators.py` — Element-Repository locator lookup (top chain entry → snake_case attr)
- `apps/api/app/services/codegen/project.py` — approved-only Jinja2 project-tree codegen (ast.parse + selector gate every .py before any write)
- `apps/api/app/templates/{pages/page_object,steps/steps,conftest,fixtures,utils,data_model}.{py.,}j2` — the template set
- `apps/api/app/routers/generate.py` — `/generate-scripts` → `codegen.generate_project`
- `apps/api/tests/unit/test_selector_gate.py` — 15 deterministic gate + locator cases (no keys/neo4j)
- `apps/api/tests/functional/test_codegen.py` — non-graph gate-rejection + graph-marked full-tree codegen
- `apps/api/tests/functional/test_generation.py`, `test_run_thread.py` — live_llm chains retargeted to the codegen contract / retained plain-spec execute leg

## Decisions Made
See key-decisions in frontmatter. Notably: codegen renders the whole tree in memory and writes only after every `.py` passes both `ast.parse` and the selector gate (no partial write on a violation); `/generate-scripts` now produces a project tree (not a single `test_login.py`), so the live thread test's execute leg uses the retained Phase-3 plain spec (execution-engine integration with the codegen tree is Phase 7).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Retargeted the live_llm generate/thread tests to the superseded generate-scripts contract**
- **Found during:** Task 2 (rewiring `/generate-scripts`)
- **Issue:** Two Manual-Only tests (`test_generation.py::test_generate_bdd_and_scripts_end_to_end`, `test_run_thread.py`) asserted the Phase-3 plain-spec generate-scripts contract (`spec_path` ending `test_login.py` + `.inventory_list`). The plan explicitly supersedes that router behavior with the project codegen, so those assertions were stale and would fail when run with keys.
- **Fix:** `test_generation` now generates scenarios → approves → calls `/generate-scripts` and asserts the `project_root`/tree (matching the new D-01 approved-only codegen). `test_run_thread` renders the RETAINED plain spec via `generation.generate_scripts` for its `/execute` leg (whose codegen-tree integration is Phase 7) so the explore→generate→execute thread stays coherent.
- **Files modified:** apps/api/tests/functional/test_generation.py, apps/api/tests/functional/test_run_thread.py
- **Verification:** both collect cleanly; full default suite 286 passed (they remain deselected without keys).
- **Committed in:** d3425f8 (Task 2)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** No scope change — a contract-alignment fix for the superseding `/generate-scripts` behavior the plan called for; no new packages, no behavior change to shipped codegen.

## Verification Results
- `uv run pytest tests/unit/test_selector_gate.py -x -q` → **15 passed** (all sink/CSS/XPath/page-object-allow/reference-allow/repo-sourced/locator cases).
- `uv run pytest tests/functional/test_codegen.py -m "not graph" -q` → **1 passed** (injected step literal rejected, no tree).
- All six Jinja2 templates render → `ast.parse` → pass the selector gate (verified via the in-memory `_render_checked_py` path; temp probe removed).
- `uv run pytest tests/unit/test_single_write_path.py -q` → **2 passed** (codegen adds zero write-Cypher).
- `grep init_chat_model app/services/codegen/project.py` → no match (deterministic codegen).
- `git diff --stat apps/api/app/templates/test_login.py.j2` → empty (unchanged; Slice 4 needs it).
- `uv run pytest -m "not live_llm and not e2e and not graph" -q` → **286 passed, 39 deselected** (+16 over 06-02's 270; no regressions).

## Manual-Only (provider keys / graph)
- `tests/functional/test_codegen.py::test_generate_project_builds_full_repo_sourced_tree` (`-m graph`) seeds Neo4j (Element Repository) + an approved scenario and asserts the full repo-sourced tree — authored + green-by-construction, run under graph_mode per project convention.
- The live generate→review→approve→codegen chain (`test_generation.py`, `test_run_thread.py`) needs a provider key — Manual-Only.
- **OOM note (carried for Slice 4):** codegen reads the Element Repository under graph_mode (neo4j up); the stability/seeded-bug RUN phase needs no graph — stop neo4j before any run phase.

## Next Phase Readiness
- Slice 3 complete: an approved scenario generates a full Element-Repository-sourced Playwright project (pages/steps/features/conftest/fixtures/utils/data/reports) with pytest-bdd step-defs bound to the `.feature`; the freehand-selector AST gate rejects inline literals; codegen reads approved-only.
- Ready for Slice 4 (N-run stability + seeded-bug): `conftest.py.j2` already reads `TARGET_BASE_URL` so the harness can point the SAME generated spec at the standard target or the seeded-bug build; the planted-spec proof can reuse the retained `test_login.py.j2`.

## Self-Check: PASSED
All key created files exist on disk; all three task commits (40130c0, d3fd4cc, d3425f8) are present in git history.

---
*Phase: 06-bdd-playwright-generation*
*Completed: 2026-06-20*
