# Phase 6: BDD & Playwright Generation - Research

**Researched:** 2026-06-20
**Domain:** Deterministic test-artifact generation (Gherkin + Playwright), KG-grounded quality gates, stability/breakage-detection harness
**Confidence:** HIGH (all novel mechanisms designed against the live codebase + locked stack; live-LLM half is Manual-Only by project convention)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Generated scenarios persist as Postgres `scenarios` rows (linked to flow/run) with a status lifecycle (draft → approved / rejected) + edited Gherkin content + timestamps. The review queue lists drafts; codegen reads ONLY status=approved. (Postgres, not Neo4j.)
- **D-02:** Edit-in-place — reviewer can edit a scenario's Gherkin in the UI and approve; saving RE-RUNS the syntax + no-vacuous-assertion gates so an edited scenario cannot bypass quality.
- **D-03:** STRUCTURED no-vacuous-assertion gate — generation emits each Then step annotated with the KG node/edge it asserts (page state / element / Creates-Updates-Deletes outcome). The gate DETERMINISTICALLY verifies EVERY Then resolves to an existing assertion in the graph; any Then with no graph-backed outcome is rejected as vacuous. NOT LLM judgment, NOT heuristic text-match.
- **D-04:** Gates enforce at generation AND on edit/approve — gherkin 29.x syntax lint (`from gherkin.parser import Parser`) + the assertion gate run at generation AND again on edit-save/approve. Deterministic, unit-testable on fixtures.
- **D-05:** EVERY locator comes from the Phase-5 Element Repository (by element key → locator chain); the LLM/template fills ONLY non-locator slots. A STATIC gate scans generated specs/pages and REJECTS any raw selector literal not sourced from the repo. Deterministic, unit-testable.
- **D-06:** Full Playwright project structure — Jinja2-templated page objects (from KG pages), specs (from approved scenarios), fixtures/conftest, utils, data models (from scenario-outline Examples), reports dir — the tests/pages/fixtures/utils/data/reports layout, under a TARGET/run-scoped path in the gitignored workspaces/ tree. Jinja2 owns structure; LLM fills narrow slots.
- **D (GEN-01):** Scenario OUTLINES with data-driven Examples tables; Examples data derives from the KG (BusinessEntity / form fields / validation rules from Phase 5) — research to specify the derivation.
- **D-07:** N-consecutive-run stability — reuse the Phase-3 subprocess runner to execute a generated spec N times; accept ONLY if all N pass (flaky → rejected). N env-configurable, default 3.
- **D-08:** A DEDICATED seeded-bug SauceDemo build (second image/compose profile with a deliberate injected defect) is the "seeded-bug build". Accepted tests run against it and MUST FAIL. Harness mechanics deterministically testable with a PLANTED template-rendered spec (no keys); full live generate→stabilize→bug-detect is Manual-Only.

### Claude's Discretion / for research
- The structured Then→KG-reference schema (D-03): emission shape + resolution check (THE novel gate).
- Examples-table data derivation from the KG.
- Page-object template structure + naming; approved-scenario→spec mapping; **pytest-bdd step-defs vs plain pytest-playwright specs** (reconcile with Phase-3's plain-spec choice + the pytest-bdd dependency).
- Seeded-bug build mechanism + N-run/bug-build harness wiring; SauceDemo seeded-defect specifics.
- Regenerate-vs-approved reconciliation — keep minimal this phase (stale-mark at most).

### Deferred Ideas (OUT OF SCOPE)
- Execution ENGINE (suite tiers, RabbitMQ workers, per-step artifacts, live run view) → Phase 7. This phase reuses the Phase-3 subprocess runner for stability only.
- Healing of generated tests when locators drift → Phase 8.
- Regenerate-vs-approved deep reconciliation → minimal (stale-mark at most) this phase.
- Scenario↔flow↔element graph visualization → out of scope (tabular).
- LLM-based risk/quality scoring of scenarios → rejected; gates are deterministic.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| GEN-01 | Generate BDD features/scenarios incl. scenario OUTLINES + data-driven Examples from flows | §Scenario Generation + Outlines; Examples derived from KG BusinessEntity/Form/validation (kg/reader + kg/schema.VERB_ENTITY_MAP) |
| GEN-02 | Approve/edit review queue; only approved feed codegen | §Review Queue Model — Postgres `scenarios` table + migration 0006 + auth-gated review router; codegen reads status=approved only |
| GEN-03 | Syntax lint gate + every Then asserts a KG-recorded outcome (no vacuous assertions) | §Structured Then→KG-reference Gate — kg_ref schema + deterministic Neo4j existence resolution; gherkin 29.x lint reused from Phase 3 |
| GEN-04 | Playwright page objects/specs/fixtures/utils/data in tests/pages/fixtures/utils/data/reports | §Element-Repository Codegen — Jinja2 template set + workspaces tree |
| GEN-05 | Locators ONLY from Element Repository (never freehand); N-run stability + seeded-bug must fail | §Freehand-Selector Static Gate + §N-run Stability & Seeded-Bug Harness |
</phase_requirements>

## Summary

Phase 6 is **deterministic generation engineering**, not a research-into-unknown-libraries phase. Every dependency is already installed and proven (pytest-bdd 8.1, gherkin-official 29.0.0 transitive, jinja2 3.1, playwright 1.60, pytest-playwright 0.8). The work is to **upgrade the Phase-3 single-scenario tracer seam** (`generation.py` + `test_login.py.j2` + the subprocess runner) into the real thing, and to design three novel deterministic mechanisms that have no canonical reference: (1) the structured **Then→KG-reference** no-vacuous-assertion gate, (2) the **Element-Repository-sourced codegen + freehand-selector static gate**, and (3) the **N-run stability + seeded-bug acceptance harness**. The headline architectural principle carried from every prior phase holds: **the LLM never emits structure or selectors** — Jinja2 owns structure, the Element Repository owns selectors, and the LLM fills only narrow semantic slots through the metered gateway, with a deterministic no-key fallback so all gates/harnesses are provable WITHOUT provider keys.

The single biggest design decision is **pytest-bdd step-defs vs. plain pytest-playwright specs**. Recommendation: **generate pytest-bdd step-definition specs bound to the approved `.feature` file** (not plain pytest-playwright). Rationale below — in short, GEN-01 makes Gherkin a first-class deliverable the user owns and edits, GEN-03 ties each `Then` to a KG assertion (a 1:1 mapping to a `@then` step is the natural home for that assertion), pytest-bdd 8.1 is already a locked dependency providing Examples-table parametrization for free (GEN-01 outlines), and pytest-bdd runs inside the SAME `uv run pytest` subprocess the Phase-3 runner already uses with the SAME pytest-playwright `page` fixture — so the runner, the N-run harness, and the seeded-bug harness need zero new execution machinery. Phase 3's plain-spec choice was explicit tracer pragmatism ("RESEARCH Open Q1: tracer favors the plain spec") and is the thing this phase exists to upgrade.

**Primary recommendation:** Build four dependency-ordered slices (scenario+gates+model → review queue+UI → Element-Repo codegen+freehand gate → N-run+seeded-bug harness). Emit each `Then`'s KG reference as a **sidecar JSON mapping** persisted on the `scenarios` row (NOT a `.feature` comment) so the gate is a pure Neo4j existence check independent of Gherkin text parsing, and so edit-in-place re-validation has a stable structured object to check. Generate pytest-bdd specs. Reuse the Phase-3 subprocess runner verbatim for N-run and the seeded-bug run. Add ZERO new Python/JS packages; the seeded-bug build is compose infra (a build-arg on the existing SauceDemo Dockerfile), not a package.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Scenario (Gherkin) generation | API / Backend (generation service via gateway) | — | LLM call must route through the metered Phase-2 gateway (D-07); pure backend |
| Gherkin syntax lint | API / Backend (pure fn) | — | `gherkin.parser.Parser` — deterministic, no I/O; reused from Phase 3 |
| Structured no-vacuous gate | API / Backend (reads Neo4j) | Database (Neo4j) | Resolves each kg_ref against the graph via read-only Cypher (kg/reader twin) |
| Review queue state | Database (Postgres) | API (router) | Relational status lifecycle — D-01 explicitly Postgres, not Neo4j |
| Review queue UI | Frontend Server (Next SSR) + Browser | API | Authenticated dashboard pages reusing the locked design system |
| Page-object/spec codegen | API / Backend (Jinja2) | Database (Neo4j read for locators) | Jinja2 owns structure; locators pulled from Element Repository by key |
| Freehand-selector static gate | API / Backend (pure AST/regex scan) | — | Scans generated `.py` source text — deterministic, no runtime |
| N-run stability | API / Backend (subprocess runner) | — | Reuses Phase-3 `asyncio.create_subprocess_exec` runner N times |
| Seeded-bug target | CDN / Static (nginx) + Infra (compose) | — | A second SauceDemo nginx image with an injected DOM defect; infra, not code |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest-bdd | 8.1.* | Bind generated `.feature` files to generated step-defs; Examples→parametrize | LOCKED in CLAUDE.md + already installed [VERIFIED: pyproject.toml]; runs inside pytest so it inherits the existing subprocess runner + pytest-playwright fixtures + xdist |
| gherkin-official | 29.0.0 (TRANSITIVE via pytest-bdd) | Parse/lint generated Gherkin BEFORE persist (`from gherkin.parser import Parser`) | The SAME parser pytest-bdd uses; pinning 40.x is INCOMPATIBLE (pytest-bdd 8.1 hard-pins `>=29,<30`) [VERIFIED: uv.lock = 29.0.0] |
| jinja2 | 3.1.* | Own ALL generated-code structure (pages/specs/fixtures/utils/data) | LOCKED + installed [VERIFIED: pyproject.toml]; the Phase-3 skeleton pattern, scaled |
| playwright (Python) | 1.60.* | Generated spec runtime (sync API inside pytest-bdd steps) | LOCKED + baked into the api image (`playwright install --with-deps chromium`) [VERIFIED: 03-02 summary] |
| pytest-playwright | 0.8.* | `page`/`context` fixtures consumed by generated step-defs | LOCKED + installed [VERIFIED: pyproject.toml] |

### Supporting (already present — no install)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| SQLAlchemy / asyncpg / Alembic | 2.0 / 0.31 / 1.18 | `scenarios` table + migration 0006 | The review queue persistence (D-01) |
| neo4j (driver) | 6.2 | Read Element Repository + resolve kg_refs | Codegen locator source + the no-vacuous gate |
| @tanstack/react-query, zod, shadcn/ui | (vendored) | Review-queue UI (table, textarea, dialog, badge) | D-02 review pages — zero new frontend deps (Phase-5 pattern) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pytest-bdd step-defs | plain pytest-playwright specs (Phase-3 choice) | Plain specs lose the Gherkin↔code binding GEN-01/GEN-03 need; the `.feature` becomes a dead artifact. See decision below — REJECTED for the real phase. |
| Sidecar JSON kg_ref mapping | `.feature` step comments / docstrings | Comments are lost on gherkin parse + fragile to edits; the gate would re-parse free text. Sidecar JSON on the `scenarios` row is structured + survives edit-in-place. RECOMMENDED. |
| Build-arg seeded-bug image | `sed`-mutated copy / separate repo | A build-arg toggling one nginx substitution on the EXISTING Dockerfile is minimal + reproducible; avoids a second source tree. RECOMMENDED. |

**Installation:**
```bash
# NONE. All packages already pinned + installed.
# Verify (Phase-6 entry check):
cd apps/api && python -c "import importlib.metadata as m; print('pytest-bdd', m.version('pytest-bdd')); print('gherkin-official', m.version('gherkin-official')); print('jinja2', m.version('jinja2'))"
# Expect: pytest-bdd 8.1.x ; gherkin-official 29.0.0 ; jinja2 3.1.x
```

## Package Legitimacy Audit

> Phase 6 installs **ZERO new packages**. Every dependency is already pinned in `apps/api/pyproject.toml` and locked in `uv.lock`, vetted in Phases 1–5.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| pytest-bdd | PyPI | 10+ yrs | high | github.com/pytest-dev/pytest-bdd | n/a (already vetted P3) | Approved — no install |
| gherkin-official | PyPI | mature | high | github.com/cucumber/gherkin | n/a (transitive) | Approved — no install (29.0.0) |
| jinja2 | PyPI | 15+ yrs | very high | github.com/pallets/jinja | n/a (already vetted P3) | Approved — no install |
| playwright | PyPI | mature | very high | github.com/microsoft/playwright-python | n/a (already vetted P3) | Approved — no install |
| pytest-playwright | PyPI | mature | high | github.com/microsoft/playwright-pytest | n/a (already vetted P3) | Approved — no install |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none
**Genuinely new packages [ASSUMED]:** none. If a planner later proposes any new package, gate it behind `checkpoint:human-verify`. The seeded-bug build is **compose infrastructure** (a build-arg on the existing `infra/targets/saucedemo/Dockerfile`), NOT a package.

## Architecture Patterns

### System Architecture Diagram

```
                         POST /api/generate-bdd  (auth-gated, run_id)
                                    │
                                    ▼
   Neo4j (Element Repo, flows,   ┌──────────────────────────────────────────┐
   BusinessEntity, Forms) ──────▶│  generation.generate_scenarios(run_id)     │
   via kg/reader (read-only)     │   1. read flows + risk (kg/reader.flows)   │
                                 │   2. read BusinessEntity/Form/validation   │
                                 │   3. gateway.complete(generate.bdd) ───────┼─▶ Phase-2 LLM gateway
                                 │      → Gherkin + per-Then kg_ref JSON       │   (metered, no-key fallback)
                                 │   4. gherkin Parser().parse()  [LINT GATE] │
                                 │   5. resolve_kg_refs() [NO-VACUOUS GATE] ──┼─▶ Neo4j existence Cypher
                                 │   6. derive Examples from KG (outlines)    │
                                 └───────────────┬────────────────────────────┘
                                                 ▼  (valid draft only)
                                  Postgres  scenarios row  (status=draft,
                                  gherkin_text, then_refs JSON, flow_id, run_id)
                                                 │
                  ┌──────────────────────────────┴───────────────────┐
                  ▼ GET /api/scenarios (list drafts)                  │ edit-save
        Review Queue UI (Next) ── approve/reject/edit ──▶ POST /api/scenarios/{id}/edit
                  │  approve                                   (re-run LINT + NO-VACUOUS gates)
                  ▼
        scenarios.status = approved  ──────────────────────────────────────┐
                                                                            ▼
                              POST /api/generate-scripts (reads status=approved ONLY)
                                                 │
                                                 ▼
   Neo4j Element Repo ───locators by key──▶ ┌────────────────────────────────────┐
   (kg/reader.element_repository)          │ codegen (Jinja2 templates)           │
                                           │  pages/  ← KG pages + repo locators  │
                                           │  steps/  ← @given/@when/@then bound   │
                                           │  features/ ← approved .feature        │
                                           │  fixtures/conftest/utils/data/reports │
                                           │  → FREEHAND-SELECTOR STATIC GATE  ────┼─▶ reject raw literals
                                           └───────────────┬──────────────────────┘
                                                           ▼ workspaces/<run_id>/<target>/
                                  ┌────────────────────────┴───────────────────────┐
                                  ▼ run N times (all green)        ▼ run vs bug-build (must FAIL)
                    subprocess runner (Phase-3, reused)   saucedemo-bug (compose, injected defect)
                                  │                                 │
                                  └─────────── ACCEPT only if: N green vs std AND fail vs bug ──┘
```

File-to-implementation mapping is in the Component Responsibilities table below, NOT the diagram.

### Recommended Project Structure (new + upgraded files)
```
apps/api/app/
├── services/
│   ├── generation.py                 # UPGRADE: generate_scenarios (outlines+Examples), kg_ref emission
│   ├── gates/
│   │   ├── gherkin_lint.py           # move/extend validate_gherkin (Parser) — shared by gen + edit
│   │   ├── assertion_gate.py         # NOVEL: resolve_then_refs against Neo4j (no-vacuous)
│   │   └── selector_gate.py          # NOVEL: static scan of generated .py for raw selectors
│   ├── codegen/
│   │   ├── project.py                # build the pages/steps/features/... tree from approved scenarios
│   │   ├── examples.py               # derive Examples tables from KG BusinessEntity/Form/validation
│   │   └── locators.py               # pull locator chain by element key -> page-object attrs
│   ├── stability.py                  # NOVEL: N-run harness + seeded-bug run (wraps execution runner)
│   └── scenario_service.py           # Postgres CRUD + status lifecycle for the review queue
├── models/scenario.py                # NEW: Scenario SQLAlchemy model
├── routers/scenarios.py              # NEW: auth-gated review router (list/get/edit/approve/reject)
├── schemas/scenario.py               # NEW: Pydantic request/response
├── templates/
│   ├── pages/page_object.py.j2       # KG-page -> page object (locators = repo attrs)
│   ├── steps/steps.py.j2             # @given/@when/@then bound to the .feature
│   ├── conftest.py.j2 / fixtures.py.j2 / utils.py.j2 / data_model.py.j2
│   └── (test_login.py.j2 retained for the Phase-3 tracer / planted-spec proof)
└── alembic/versions/0006_scenarios.py
apps/web/app/(dashboard)/scenarios/   # NEW review-queue pages (list + edit/approve)
infra/targets/saucedemo/Dockerfile    # UPGRADE: SEED_BUG build-arg toggles one injected defect
infra/docker-compose.yml              # ADD saucedemo-bug service (profile-gated, distinct port)
```

### Pattern 1: Structured Then→KG-reference (THE novel gate, GEN-03 / D-03)
See the dedicated section "## Novel Mechanism 1: Structured Then→KG-reference Gate" below.

### Pattern 2: Jinja2-owns-structure / LLM-fills-slots (scaled)
**What:** Exactly the Phase-3 pattern (`templates/test_login.py.j2`) extended to a multi-file tree. The LLM never emits a file. The template emits the file; the LLM fills only: scenario prose, step labels, and Example *cell values* (which are themselves re-validated against the KG). Selectors are NEVER slots — they are template lookups against the Element Repository.
**Source:** `apps/api/app/services/generation.py:44-52` (OBSERVED_SELECTORS hard-coded), `templates/test_login.py.j2:12-14`.

### Anti-Patterns to Avoid
- **LLM emits a whole spec file** — Phase-3 Pitfall 5; the template owns structure. A whole-file LLM emission would defeat the freehand-selector gate.
- **Direct provider call** — D-07; ALL generation routes `llm_gateway.complete(operation_type=..., run_id=...)`. Grep-asserted in Phase 3 (`generation.py` contains no `init_chat_model`).
- **In-process pytest for runs** — Phase-3 Pitfall 3; sync Playwright inside the asyncio API deadlocks. ALWAYS subprocess (`asyncio.create_subprocess_exec`, argv list, no shell).
- **kg_ref as a free-text `.feature` comment** — lost on parse, fragile to edit. Use the sidecar JSON on the `scenarios` row.
- **gherkin-official 40.x direct pin** — INCOMPATIBLE with pytest-bdd 8.1 (`>=29,<30`). Use the transitive 29.0.0 (`from gherkin.parser import Parser`).
- **Writing KG from this phase** — Phase 6 is READ-ONLY against Neo4j (single writer is Phase-5 kg/writer). The single-write-path grep gate must stay green; all gate/codegen Cypher uses `execute_read`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Gherkin parsing/validation | A regex Gherkin validator | `gherkin.parser.Parser` (29.0.0) | Already the parser pytest-bdd executes; a regex validator drifts from what actually runs |
| Examples-table parametrization | Custom loop over Example rows in the runner | pytest-bdd Scenario Outline → auto-parametrize | pytest-bdd expands `Examples:` into pytest params natively |
| Python source scanning (selector gate) | Brittle line-by-line regex on whole files | `ast` module + targeted node inspection (with a regex fallback for string literals) | `ast.parse` already used in Phase 3; AST distinguishes a `page.locator("...")` call arg from a page-object attribute reference |
| Subprocess test run | A new runner | Phase-3 `execution.run_execution` shape | Already isolated, argv-list, no-shell, output-capped, finishes the run row |
| Seeded-bug target app | A hand-written broken HTML app | A build-arg on the EXISTING SauceDemo Dockerfile | One reproducible toggle; same nginx serve, distinct port |

**Key insight:** Everything in this phase that *looks* like it needs an LLM (validation, breakage detection, locator selection) is deliberately deterministic. The LLM is confined to generating *prose Gherkin* and is fully replaceable by the no-key fallback for testing.

## Runtime State Inventory

> Phase 6 is primarily additive (new tables, new services, new compose service). The one rename/upgrade is the Phase-3 generation seam.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Postgres: NEW `scenarios` table (migration 0006 chains after 0005). Neo4j: READ-ONLY (no writes). | Alembic migration 0006; codegen/gate reads only |
| Live service config | Compose: NEW `saucedemo-bug` service (profile-gated). The existing `saucedemo` service is unchanged. graph_mode helper must keep neo4j reachable for codegen (reads Element Repository). | Add compose service + build-arg; document graph_mode + bug-build memory in the plan |
| OS-registered state | None — no OS scheduler/service registration. | None — verified: only Docker Compose services + uvicorn. |
| Secrets/env vars | NEW env: `STABILITY_RUNS` (default 3), `SEEDED_BUG_BASE_URL` (the bug-build URL). Provider keys unchanged (empty → Manual-Only). No new secrets. | Add to compose api env + .env.example (Phase-2 pattern: compose enumerates env explicitly) |
| Build artifacts | The Phase-3 `test_login.py.j2` template is RETAINED (used by the deterministic execute proof + the planted-spec stability proof). New templates are additive. `workspaces/<run_id>/` gains a per-target subtree. | Keep test_login.py.j2; add codegen templates; workspaces stays gitignored |

**Nothing found in category OS-registered state:** None — verified by inspecting `infra/` (only `docker-compose.yml` + `scripts/` helpers; no systemd/Task Scheduler).

## Novel Mechanism 1: Structured Then→KG-reference Gate (GEN-03 / D-03)

This is THE novel deterministic trust mechanism. Designed below end-to-end.

### The kg_ref shape (what generation emits per Then)
Emit a **sidecar JSON array** (persisted on the `scenarios.then_refs` column), one entry per `Then` step, NOT a `.feature` comment. Each entry:

```jsonc
{
  "then_text": "the cart badge shows 1 item",   // the literal Then step text (for display/trace)
  "kind": "edge" | "element" | "page",            // which KG existence check to run
  "ref": {
    // kind=edge  -> a Creates/Updates/Deletes outcome edge on a BusinessEntity:
    "edge_type": "Updates",                        // one of Creates|Updates|Deletes (kg/schema constants)
    "entity": "Cart"                               // BusinessEntity.name (kg/schema VERB_ENTITY_MAP target)
    // kind=element -> an element that must exist in the Element Repository:
    // "element_key": "fp-inventory#button:Add to cart"
    // kind=page    -> a page state the Then asserts you reach:
    // "page_fingerprint": "fp-inventory"  (or "page_url": "...")
  }
}
```

**Why sidecar JSON, not a `.feature` annotation:** (a) gherkin-official drops comments on parse — a `# kg:` comment cannot be recovered structurally; (b) edit-in-place (D-02) must re-validate, and a structured object on the row is stable across Gherkin text edits; (c) the gate becomes a pure function `resolve_then_refs(then_refs, driver) -> list[Unresolved]` with no Gherkin re-parsing. The mapping is generated alongside the Gherkin in the SAME gateway call (ask the model for `{gherkin, then_refs}` JSON; the no-key fallback emits a minimal valid pair).

### The resolution algorithm (deterministic, the gate)
```
def resolve_then_refs(then_refs, driver) -> list[str]:   # returns list of vacuous Then texts
    unresolved = []
    for r in then_refs:
        if r.kind == "edge":
            ok = _edge_exists(driver, r.ref.edge_type, r.ref.entity)
        elif r.kind == "element":
            ok = _element_exists(driver, r.ref.element_key)
        elif r.kind == "page":
            ok = _page_exists(driver, r.ref.page_fingerprint or r.ref.page_url)
        else:
            ok = False                      # unknown kind == vacuous
        if not ok:
            unresolved.append(r.then_text)
    return unresolved   # EMPTY == every Then is graph-backed == passes the gate
```
A scenario passes iff `resolve_then_refs(...) == []` AND it has **at least one** `Then` with a ref (a scenario with zero Thens, or a Then with no ref, is vacuous by definition).

### Concrete Cypher existence checks (read-only, parameterized — kg/reader twin)
These mirror the existing `kg/reader.py` style (`execute_read`, `LIMIT`, parameterized, labels/edge-types from `kg/schema` constants — NEVER interpolated). Edge-type cannot be parameterized in Cypher, so it is validated against the `kg/schema` allow-list THEN injected from the constant (not from LLM text):

```cypher
-- kind=edge (Creates/Updates/Deletes outcome exists on the named BusinessEntity):
MATCH (:`{Page|Form|Workflow}`)-[r:`<EDGE_TYPE from schema allow-list>`]->(be:BusinessEntity {name:$entity})
RETURN count(r) > 0 AS exists

-- kind=element (the element is in the Element Repository):
MATCH (:Page)-[:HAS_ELEMENT]->(e:Element {key:$element_key})
RETURN count(e) > 0 AS exists

-- kind=page (the page state exists):
MATCH (p:Page) WHERE p.fingerprint = $fp OR p.url = $url
RETURN count(p) > 0 AS exists
```
`edge_type` is checked `in {CREATES, UPDATES, DELETES}` (kg/schema) before the query is built; an unrecognized edge_type is treated as vacuous (no Cypher run). This keeps the single-write-path grep gate green (all `execute_read`) and prevents injection.

### What counts as "vacuous"
- A `Then` with **no kg_ref** at all → vacuous.
- A `Then` whose kg_ref **does not resolve** to an existing node/edge in Neo4j → vacuous.
- A `Then` with an **unknown `kind`** or an edge_type outside the schema allow-list → vacuous.
- A scenario with **zero `Then` steps** → vacuous (nothing asserted).
- Pass condition: every `Then` has a ref AND every ref resolves.

### Deterministic + unit-testable on a fixture KG
- **Unit (no keys, mocked driver):** feed `then_refs` + a fake driver returning `exists=true/false` per query; assert `resolve_then_refs` returns exactly the unresolved Then texts. Table-test all four vacuous cases. This is the same fake-driver injection pattern `kg/reader` already supports (`driver` kwarg).
- **Functional (graph_mode, seeded graph):** seed the SauceDemo fixture graph (the Phase-5 `kg/ground_truth/saucedemo.json` fixture is available), generate refs that DO and DON'T resolve, assert pass/reject against the live Neo4j.

## Novel Mechanism 2: Scenario Generation + Outlines + Examples derivation (GEN-01)

### Gateway prompt shape
One gateway call per flow (`operation_type="generate.bdd"`, the explore/run `run_id`), grounded ONLY in deterministic KG-derived context (never raw DOM — the Phase-3/Phase-5 untrusted-fence pattern). Inputs: the flow steps + risk (kg/reader.flows / build_flows), the pages/elements on the flow (kg/reader.page_detail / element_repository), and the BusinessEntity/Form/validation context. Output requested as a JSON object `{gherkin: "<Feature text>", then_refs: [...]}` so the kg_ref mapping is emitted in lockstep. Temperature 0, small max_tokens (the model writes prose, not files). **No-key fallback:** a deterministic minimal valid `Feature`/`Scenario` (one `Given`/`When`/`Then`) with a single resolvable kg_ref derived from the flow's terminal page — so generation, the lint gate, and the no-vacuous gate are all provable with NO provider key (exactly the Phase-5 `categorize_flow` no-key degrade pattern).

### Examples-table data derivation from the KG (the outline data)
Scenario Outlines need an `Examples:` table; the data is DERIVED deterministically from the KG, NOT invented by the LLM:
- **Form fields → columns.** `kg/reader.page_detail` returns `forms` (Form nodes via HAS_FORM). Each form field becomes an Example column (`<username>`, `<password>`, ...).
- **BusinessEntity values → rows.** `kg/schema.VERB_ENTITY_MAP` maps action labels to BusinessEntity {name, kind, edge} (Cart/Order/Product). Entity instances + the SauceDemo public user matrix (standard_user, locked_out_user, problem_user, performance_glitch_user — well-known public demo accounts) seed positive/negative rows.
- **Validation rules → negative rows.** Phase-5 captured form validation rules (EXPL-04 / KG). A required/empty/invalid rule becomes a negative Example row whose `Then` asserts an *error page-state* (a `kind=page` ref to the validation/error state), not a success.
- Derivation lives in `codegen/examples.py` as a pure function over the KG read structures → unit-testable with a fixture graph, no keys.

### gherkin 29.x parse-validate before persisting a draft
Reuse `generation.validate_gherkin` (now `gates/gherkin_lint.py`): `Parser().parse(text)` BEFORE the row write; malformed → no draft (Phase-3 T-03-12, verbatim). Then run the no-vacuous gate. Only a scenario passing BOTH becomes a `draft` row.

## Novel Mechanism 3: Element-Repository codegen + freehand-selector gate (GEN-04 / GEN-05a)

### Page objects from KG pages with repo locators
`codegen/locators.py` reads `kg/reader.element_repository()` (already returns, per element: `key`, `role`, `label`, deserialized `chain` = prioritized locator chain [data-testid → aria-label → role → text → xpath], `history`, `page_fp`, `page_url`). For each KG page, the Jinja2 `pages/page_object.py.j2` emits a Page Object class whose attributes are the **top-priority locator from each element's chain**, rendered via `tojson` into a `page.locator(...)`/`get_by_*` call. The element KEY and the resolved locator are TEMPLATE inputs sourced from the repo — the LLM never sees or emits them. This is the Phase-3 `OBSERVED_SELECTORS` mechanism generalized from a hard-coded tuple to a KG query.

### pytest-bdd spec wiring (the reconciled decision — see "## Key Decision" below)
`steps/steps.py.j2` emits `@given/@when/@then` step-defs bound to the approved `.feature` via `scenarios("...feature")`. Each `@then` step calls a Page Object assertion method (which uses a repo locator) — so the GEN-03 Then→KG mapping has a 1:1 home in code. Examples columns arrive as step parameters via pytest-bdd's outline parametrization.

### The freehand-selector STATIC gate (deterministic, GEN-05a)
Scan every generated `.py` (specs + steps; page objects are the ALLOWED locator home) with `ast` (Phase-3 already `ast.parse`s rendered output):
- **Detection rule:** In spec/step files, flag any **string-literal argument** to a selector sink — `page.locator(...)`, `page.fill/click/...(<css-string>)`, `get_by_role/get_by_text/get_by_test_id/get_by_label/get_by_placeholder(...)`, or any string that matches a CSS/XPath shape (`^#`, `^\.`, `^//`, `[attr=`). **Allow:** references to Page Object attributes (`self.login_button`, `page_obj.add_to_cart`) and locators returned by the page-object layer. **Reject:** an inline literal selector in a spec/step → `SelectorGateError` (no file accepted).
- **Page objects** are the single sanctioned place a literal locator appears, and even there it must be traceable to a repo element (the template sourced it, so by construction it is; a unit test asserts every page-object literal equals a repo chain entry).
- **Implementation:** AST walk for `Call` nodes whose `func` is an attribute in the selector-sink set and whose first arg is a `Constant` str → violation, UNLESS the file is a page-object module. Pair with a regex fallback for raw CSS/XPath string constants anywhere in spec/step files. Pure, unit-testable on rendered fixtures (no keys).

## Novel Mechanism 4: N-run stability + seeded-bug harness (GEN-05b / D-07 / D-08)

### N-run stability (reuse the Phase-3 subprocess runner)
`stability.py` calls the Phase-3 `execution.run_execution`-shaped subprocess (`uv run pytest <spec> -q`, argv list, no shell, output-capped) **N times** (default `STABILITY_RUNS=3`, env-configurable). Accept iff ALL N return `passed` (exit 0). Any non-green (incl. flake) → reject. Each run is fully isolated (fresh subprocess + fresh browser context via pytest-playwright). The harness records per-run status for the trace.

### The seeded-bug SauceDemo build
- **Mechanism:** add a `SEED_BUG` build-arg to the EXISTING `infra/targets/saucedemo/Dockerfile`. When `SEED_BUG=1`, a final nginx layer applies ONE deterministic DOM mutation to the built static files (e.g. `sed -i 's/id="login-button"/id="login-button-BROKEN"/'` on the served HTML/JS, or rename `.inventory_list`). This is a one-line reproducible defect on the same nginx serve — no second source tree, no separate repo.
- **Compose:** add a `saucedemo-bug` service building `./targets/saucedemo` with `args: {SEED_BUG: "1"}`, a DISTINCT service name + host port (e.g. `8081:80`), profile-gated (e.g. `profiles: [bugbuild]`) so it is OFF by default and only up during the acceptance harness.
- **Pointing accepted tests at it:** the harness re-runs the SAME accepted spec with `SEEDED_BUG_BASE_URL` (e.g. `http://saucedemo-bug:80` in-cluster) overriding the base URL, and asserts the run **FAILS** (the renamed id makes the login/assert step fail). ACCEPT the test only if: N green vs standard SauceDemo AND red vs the bug build (proves real-breakage detection — GEN-05/QUAL-02 spirit; full QUAL-02 healing metric is Phase 8).

### Proving the WHOLE harness deterministically WITHOUT keys (the planted spec)
Same trick as Phase-3's deterministic execute proof: render the REAL codegen templates with FIXED KG-sourced slots (a PLANTED spec — no gateway, no keys) and run it through the harness. Assert: planted spec passes N times vs standard SauceDemo, and FAILS vs `saucedemo-bug`. This proves the run-N-times + bug-build + pass-then-fail mechanics with zero LLM spend. The full live generate→review→codegen→stabilize chain is Manual-Only (needs keys), consistent with Phases 4–5.

### Memory bound (CRITICAL — flag for the plan)
Host 5.7 GB / WSL cap 3 GB. The acceptance harness wants: postgres+redis+api + **neo4j** (codegen reads the Element Repository) + **saucedemo** + **saucedemo-bug** + a **Chromium subprocess**. From STATE.md: postgres+redis+api+neo4j+saucedemo ≈ 2.9 GB already near the cap; adding saucedemo-bug (128 m) + Chromium (~300–500 m transient) **risks OOM**.
- **Mitigation (recommended):** Do NOT run standard + bug builds concurrently with neo4j up. Sequence the harness: (1) with graph_mode (neo4j up, web stopped) do codegen reading the Element Repository and WRITE the spec; (2) stop neo4j, then run the N-run stability vs `saucedemo` and the single bug run vs `saucedemo-bug` (the spec is already written; running it needs no graph). saucedemo (128 m) + saucedemo-bug (128 m) + Chromium fit comfortably without neo4j. The planted-spec proof needs no neo4j at all. **The plan MUST bound this and prefer the sequenced approach; flag concurrent neo4j+both-targets+Chromium as an OOM risk.**

## Key Decision: pytest-bdd step-defs vs plain pytest-playwright specs

**RECOMMENDATION: generate pytest-bdd step-definition specs bound to the approved `.feature`.**

| Factor | pytest-bdd step-defs (RECOMMENDED) | plain pytest-playwright (Phase-3 tracer) |
|--------|-----------------------------------|------------------------------------------|
| GEN-01 (Gherkin is a deliverable the user owns/edits) | `.feature` is live + executed | `.feature` is a dead artifact |
| GEN-03 (each Then ↔ KG assertion) | 1:1 `@then` step ↔ kg_ref — natural | no per-Then code home |
| GEN-01 outlines/Examples | pytest-bdd auto-parametrizes `Examples:` | hand-rolled param loop |
| Dependency | pytest-bdd 8.1 ALREADY locked + installed | wastes the locked dep |
| Runner reuse | runs in the SAME `uv run pytest` subprocess + same `page` fixture | same |
| Phase-3 reconciliation | Phase 3 chose plain specs as explicit tracer pragmatism ("Open Q1: tracer favors the plain spec") — THIS phase is the upgrade | n/a |

**Why it's safe:** pytest-bdd executes inside pytest, so the Phase-3 subprocess runner, the N-run harness, the seeded-bug harness, and pytest-playwright's `page` fixture all work UNCHANGED — pytest-bdd is purely a test-collection layer over the same pytest invocation. The Phase-3 plain `test_login.py.j2` is RETAINED for the deterministic execute proof + the planted-spec stability proof (those don't need the Gherkin binding), so nothing regresses.


## Review Queue Model (GEN-02 / D-01 / D-02)

### Postgres `scenarios` schema (migration 0006, chains after 0005)
```python
# app/models/scenario.py  (SQLAlchemy 2.0 async, mirrors Run/Execution model style)
class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[int]            = mapped_column(primary_key=True)
    run_id: Mapped[str]        = mapped_column(index=True)        # threads explore->generate (Phase-3 convention)
    flow_id: Mapped[str]       = mapped_column(index=True)        # the source flow (kg/flows id)
    feature_name: Mapped[str]
    gherkin_text: Mapped[str]  = mapped_column(Text)             # the (possibly edited) Feature text
    then_refs: Mapped[dict]    = mapped_column(JSON)             # the sidecar Then->kg_ref mapping (Mechanism 1)
    status: Mapped[str]        = mapped_column(default="draft")  # draft | approved | rejected
    edited: Mapped[bool]       = mapped_column(default=False)    # set true on edit-in-place save
    stale: Mapped[bool]        = mapped_column(default=False)    # minimal regenerate reconciliation (deferred-deep)
    created_at / updated_at: Mapped[datetime]  (server_default / onupdate)
```
- `status` is a string enum (draft -> approved/rejected); a CHECK or app-level guard restricts values.
- `then_refs` is JSON (asyncpg/SQLAlchemy JSON) — the structured mapping the gate consumes; survives edit.
- `stale` is the MINIMAL regenerate-vs-approved reconciliation (mark stale when the underlying flow/graph changes; deep re-derivation is deferred per CONTEXT).
- Migration `0006_scenarios.py` sets `down_revision="0005"` (chain after 0005_explore_stop_reason).

### Review router (auth-gated, mirrors routers/kg.py + executions.py)
`APIRouter(prefix="/api", tags=["scenarios"], dependencies=[Depends(get_current_user)])`:
- `GET /scenarios?status=draft` — list (default drafts) for the queue.
- `GET /scenarios/{id}` — one scenario (gherkin + then_refs + status).
- `POST /scenarios/{id}/edit` — save edited gherkin_text (+ optionally then_refs); **RE-RUNS lint + no-vacuous gates** (D-02/D-04); on failure -> 422, no save; on success -> `edited=true`, stays `draft`.
- `POST /scenarios/{id}/approve` — re-run BOTH gates (defense in depth) then set `status=approved`; only approved feed codegen.
- `POST /scenarios/{id}/reject` — set `status=rejected`.
- **Codegen reads `status=approved` ONLY** (D-01) — `scenario_service.list_approved(run_id)` filters in the query.

### Review-queue UI (zero new frontend deps — Phase-5 pattern)
New authenticated pages under `apps/web/app/(dashboard)/scenarios/` reusing the locked design system (shadcn table/card/badge/textarea/dialog, @tanstack/react-query, zod-at-boundary). One sidebar nav item. A list view (drafts with status badges) + a detail/edit view (Gherkin textarea + the resolved/unresolved Then list + approve/reject/edit actions). Inline 422 surfacing when an edit fails the gate (mirror the Phase-5 error+Retry state).

## Common Pitfalls

### Pitfall 1: kg_ref as a Gherkin comment
**What goes wrong:** comments are discarded by `gherkin.parser`; the gate cannot recover them; edits break alignment.
**How to avoid:** sidecar JSON on the `scenarios.then_refs` column (Mechanism 1). Generate gherkin + then_refs in one gateway JSON response.
**Warning signs:** the gate re-parses `.feature` text to find assertions.

### Pitfall 2: edge_type Cypher injection
**What goes wrong:** Cypher relationship types cannot be parameterized; interpolating an LLM-supplied edge_type is an injection + a way to fabricate a "resolved" ref.
**How to avoid:** validate `edge_type in {CREATES,UPDATES,DELETES}` (kg/schema constants) BEFORE building the query; inject the constant, never the LLM string. Unknown edge_type -> vacuous.

### Pitfall 3: freehand-selector gate false-positives on page objects
**What goes wrong:** a naive regex flags the legitimate repo-sourced literal inside the page-object module and rejects valid codegen.
**How to avoid:** the gate ALLOWS literals in page-object modules (their literals are repo-traceable by construction + asserted by a unit test) and REJECTS literals only in spec/step modules. Distinguish by module path/role.

### Pitfall 4: OOM running both targets + neo4j + Chromium
**What goes wrong:** neo4j (1 g) + saucedemo + saucedemo-bug + Chromium + api breaches the 3 GB WSL cap -> OOM kill mid-harness.
**How to avoid:** sequence — codegen (needs neo4j) WRITES the spec under graph_mode; then STOP neo4j and run stability + bug-run (need no graph). Planted-spec proof needs no neo4j. (Mechanism 4 memory bound.)

### Pitfall 5: uvicorn --reload bouncing on workspace writes
**What goes wrong:** N-run + codegen write many files under the mounted `/app/workspaces`; the reload watcher restarts the server mid-harness (the exact Phase-3 03-04 Rule-3 bug).
**How to avoid:** already mitigated — `--reload-dir app` scopes the watcher (Phase-3 fix). Keep workspace writes outside `app/`. Verify it still holds with the larger codegen tree.

### Pitfall 6: gherkin-official 40.x temptation
**What goes wrong:** CLAUDE.md's stack table lists gherkin-official 40.x; a direct pin breaks pytest-bdd 8.1 (`>=29,<30`).
**How to avoid:** DO NOT pin gherkin-official. Use the transitive 29.0.0 (`from gherkin.parser import Parser`). (STATE.md memory `gherkin-pytest-bdd-conflict`; the CLAUDE.md correction is a tracked Deferred Item.)

## State of the Art

| Old Approach (Phase 3 tracer) | Current Approach (Phase 6) | When Changed | Impact |
|--------------|------------------|--------------|--------|
| One hard-coded `.feature` + plain pytest-playwright `test_login.py` | Outlines+Examples Gherkin + pytest-bdd step-defs bound to the `.feature` | Phase 6 | Gherkin becomes a live, owned, edited deliverable |
| Selectors hard-coded as a tuple (`OBSERVED_SELECTORS`) | Selectors pulled from the KG Element Repository by element key | Phase 6 | Generalizes from SauceDemo-only to any explored app |
| LLM fills a single scenario label | LLM fills prose + Example cells (re-validated vs KG); structure/selectors never LLM | Phase 6 | Same safety invariant, scaled |
| Single subprocess run | N-run stability + seeded-bug breakage detection | Phase 6 | Trust gate before a test is "accepted" |

**Deprecated/outdated:**
- The Phase-3 plain-spec choice for *deliverable* tests — retained ONLY for the deterministic execute/planted-spec proofs, superseded by pytest-bdd for real generated tests.

## MVP Slice Ordering (dependency-ordered, each demonstrable)

1. **Slice 1 — Scenario generation + gates + model (GEN-01, GEN-03).**
   `scenarios` table + migration 0006; `generate_scenarios` (outlines+Examples derivation from KG); gherkin lint gate (reused) + the structured Then->KG no-vacuous gate; no-key fallback. *Demo:* generate -> a `draft` row with gherkin + then_refs; malformed/vacuous -> no draft. Unit-tested on a fixture KG, no keys.
2. **Slice 2 — Review queue API + UI (GEN-02).**
   Review router (list/get/edit/approve/reject, auth-gated) with edit-in-place re-validation; the review-queue UI pages. *Demo:* edit a draft -> re-validated; approve -> status=approved; reject works; only approved are queryable for codegen.
3. **Slice 3 — Element-Repository codegen + freehand-selector gate (GEN-04, GEN-05a).**
   Jinja2 template set (pages/steps/features/conftest/fixtures/utils/data/reports); `codegen/locators.py` pulling repo locators by key; the static freehand-selector gate. *Demo:* approved scenario -> full project tree with repo-sourced locators; an injected inline literal -> gate rejects. Graph-marked functional + unit on rendered fixtures.
4. **Slice 4 — N-run stability + seeded-bug build + breakage detection (GEN-05b).**
   `stability.py` (N-run via the Phase-3 runner); the `SEED_BUG` build-arg + `saucedemo-bug` compose service; the planted-spec deterministic proof (passes N times vs std, fails vs bug). *Demo:* planted spec accepted (N green vs SauceDemo, red vs bug build) with zero keys; live generate->stabilize is Manual-Only.

## Validation Architecture

> nyquist_validation enabled (no `workflow.nyquist_validation:false` in config). Tests below are DETERMINISTIC + no-key unless marked.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.x + pytest-asyncio 1.4 (auto) + pytest-bdd 8.1 + pytest-playwright 0.8 |
| Config file | `apps/api/pyproject.toml` (markers: live_llm, e2e, graph, generated) |
| Quick run command | `cd apps/api && uv run pytest tests/unit/test_<module>.py -x -q` |
| Full suite command | `cd apps/api && uv run pytest -m "not live_llm and not e2e and not graph" -q` |

### Phase Requirements -> Test Map
| Req | Behavior | Type | Automated Command | Exists? |
|-----|----------|------|-------------------|---------|
| GEN-03 | gherkin lint rejects malformed | unit | `uv run pytest tests/unit/test_gherkin_lint.py -x` | Wave 0 (extend Phase-3 test) |
| GEN-03 | no-vacuous gate: unresolved Then rejected | unit (fake driver) | `uv run pytest tests/unit/test_assertion_gate.py -x` | Wave 0 |
| GEN-03 | no-vacuous gate resolves vs live graph | functional (graph) | `uv run pytest tests/functional/test_assertion_gate.py -m graph` | Wave 0 |
| GEN-01 | Examples derived from KG (forms/entities/validation) | unit (fixture KG) | `uv run pytest tests/unit/test_examples_derivation.py -x` | Wave 0 |
| GEN-01 | scenario generation no-key fallback = minimal valid+resolvable | unit (mocked gateway) | `uv run pytest tests/unit/test_generate_scenarios.py -x` | Wave 0 |
| GEN-02 | status transitions draft->approved/rejected; edit re-validates | functional | `uv run pytest tests/functional/test_scenarios_router.py` | Wave 0 |
| GEN-02 | codegen reads approved only; auth-gated (401) | functional | (same file) | Wave 0 |
| GEN-05a | freehand-selector gate rejects inline literal in spec/step, allows page-object | unit (rendered fixtures) | `uv run pytest tests/unit/test_selector_gate.py -x` | Wave 0 |
| GEN-04 | codegen pulls repo locators; full tree rendered + ast-parseable | functional (graph) | `uv run pytest tests/functional/test_codegen.py -m graph` | Wave 0 |
| GEN-05b | N-run harness accepts only all-green (planted spec) | functional (graph, planted) | `uv run pytest tests/functional/test_stability.py -m graph` | Wave 0 |
| GEN-05b | seeded-bug build: accepted spec FAILS vs bug build | functional (graph/bugbuild, planted) | `uv run pytest tests/functional/test_seeded_bug.py -m graph` | Wave 0 |
| GEN-01..05 | live generate->review->codegen->stabilize | live_llm/manual | `uv run pytest -m live_llm` (needs key) | Wave 0 (Manual-Only) |

### Sampling Rate
- **Per task commit:** the relevant `tests/unit/test_*.py -x -q` (zero spend).
- **Per wave merge:** `uv run pytest -m "not live_llm and not e2e and not graph" -q` (full default gate) + the graph-marked functional suite under graph_mode.
- **Phase gate:** full default suite green + graph functional green + the planted-spec stability/seeded-bug proof green before `/gsd:verify-work`. Live generate->stabilize demoed Manual-Only when a key is present.

### Wave 0 Gaps
- [ ] `tests/unit/test_assertion_gate.py` — fake-driver no-vacuous resolution (GEN-03)
- [ ] `tests/unit/test_examples_derivation.py` — KG->Examples (GEN-01)
- [ ] `tests/unit/test_selector_gate.py` — rendered-fixture static scan (GEN-05a)
- [ ] `tests/unit/test_generate_scenarios.py` — mocked-gateway + no-key fallback (GEN-01)
- [ ] `tests/functional/test_scenarios_router.py` — status lifecycle + auth (GEN-02)
- [ ] `tests/functional/test_codegen.py` — repo-locator codegen under graph_mode (GEN-04)
- [ ] `tests/functional/test_stability.py` + `test_seeded_bug.py` — planted-spec N-run + bug-build (GEN-05b)
- [ ] Compose: `saucedemo-bug` service + `SEED_BUG` build-arg (infra; verify build before harness)
- [ ] Frontend: `apps/web/tests/e2e/scenarios.spec.ts` — mocked-API review-queue e2e (Phase-5 pattern)

## Security Domain

> security_enforcement enabled (absent = enabled).

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `Depends(get_current_user)` on every new router (review + generate) — Phase-1 JWT |
| V3 Session Management | no (inherited) | existing httpOnly-cookie JWT; no change |
| V4 Access Control | yes | router-level auth gate; codegen reads approved-only (no privilege bypass) |
| V5 Input Validation | yes | gherkin Parser lint + structured kg_ref schema validation; edge_type allow-list (no Cypher injection); Pydantic bodies; edited Gherkin re-linted before save |
| V6 Cryptography | no | no new crypto; provider keys via existing gateway; PLAT-07 (no creds in prompts/artifacts) carried |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cypher injection via LLM edge_type/element_key | Tampering | parameterize values; edge_type from kg/schema allow-list constants only; read-only execute_read |
| Freehand/malicious selector in generated code | Tampering | static selector gate rejects inline literals; locators only from repo |
| Command injection via spec_path in the runner | Tampering | run_id-derived spec_path, argv list, no shell (Phase-3 T-03-15, reused verbatim) |
| Target creds leaking into Gherkin/artifacts | Info Disclosure | PLAT-07: SauceDemo PUBLIC demo creds only; no decrypted/ciphertext creds in prompts or generated files |
| Untrusted DOM/flow text in prompts | Tampering/Injection | untrusted-fence prompt pattern (Phase-3/5); only KG-derived structured context, never raw DOM |
| Edited scenario bypassing gates | Tampering | edit-save AND approve both re-run lint + no-vacuous gates (D-02/D-04) |
| Unbounded read DoS on the graph | DoS | LIMIT on every read query (kg/reader pattern); gate queries are count-existence |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pytest-bdd | spec generation/execution | yes | 8.1.* | — |
| gherkin-official | lint gate | yes | 29.0.0 (transitive) | — |
| jinja2 | codegen | yes | 3.1.* | — |
| playwright + chromium | spec runtime | yes (baked into api image) | 1.60.* | — |
| pytest-playwright | page fixtures | yes | 0.8.* | — |
| Neo4j (graph profile) | Element Repo + no-vacuous gate | yes via graph_mode | 2025 | gate/codegen unit tests use a fake driver |
| SauceDemo (default) | N-run stability target | yes | nginx static | — |
| saucedemo-bug | seeded-bug breakage detection | no (to build this phase) | — | none — must build (build-arg) |
| ANTHROPIC/OPENAI key | live generate->stabilize | no (empty) | — | deterministic no-key fallback (gates/harness fully provable without it; live = Manual-Only) |

**Missing with no fallback:** `saucedemo-bug` build (Slice 4 must create it — it is the GEN-05 breakage-detection mechanism).
**Missing with fallback:** provider keys -> no-key fallback covers all deterministic proofs; live generation is Manual-Only (project-wide convention).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | SauceDemo public accounts (locked_out_user/problem_user/etc.) seed negative Example rows | Examples derivation | LOW — only enriches outlines; positive standard_user row suffices |
| A2 | A `sed`/substitution build-arg on the existing nginx build reliably injects one DOM defect that breaks the accepted spec | Seeded-bug build | MEDIUM — the mutation must target an element the accepted spec actually asserts; pick the mutated id/class TOGETHER with the planted spec |
| A3 | Phase-5 captured form validation rules are queryable for negative-row derivation | Examples derivation | LOW-MEDIUM — if validation rules aren't in the KG, derive negatives from required-field emptiness instead (still deterministic) |
| A4 | Sequencing codegen (neo4j up) then stability/bug-run (neo4j down) keeps memory under 3 GB | Memory bound | MEDIUM — verify empirically in the plan; if concurrent is needed, drop one target or lower neo4j heap |

## Open Questions

1. **Exact seeded defect on SauceDemo.**
   - Known: a renamed `#login-button` or `.inventory_list` breaks the login/assert flow deterministically.
   - Unclear: which mutation best demonstrates breakage for the planted spec AND a realistic generated spec.
   - Recommendation: rename `.inventory_list` (the post-login success assertion) — a single `sed` on the served bundle; author the planted spec to assert `.inventory_list` so it passes vs std and fails vs bug. Decide id+spec together (A2).

2. **then_refs on edit-in-place.**
   - Known: gherkin_text is editable; then_refs is structured.
   - Unclear: if a reviewer edits a `Then`'s text, must they also re-supply its kg_ref?
   - Recommendation (minimal): keep then_refs editable as JSON alongside the text; re-run the no-vacuous gate on save. If a Then is added without a ref, the gate rejects (vacuous). Deep re-derivation on edit is deferred.

## Sources

### Primary (HIGH confidence)
- Codebase (live): `apps/api/app/services/generation.py`, `templates/test_login.py.j2`, `services/execution.py`, `services/kg/reader.py`, `services/kg/schema.py`, `infra/docker-compose.yml`, `infra/targets/saucedemo/Dockerfile`, `pyproject.toml`, `uv.lock` — the exact seams to upgrade + the locked/installed versions.
- `apps/api/uv.lock` — gherkin-official 29.0.0 (transitive); pytest-bdd 8.1, jinja2 3.1, playwright 1.60, pytest-playwright 0.8 [VERIFIED].
- Phase summaries 03-03, 03-04, 05-02, 05-03, 02-01 — generation seam, subprocess runner, Element Repository, gateway no-key fallback patterns.
- CLAUDE.md (locked stack) + STATE.md (gherkin-pytest-bdd-conflict memory, 3 GB cap, port facts).

### Secondary (MEDIUM confidence)
- pytest-bdd Scenario Outline -> pytest parametrization behavior [CITED: pytest-bdd docs — standard outline support; behavior is the locked-version default].

### Tertiary (LOW confidence)
- None — no unverified web claims; this phase is grounded entirely in the installed stack + codebase.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every dep installed + version-locked (uv.lock verified); zero new packages.
- Architecture (the 4 novel mechanisms): HIGH — designed against live code surfaces (kg/reader, kg/schema, execution runner, generation seam); deterministic + unit-testable by construction.
- Pitfalls: HIGH — drawn from concrete prior-phase deviations (03-04 reload bug, 05-02 no-key fallback, gherkin conflict memory).
- Seeded-bug specifics: MEDIUM — mechanism is sound; exact mutation+planted-spec pairing is an A2 plan decision.

**Research date:** 2026-06-20
**Valid until:** 2026-07-20 (stable — locked stack, no fast-moving external deps)
