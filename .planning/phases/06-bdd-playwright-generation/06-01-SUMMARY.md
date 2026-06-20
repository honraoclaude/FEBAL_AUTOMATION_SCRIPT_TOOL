---
phase: 06-bdd-playwright-generation
plan: 01
subsystem: api
tags: [gherkin, pytest-bdd, neo4j, sqlalchemy, alembic, llm-gateway, scenarios, quality-gates]

# Dependency graph
requires:
  - phase: 05-knowledge-graph-flow-learning
    provides: "kg/reader (page_detail, element_repository, flows_source), kg/schema (edge constants, VERB_ENTITY_MAP), kg/flows.build_flows, kg/writer"
  - phase: 03-tracer-bullet-minimal-end-to-end-loop
    provides: "generation.py seam (gateway-routed, gherkin-validate-before-write, Jinja2 owns structure), run_service CRUD pattern, alembic chain (head 0005)"
  - phase: 02-llm-gateway
    provides: "llm_gateway.complete(operation_type, run_id) + BudgetExceeded/KillSwitchActive + deterministic no-key degrade pattern"
provides:
  - "Postgres scenarios table (migration 0006) + Scenario model (draft|approved|rejected + then_refs JSON sidecar)"
  - "scenario_service CRUD with status guard + list_approved (approved-only enforced in SQL)"
  - "gates/gherkin_lint.validate_gherkin (shared 29.x lint) + GenerationError (shared exception)"
  - "gates/assertion_gate.resolve_then_refs / assert_non_vacuous (structured Then->KG no-vacuous gate, read-only, injection-safe)"
  - "codegen/examples.derive_examples (pure KG->Examples outline data)"
  - "generation.generate_scenarios (gateway + no-key fallback + validate-before-persist draft writer)"
affects: [06-02-review-queue, 06-03-codegen, 06-04-stability-seeded-bug]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Structured Then->KG sidecar JSON gate: resolve refs by read-only count-existence Cypher; edge_type validated against kg/schema allow-list BEFORE query (injection-safe)"
    - "Pure KG->Examples derivation (form fields->columns, public-user matrix + required-empty negatives) — no LLM invents Example data"
    - "validate-before-persist (lint THEN no-vacuous) before any draft row write; gateway-only generation with deterministic no-key fallback"

key-files:
  created:
    - apps/api/app/models/scenario.py
    - apps/api/alembic/versions/0006_scenarios.py
    - apps/api/app/services/scenario_service.py
    - apps/api/app/services/gates/__init__.py
    - apps/api/app/services/gates/gherkin_lint.py
    - apps/api/app/services/gates/assertion_gate.py
    - apps/api/app/services/codegen/__init__.py
    - apps/api/app/services/codegen/examples.py
    - apps/api/tests/fixtures/kg_scenarios.py
    - apps/api/tests/unit/test_gherkin_lint.py
    - apps/api/tests/unit/test_assertion_gate.py
    - apps/api/tests/unit/test_examples_derivation.py
    - apps/api/tests/unit/test_generate_scenarios.py
    - apps/api/tests/functional/test_assertion_gate_graph.py
  modified:
    - apps/api/app/services/generation.py
    - apps/api/app/main.py

key-decisions:
  - "GenerationError moved into gates/gherkin_lint.py and re-imported by generation.py so generation AND the future edit/approve router share ONE exception type + ONE linter (D-04)"
  - "assertion_gate uses LIMIT 1 count-existence reads; edge_type injected as a kg/schema CONSTANT (never the LLM string); unknown kind / disallowed edge_type run NO Cypher"
  - "derive_examples carries a hidden expected_result + then_kind + then_ref per row (graph-backed page state) so negative rows stay no-vacuous-gate-satisfiable; visible columns are form fields + expected_result"
  - "generate_scenarios falls back to a minimal valid Feature whose single Then asserts the flow's terminal page (resolvable) on ANY gateway failure incl. empty-key auth error"

patterns-established:
  - "Sidecar JSON Then->kg_ref on the scenarios row (not a .feature comment) — survives edit, no Gherkin re-parse"
  - "Fake neo4j driver factory (resolves existence by params, logs every call) for unit-testing the gate with no neo4j/keys"

requirements-completed: [GEN-01, GEN-03]

# Metrics
duration: ~45min
completed: 2026-06-20
---

# Phase 6 Plan 01: Scenario Generation + Quality Gates Summary

**Postgres scenarios review-queue model + the structured Then->KG no-vacuous gate (read-only, injection-safe Cypher) + shared gherkin 29.x lint + deterministic KG->Examples derivation + a gateway-routed generate_scenarios with a no-key fallback that validates lint+no-vacuous before persisting a draft row.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-06-20T~15:00Z
- **Completed:** 2026-06-20
- **Tasks:** 3
- **Files modified:** 16 (14 created, 2 modified)

## Accomplishments
- `scenarios` table (migration 0006, chained after 0005) + `Scenario` model with the draft|approved|rejected lifecycle and a `then_refs` JSON sidecar; `scenario_service` with a VALID status guard and `list_approved` filtering approved-only in the SQL query (D-01).
- The novel deterministic trust mechanism: `assertion_gate.resolve_then_refs` / `assert_non_vacuous` reject every vacuous class (no ref / unresolvable / unknown kind / disallowed edge_type / zero Thens) using read-only LIMIT-guarded count-existence Cypher with the edge_type validated against the kg/schema allow-list BEFORE any query is built (injection safety, T-06-01).
- The gherkin 29.x lint gate was extracted into `gates/gherkin_lint.py` (validate_gherkin + GenerationError) and re-imported by generation.py so generation and the later edit/approve router share ONE linter and ONE exception (D-04).
- `codegen/examples.derive_examples` derives outline data deterministically from the KG (form fields -> columns; public Swag Labs user matrix + required-field-emptiness -> positive/negative rows whose Then references a graph-backed page state).
- `generation.generate_scenarios` routes one metered gateway call per flow (operation_type=generate.bdd) with a deterministic minimal valid+resolvable no-key fallback, then validate-before-persist (lint THEN no-vacuous) before writing a draft row — proven with mocked gateway + fake driver, zero spend, zero neo4j.

## Task Commits

1. **Task 1: scenarios model + migration 0006 + scenario_service + Wave-0 fixtures** - `ff1442c` (feat)
2. **Task 2: gherkin lint gate (extracted) + structured Then->KG no-vacuous gate** - `757827d` (feat)
3. **Task 3: KG->Examples derivation + generate_scenarios (gateway + no-key fallback)** - `d0572e1` (feat)

## Files Created/Modified
- `apps/api/app/models/scenario.py` - Scenario SQLAlchemy model (lifecycle + then_refs JSON)
- `apps/api/alembic/versions/0006_scenarios.py` - scenarios table migration (down_revision="0005")
- `apps/api/app/services/scenario_service.py` - CRUD + status guard + list_approved (approved-only in SQL)
- `apps/api/app/services/gates/gherkin_lint.py` - shared validate_gherkin + GenerationError
- `apps/api/app/services/gates/assertion_gate.py` - resolve_then_refs / assert_non_vacuous (read-only, injection-safe)
- `apps/api/app/services/codegen/examples.py` - pure KG->Examples derivation
- `apps/api/app/services/generation.py` - generate_scenarios + re-imported shared lint; removed duplicate Parser logic
- `apps/api/app/main.py` - register Scenario for Alembic metadata discovery
- `apps/api/tests/fixtures/kg_scenarios.py` - fixture KG + four-case then_refs + fake_driver
- `apps/api/tests/unit/test_{gherkin_lint,assertion_gate,examples_derivation,generate_scenarios}.py` - deterministic unit suite
- `apps/api/tests/functional/test_assertion_gate_graph.py` - seeded-graph resolution (graph-marked)

## Decisions Made
See key-decisions in frontmatter. Notably: the Examples rows carry hidden `then_ref`/`expected_result`/`then_kind` columns so a negative row's Then still resolves to an existing page-state (keeping the no-vacuous gate satisfiable), and the no-key fallback's single Then asserts the flow's terminal page (always graph-backed).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Renamed functional test to avoid a pytest basename collision**
- **Found during:** Task 3 (running the full default suite)
- **Issue:** The plan named both `tests/unit/test_assertion_gate.py` and `tests/functional/test_assertion_gate.py`. Under pytest's default import mode with no `tests/__init__.py`, two files sharing a basename collide ("import file mismatch") and abort collection of the whole suite.
- **Fix:** Renamed the functional file to `tests/functional/test_assertion_gate_graph.py` (content unchanged; still `@pytest.mark.graph`).
- **Files modified:** apps/api/tests/functional/test_assertion_gate_graph.py (renamed from test_assertion_gate.py)
- **Verification:** `uv run pytest -m "not live_llm and not e2e and not graph"` collects + passes (260 passed).
- **Committed in:** d0572e1 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** A pure test-file rename to satisfy pytest collection; no behavior change, no scope creep. The functional graph test is preserved verbatim.

## Issues Encountered
- A class-body closure bug in the test fixture Controller (`created = created` at class scope) raised NameError; fixed by moving the bindings into `__init__`. Resolved during Task 3, no impact on shipped code.

## Verification Results
- `uv run alembic upgrade head` -> head **0006**.
- `uv run pytest -m "not live_llm and not e2e and not graph"` -> **260 passed, 34 deselected** (includes all new unit tests; no regressions).
- `uv run pytest tests/unit/test_single_write_path.py` -> green (assertion_gate adds zero write-Cypher).
- `grep init_chat_model app/services/generation.py` -> no match (gateway-only, D-07).
- Functional graph test (`tests/functional/test_assertion_gate_graph.py -m graph`) authored; runs under graph_mode (not executed in this default-suite run — provider keys/neo4j Manual-Only per project convention).

## User Setup Required
None - no external service configuration required. Live generation needs ANTHROPIC_API_KEY/OPENAI_API_KEY (Manual-Only); all gates/derivation are deterministically proven without keys.

## Next Phase Readiness
- Slice 1 foundation complete: a flow can be turned into a quality-gated draft scenario row.
- Ready for Slice 2 (review queue API + UI): the shared `validate_gherkin` + `assert_non_vacuous` are reusable by the edit/approve router (D-02/D-04); `scenario_service` already exposes set_status/update_gherkin/list_approved.
- Graph functional + live generation remain Manual-Only (keys/neo4j).

## Self-Check: PASSED

All 7 spot-checked created files exist on disk; all 4 commits (ff1442c, 757827d, d0572e1, dde77a2) are present in git history.

---
*Phase: 06-bdd-playwright-generation*
*Completed: 2026-06-20*
