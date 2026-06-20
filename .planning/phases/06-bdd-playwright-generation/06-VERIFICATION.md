---
phase: 06-bdd-playwright-generation
verified: 2026-06-20T18:30:00Z
status: human_needed
score: 5/5 must-haves verified (deterministic contract); 3 Manual-Only items pending human run
overrides_applied: 0
mode: mvp
human_verification:
  - test: "Live generate → review → approve → codegen → stabilize → seeded-bug (full chain with provider keys)"
    expected: "With ANTHROPIC_API_KEY/OPENAI_API_KEY set: explore SauceDemo (graph_mode), POST /generate-scenarios produces drafts with outlines+Examples (every Then resolvable), approve in the review UI, POST /generate-scripts emits the repo-sourced Playwright tree, run_stability passes N×, run_seeded_bug FAILS vs saucedemo-bug (8081)"
    why_human: "Requires real LLM spend + a real explored graph; provider keys are empty by project convention (same as Phases 4-5). The deterministic mechanics underneath are fully proven without keys."
  - test: "Graph-marked deterministic tests under graph_mode (assertion-gate-graph, codegen full tree, stability/seeded-bug planted spec)"
    expected: "graph_mode up; saucedemo (8080) + saucedemo-bug (8081) built and up; stop neo4j before the run phase (OOM sequencing). test_assertion_gate_graph, test_codegen -m graph, test_stability/-m graph (2), test_seeded_bug -m graph (3) all green."
    why_human: "Needs the live neo4j + saucedemo + saucedemo-bug stack running; the 44 deselected tests are correctly excluded from the keyless gate. Authored + green-by-construction; the harness logic itself is proven by the in-process planted-spec runs."
  - test: "Memory fit: neo4j + saucedemo + saucedemo-bug + Chromium under the 3GB WSL cap"
    expected: "docker stats during the seeded-bug harness stays under 3GB with the documented sequencing (codegen reads the Element Repository under graph_mode, then STOP neo4j before run_stability/run_seeded_bug)."
    why_human: "Host Vmmem observation only measurable by running the stack on the dev box."
deferred: []
---

# Phase 6: BDD & Playwright Generation Verification Report

**Phase Goal:** User turns discovered flows into reviewed, quality-gated Gherkin scenarios and stable Playwright automation they own
**Verified:** 2026-06-20T18:30:00Z
**Status:** human_needed
**Re-verification:** No — initial verification
**Mode:** mvp

## User Flow Coverage

User goal: «Turn discovered flows into reviewed, quality-gated Gherkin scenarios and stable Playwright automation the user owns.»

(The ROADMAP goal is not in strict "As a…, I want…, so that…" user-story syntax. It is verified here as the user-outcome it describes — the per-step coverage below maps the five SCs to codebase evidence. The live walk-through with provider keys is the human_needed item.)

| Step | Expected | Evidence | Status |
|------|----------|----------|--------|
| Generate scenarios from flows | POST /generate-scenarios mines flows → gated draft rows with outlines + KG-derived Examples | `app/routers/generate.py:7` (/generate-scenarios feeder), `generation.py:357 generate_scenarios` (per-flow gateway call + fallback + validate-before-persist), `codegen/examples.py derive_examples` (pure KG→Examples) | ✓ |
| Quality gate every scenario | Gherkin lint + every Then resolves to a KG outcome before a draft is written | `gates/gherkin_lint.validate_gherkin` (29.x Parser) + `gates/assertion_gate.assert_non_vacuous` run BEFORE `create_scenario` (`generation.py:390-400`) | ✓ |
| Review queue: approve/edit | Drafts land in a UI queue; edit + approve re-run BOTH gates; only approved feed codegen | `routers/scenarios.py` (auth-gated; edit:234, approve:252 both re-run lint+no-vacuous → 422 on fail), `scenario_service.list_approved` (approved-only in SQL), `apps/web/.../scenarios/page.tsx` + `[id]/page.tsx` | ✓ |
| Generate Playwright project | pages/steps/features/fixtures/utils/data/reports tree; every locator from the Element Repository | `codegen/project.generate_project` (full tree, approved-only, ast.parse+selector-gate before write), `codegen/locators.page_object_locators` (top repo chain entry per element key) | ✓ |
| Stability + breakage gate | Accepted iff N green vs standard AND red vs the seeded-bug build | `services/stability.accept_spec` (run_stability all-green AND run_seeded_bug detected_breakage), `infra/targets/saucedemo/Dockerfile` SEED_BUG, `docker-compose.yml` saucedemo-bug | ✓ |
| Outcome: user owns reviewed + stable automation | Reviewed (approve/edit gated) + stable (N-run + seeded-bug) tree under workspaces/<run_id>/ | All five SCs verified above; full live chain is the human_needed walk-through | ⚠ pending live run |

## Goal Achievement

### Observable Truths

| # | Truth (Success Criterion) | Status | Evidence |
|---|---------------------------|--------|----------|
| 1 | SC1/GEN-01: generate features/scenarios incl. outlines + data-driven Examples from discovered flows | ✓ VERIFIED | `generation.generate_scenarios` routes one metered `generate.bdd` gateway call per flow with a deterministic no-key fallback; `codegen/examples.derive_examples` is PURE (grep: no init_chat_model/llm_gateway) — derives columns from KG form fields + positive/negative rows; unit tests `test_examples_derivation.py` + `test_generate_scenarios.py` green |
| 2 | SC2/GEN-03: gherkin lint gate + every Then asserts a KG-recorded outcome (no vacuous) | ✓ VERIFIED | `gherkin_lint.validate_gherkin` uses `from gherkin.parser import Parser` (29.x transitive, NO pin). `assertion_gate` is read-only (only `execute_read` count-existence, zero write-Cypher), edge_type validated against kg/schema `{Creates,Updates,Deletes}` allow-list BEFORE any Cypher is built (injection-safe), all 5 vacuous classes rejected. `test_assertion_gate.py` uses a FAKE driver (no neo4j/keys), asserts NO Cypher for unknown-kind/disallowed-edge via the call log. Re-run on edit AND approve in the router (D-04) |
| 3 | SC3/GEN-02: approve/edit review queue; only approved feed codegen | ✓ VERIFIED | `routers/scenarios.py` router-level `Depends(get_current_user)`; edit (line 234) + approve (line 252) both re-run `validate_gherkin` THEN `assert_non_vacuous` → 422 + no save on fail. `scenario_service.list_approved` filters `status=="approved"` in the SQL query. `codegen/project.generate_project` reads `list_approved` only (raises if none). UI: list + detail pages, native `<textarea>` (no shadcn add), honest server-authoritative per-Then indicators |
| 4 | SC4/GEN-04: full Playwright structure with locators sourced ONLY from the Element Repository | ✓ VERIFIED | `generate_project` emits pages/steps/features/fixtures/utils/data + empty reports/. `page_object_locators` pulls each element's top-priority chain entry from `kg/reader.element_repository` by key (read-only). `selector_gate` is AST-based (`ast.walk`/NodeVisitor over selector-sink Calls; regex only a fallback for raw CSS/XPath constants): rejects inline literals in spec/step modules, allows page-object literals, AND `assert_page_object_literals_are_repo_sourced` proves each == a supplied repo chain entry. Every rendered .py is ast-parsed + gated before any write (render-in-memory, write-only-after). `test_selector_gate.py` 15 cases on rendered fixtures (fake driver) green |
| 5 | SC5/GEN-05: N-run stability check + seeded-bug build the accepted tests must fail against | ✓ VERIFIED | `stability.run_stability` reuses the Phase-3 `create_subprocess_exec` shape VERBATIM (argv LIST, no shell, NO in-process pytest — grep confirms `pytest.main`/`shell=True` appear ONLY in docstring prose), N from `settings.stability_runs` (default 3), accept iff all green (fail-fast). `Dockerfile` SEED_BUG build-arg (default 0 byte-identical; SEED_BUG=1 renames `.inventory_list`→`_BROKEN`). `docker-compose.yml` saucedemo-bug: profile `[bugbuild]`, port 8081, mem_limit 128m. `accept_spec` = green-vs-std AND red-vs-bug. Proven by planted template-rendered spec (`test_stability.py`/`test_seeded_bug.py`, graph-marked, no keys) |

**Score:** 5/5 truths verified (deterministic contract holds)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/services/gates/gherkin_lint.py` | shared 29.x lint + GenerationError | ✓ VERIFIED | `from gherkin.parser import Parser`; no pyproject pin |
| `app/services/gates/assertion_gate.py` | read-only injection-safe no-vacuous gate | ✓ VERIFIED | execute_read only; allow-list validated pre-Cypher; all vacuous classes |
| `app/services/gates/selector_gate.py` | AST freehand-selector gate + repo-traceability | ✓ VERIFIED | ast NodeVisitor + regex fallback + page-object allowlist + repo-sourced assertion |
| `app/services/codegen/examples.py` | pure KG→Examples derivation | ✓ VERIFIED | no LLM (grep clean) |
| `app/services/codegen/locators.py` | Element-Repository locator lookup | ✓ VERIFIED | top chain entry by element key; read-only; skips no-chain elements |
| `app/services/codegen/project.py` | full approved-only Jinja2 tree | ✓ VERIFIED | list_approved + ast.parse + selector gate before any write |
| `app/services/generation.py` | gateway-only generate_scenarios + fallback | ✓ VERIFIED | llm_gateway.complete only; validate-before-persist |
| `app/services/stability.py` | N-run + seeded-bug + accept_spec | ✓ VERIFIED | subprocess (no in-process pytest); green-AND-red acceptance |
| `app/models/scenario.py` + `alembic/versions/0006_scenarios.py` | scenarios table chained after 0005 | ✓ VERIFIED | down_revision='0005'; lifecycle + then_refs JSON sidecar; chain 0001→0006 linear |
| `app/routers/scenarios.py` | auth-gated review router | ✓ VERIFIED | router-level get_current_user; both gates on edit+approve; registered in main.py:112 |
| `app/templates/` (7 templates) | Jinja2 owns structure | ✓ VERIFIED | conftest/data_model/fixtures/utils + pages/page_object + steps/steps + retained test_login |
| `apps/web/.../scenarios/*` + `components/scenarios/*` | review-queue UI, zero new deps | ✓ VERIFIED | list + [id] pages; native textarea; honest gate indicators; no textarea.tsx vendored |
| `infra/targets/saucedemo/Dockerfile` + `docker-compose.yml` | SEED_BUG + saucedemo-bug | ✓ VERIFIED | build-arg default-off; profile bugbuild; port 8081; mem_limit 128m |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| review router edit/approve | both quality gates | validate_gherkin + assert_non_vacuous before write | ✓ WIRED | scenarios.py:234,252 |
| codegen | approved scenarios only | scenario_service.list_approved | ✓ WIRED | project.py:134 (raises if empty) |
| page objects | Element Repository | page_object_locators → kg/reader.element_repository | ✓ WIRED | locators.py:71 |
| generated conftest | TARGET_BASE_URL override | base_url_env slot filled by project.py | ✓ WIRED | conftest.py.j2 `os.environ.get({{base_url_env}})`; project.py:237 |
| seeded-bug run | saucedemo-bug build | run_seeded_bug sets TARGET_BASE_URL → SEEDED_BUG_BASE_URL | ✓ WIRED | stability.py:147; compose default http://saucedemo-bug:80 |
| stability harness | Phase-3 subprocess runner | create_subprocess_exec + _run_cwd | ✓ WIRED | stability.py:74 (no in-process pytest) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full deterministic suite (independent re-run) | `uv run pytest -m "not live_llm and not e2e and not graph" -q` | 286 passed, 44 deselected in 70s | ✓ PASS |
| 5 novel-mechanism unit files | `uv run pytest test_assertion_gate test_gherkin_lint test_selector_gate test_examples_derivation test_generate_scenarios -q` | 37 passed in 3.87s | ✓ PASS |
| Subprocess discipline (no in-process pytest) | grep `stability.py` for create_subprocess_exec / pytest.main / shell=True | create_subprocess_exec (argv list) present; pytest.main/shell=True only in docstring prose | ✓ PASS |
| No new gherkin pin | grep pyproject.toml for gherkin | no match (transitive 29.x only) | ✓ PASS |
| No new frontend shadcn textarea | ls components/ui/textarea.tsx | absent (native styled textarea used) | ✓ PASS |
| Alembic chain reachable | head 0006, down_revision 0005, chain 0001→0006 linear | confirmed | ✓ PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes declared for this phase; the planted-spec functional tests (graph-marked) are the phase's runnable verification and are routed to human_needed (live stack required).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| GEN-01 | 06-01 | features/scenarios incl. outlines + Examples from flows | ✓ SATISFIED | generate_scenarios + derive_examples |
| GEN-02 | 06-02 | approve/edit review queue; only approved feed codegen | ✓ SATISFIED | scenarios router + list_approved + UI |
| GEN-03 | 06-01 | syntax lint + every Then KG-recorded (no vacuous) | ✓ SATISFIED | gherkin_lint + assertion_gate |
| GEN-04 | 06-03 | full Playwright structure, repo-only locators | ✓ SATISFIED | project.generate_project + locators |
| GEN-05 | 06-03/06-04 | repo locators + N-run stability + seeded-bug | ✓ SATISFIED | selector_gate + stability + SEED_BUG |

No orphaned requirements (REQUIREMENTS.md maps only GEN-01..05 to Phase 6; all claimed by plans).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No TBD/FIXME/XXX debt markers in phase-modified files; "no-key fallback" returns are intentional resolvable Features, not stubs; empty `return {}` in `_flow_risk_index` is honest graceful degradation for a down graph | ℹ Info | None — all "empty returns" are honest degradation paths, never silent stubs that flow to fabricated success |

Note: the no-vacuous gate, selector gate, and the honest per-Then UI indicators explicitly REJECT fabricated-green patterns — the codebase actively guards against the stub class this verifier hunts for.

### Human Verification Required

The deterministic contract (all 5 SCs' keyless mechanics) is fully proven. Three Manual-Only items remain — expected and NOT failures (provider keys empty + live stack required, same convention as Phases 4-5):

1. **Live generate → review → approve → codegen → stabilize → seeded-bug** — set provider keys, explore SauceDemo under graph_mode, generate scenarios, approve in the UI, generate the Playwright tree, run N-run stability vs 8080, then vs saucedemo-bug (8081) and confirm FAILURE.
2. **Graph-marked deterministic tests under graph_mode** — bring up neo4j + saucedemo + saucedemo-bug; run the 44 deselected graph tests (assertion-gate-graph, codegen full-tree, planted-spec stability/seeded-bug). Stop neo4j before the run phase (OOM sequencing).
3. **Memory fit under 3GB** — `docker stats` during the seeded-bug harness with the documented sequencing.

### Gaps Summary

No gaps. All five Success Criteria are observably true in the codebase, independently confirmed by re-running the deterministic suite (286 passed, 44 deselected) and reading the three novel mechanisms line-by-line:

1. **No-vacuous Then→KG gate** — pure read-only (execute_read count-existence only, zero write-Cypher), edge_type validated against the kg/schema constant allow-list BEFORE Cypher construction (injection-safe; no query runs for unknown-kind/disallowed-edge, asserted via fake-driver call log), all 5 vacuous classes rejected, re-run on edit AND approve.
2. **Freehand-selector AST gate** — genuinely AST-based (NodeVisitor over selector-sink Calls; regex is only a constant-string fallback), rejects spec/step literals, allows page-object literals only while separately asserting each is repo-traceable; locators pulled from the Element Repository by key.
3. **N-run + seeded-bug harness** — reuses the Phase-3 subprocess runner verbatim (no in-process pytest), N default 3 accept-iff-all-green, SEED_BUG build-arg (default byte-identical) + profile-gated saucedemo-bug on port 8081, accept_spec = green-vs-std AND red-vs-bug, proven by a planted template-rendered spec with no keys.

Zero new packages (no gherkin-official 40.x pin), zero new frontend shadcn/deps (native textarea), migration 0006 chains linearly after 0005 with `alembic upgrade head` reachable, codegen reads approved-only, routers auth-gated.

Status is **human_needed** (not passed) strictly because Manual-Only live-stack/keyed walk-throughs remain — the deterministic phase contract itself PASSES.

---

_Verified: 2026-06-20T18:30:00Z_
_Verifier: Claude (gsd-verifier)_
