# Phase 6: BDD & Playwright Generation - Pattern Map

**Mapped:** 2026-06-20
**Files analyzed:** 28 (new + modified)
**Analogs found:** 25 / 28 (3 net-new mechanisms keyed to their closest reference)

> **Phase 6 is an UPGRADE, not a greenfield.** Almost every new file extends a Phase-3 / Phase-5
> seam rather than inventing a pattern. Read this map as: "this new file copies THAT existing
> file's shape, changing only X." The three genuinely novel mechanisms (Then→KG gate,
> freehand-selector AST gate, N-run+seeded-bug harness) are flagged in `## No Direct Analog`
> with their closest reference + the exact delta.

---

## Carried Invariants (apply to EVERY relevant new file)

These are non-negotiable patterns proven in Phases 1–5. The planner must thread each into the
plans that touch the matching tier.

| Invariant | Source of truth | Applies to |
|-----------|-----------------|------------|
| **Gateway-only LLM + no-key fallback** | `services/llm_gateway.py` `complete()`; `services/kg/flows.py:184-227` `categorize_flow` | `generation.py` (scenario gen) — never `init_chat_model` directly |
| **Jinja2 owns structure / LLM fills narrow slots** | `generation.py:221-257`; `templates/test_login.py.j2:1-14` | all `codegen/` + `templates/` |
| **workspaces/<run_id>/ artifacts (gitignored)** | `generation.py:78-84` (`_ws_run_dir`); `core/workspaces` | `codegen/project.py`, stability harness |
| **Subprocess (never in-process pytest) for runs** | `services/execution.py:49-92` (`asyncio.create_subprocess_exec`, argv list, no shell) | `stability.py` (N-run + seeded-bug) |
| **Read-only parameterized Cypher, labels/edges from `kg/schema` constants** | `services/kg/reader.py:30-39` (`execute_read`), `:_LIMIT` DoS guard | `gates/assertion_gate.py`, `codegen/locators.py`, `codegen/examples.py` — NO writes (single-writer is Phase-5 kg/writer; the grep gate must stay green) |
| **Auth-gated routers** | `routers/kg.py:49-54`, `routers/executions.py:20-24` (`dependencies=[Depends(get_current_user)]`) | `routers/scenarios.py` |
| **Fresh SessionLocal in background/metered paths** | `execution.py:86`, `flows.py:205` | `stability.py`, `generation.py` metered calls |
| **gherkin 29.x parser (NOT a 40.x pin)** | `generation.py:30` `from gherkin.parser import Parser` | `gates/gherkin_lint.py` |
| **Migration chain head is 0005 → next is 0006** | `alembic/versions/0005_explore_stop_reason.py:18-19` | `0006_scenarios.py` (`down_revision="0005"`) |
| **OOM mitigation** | docker-compose neo4j block `:146-173`; STATE.md 3GB cap | stability harness: codegen under graph_mode (neo4j up), STOP neo4j before the run phase |

---

## File Classification

### Backend — services / gates / codegen

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `services/generation.py` (UPGRADE) | service | transform | itself (Phase-3 generate seam) | exact (in-place upgrade) |
| `services/gates/gherkin_lint.py` (NEW, extracted) | utility | transform | `generation.py:87-97` `validate_gherkin` | exact (move + extend) |
| `services/gates/assertion_gate.py` (NEW) | service | request-response (Neo4j read) | `kg/reader.py` existence reads + `kg/schema.py` allow-list | role-match (net-new) |
| `services/gates/selector_gate.py` (NEW) | utility | transform (AST scan) | `generation.py:248-252` `ast.parse` | partial (net-new) |
| `services/codegen/project.py` (NEW) | service | file-I/O | `generation.py:240-257` (Jinja2 render + write) | role-match |
| `services/codegen/examples.py` (NEW) | utility | transform | `kg/flows.py` pure-fn over KG structures | role-match (net-new) |
| `services/codegen/locators.py` (NEW) | utility | transform | `generation.py:44-46` `OBSERVED_SELECTORS` (generalized) | role-match (net-new) |
| `services/stability.py` (NEW) | service | batch (subprocess) | `services/execution.py:49-92` | role-match (net-new orchestration) |
| `services/scenario_service.py` (NEW) | service | CRUD | `services/run_service.py` | exact |

### Backend — models / schemas / routers / migrations / templates

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `models/scenario.py` (NEW) | model | CRUD | `models/run.py` (Run/Execution) | exact |
| `alembic/versions/0006_scenarios.py` (NEW) | migration | — | `alembic/versions/0004_runs_executions.py` | exact |
| `schemas/scenario.py` (NEW) | schema | request-response | `schemas/kg.py` | exact |
| `routers/scenarios.py` (NEW) | route | CRUD | `routers/kg.py` + `routers/executions.py` (+ mutation translation from `routers/generate.py`) | exact |
| `routers/generate.py` (UPGRADE) | route | request-response | itself | exact (extend) |
| `templates/pages/page_object.py.j2` (NEW) | config (template) | — | `templates/test_login.py.j2` | role-match |
| `templates/steps/steps.py.j2` (NEW) | config (template) | — | `templates/test_login.py.j2` | role-match |
| `templates/{conftest,fixtures,utils,data_model}.j2` (NEW) | config (template) | — | `templates/test_login.py.j2` | role-match |
| `templates/test_login.py.j2` (RETAINED) | config (template) | — | itself | keep verbatim (planted-spec proof) |

### Frontend — review queue

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/(dashboard)/scenarios/page.tsx` (NEW) | component | request-response | `app/(dashboard)/graph/flows/page.tsx` | exact |
| `app/(dashboard)/scenarios/[id]/page.tsx` (NEW) | component | request-response + mutation | `app/(dashboard)/graph/flows/[id]/page.tsx` | role-match |
| `lib/api/scenarios.ts` (NEW) | utility (zod client) | request-response | `lib/api/kg.ts` | exact |
| `components/app-sidebar.tsx` (MODIFY) | component | — | itself (`NAV_ITEMS`) | exact (append one item) |
| `tests/e2e/scenarios.spec.ts` (NEW) | test | — | existing web e2e (Phase-5 pattern) | role-match |

### Infra

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `infra/targets/saucedemo/Dockerfile` (UPGRADE) | config | — | itself | exact (add `SEED_BUG` build-arg) |
| `infra/docker-compose.yml` (MODIFY) | config | — | `saucedemo` service `:130-143` | exact (add `saucedemo-bug` sibling) |

### Tests (backend)

| New File | Closest Analog |
|----------|----------------|
| `tests/unit/test_assertion_gate.py`, `test_examples_derivation.py`, `test_selector_gate.py`, `test_generate_scenarios.py` | `tests/unit/conftest.py` `fake_gateway` + fake-driver injection (`kg/reader` `driver=` kwarg) |
| `tests/functional/test_scenarios_router.py`, `test_codegen.py`, `test_stability.py`, `test_seeded_bug.py` | Phase-3 deterministic execute proof + graph-marked functional pattern |

---

## Pattern Assignments

### `services/generation.py` (UPGRADE — service, transform)

**Analog:** itself. Keep the existing seam; ADD `generate_scenarios(db, run_id)`.

- **Gateway call shape — copy verbatim** (`generation.py:201-207`): `await llm_gateway.complete(db, messages, operation_type="generate.bdd", run_id=run_id, max_tokens=...)`. The ONLY LLM path (D-07). Never `init_chat_model`.
- **Validate-before-persist** (`generation.py:208-216`): call lint THEN the no-vacuous gate BEFORE the row write; on failure raise `GenerationError`, write nothing. (Phase 6 writes a Postgres `draft` row instead of a `.feature` file, but the order is identical.)
- **No-key fallback — copy `flows.py:184-227`**: wrap the metered call; on `BudgetExceeded`/`KillSwitchActive`/any provider error, emit a DETERMINISTIC minimal `{gherkin, then_refs}` pair (one `Given/When/Then` with a single resolvable ref from the flow's terminal page) so gen + both gates are provable with NO key.
- **Request `{gherkin, then_refs}` JSON** in one gateway call (RESEARCH Mechanism 1) — the sidecar then_refs is emitted in lockstep with the prose.
- **Untrusted-fence prompt — copy `flows.py:165-203`** (`<<<UNTRUSTED_STEPS>>>`): KG-derived context only, never raw DOM.

### `services/gates/gherkin_lint.py` (NEW — extract from generation.py)

**Analog:** `generation.py:87-97` `validate_gherkin`.

Move this verbatim so BOTH generation AND the edit/approve router share one linter (D-04):
```python
from gherkin.parser import Parser
def validate_gherkin(text: str) -> None:
    try:
        Parser().parse(text)
    except Exception as exc:  # noqa: BLE001
        raise GenerationError(f"invalid Gherkin: {exc}") from exc
```
Do NOT add a `gherkin-official` pin — 29.0.0 is transitive via pytest-bdd (CRITICAL conflict).

### `services/gates/assertion_gate.py` (NEW — the novel no-vacuous gate)

**Analog:** `kg/reader.py:30-39` (`_read`/`execute_read` + `_LIMIT`) + `kg/schema.py:33-37,62-70` (edge constants + `VERB_ENTITY_MAP`).

- **Read shape — copy `reader._read`** exactly: managed `execute_read`, parameterized, `LIMIT`, `driver` kwarg defaulting to the lifespan singleton (so a fake driver injects in unit tests).
- **Edge-type allow-list — use `kg/schema` constants** (`CREATES`/`UPDATES`/`DELETES`): validate `edge_type in {...}` BEFORE building Cypher, then inject the CONSTANT (never the LLM string) — relationship types can't be parameterized (Pitfall 2 / injection). Unknown edge_type → vacuous.
- **Existence Cypher** (RESEARCH §Mechanism 1): three count-existence queries (edge / element by key / page by fingerprint), all `execute_read`.
- **Pure gate fn**: `resolve_then_refs(then_refs, driver) -> list[str]` (unresolved Then texts); pass iff `== []` AND ≥1 Then has a ref.

### `services/gates/selector_gate.py` (NEW — the novel freehand-selector AST gate)

**Analog:** `generation.py:248-252` (`ast.parse(rendered)` already used on rendered output).

- AST-walk for `Call` nodes whose `func` is a selector sink (`page.locator`, `page.fill/click`, `get_by_role/_text/_test_id/_label/_placeholder`) with a `Constant` str first arg → violation, UNLESS the module is a page-object. Page objects are the single sanctioned literal home (and a unit test asserts each literal equals a repo chain entry). Regex fallback for raw CSS/XPath constants in spec/step files. Conceptually the AST cousin of the Phase-4 single-write-path grep gate.

### `services/codegen/locators.py` (NEW)

**Analog:** `generation.py:44-46` `OBSERVED_SELECTORS` (hard-coded tuple) → generalized to a KG query.

Read `kg/reader.element_repository()` (returns per element: `key`, `role`, `label`, deserialized `chain`, `history`, `page_fp`, `page_url` — `reader.py:114-124`). Each page object's attribute = the top-priority chain entry, sourced by the template — the LLM never sees or emits it.

### `services/codegen/examples.py` (NEW)

**Analog:** `kg/flows.py` pure-fn-over-KG-structures style; inputs from `reader.page_detail` (`forms`) + `kg/schema.VERB_ENTITY_MAP`.

Pure function: Form fields → Example columns; BusinessEntity/SauceDemo public users → rows; validation rules → negative rows. Unit-testable on a fixture graph, no keys (A3 fallback: derive negatives from required-field emptiness if validation rules absent).

### `services/codegen/project.py` (NEW — service, file-I/O)

**Analog:** `generation.py:63-67` (`_jinja_env` setup) + `:240-257` (render → `ast.parse` → write under `_run_dir`).

Build the `pages/steps/features/conftest/fixtures/utils/data/reports` tree under `_ws_run_dir(run_id)/<target>/`. `ast.parse` every rendered `.py` before write, then run the freehand-selector gate. Reads `scenario_service.list_approved(run_id)` ONLY (D-01).

### `services/stability.py` (NEW — the novel N-run + seeded-bug harness)

**Analog:** `services/execution.py:49-92` `run_execution` (subprocess shape) — reuse VERBATIM.

- Call the `asyncio.create_subprocess_exec("uv","run","pytest",spec_path,"-q", ...)` shape N times (`STABILITY_RUNS`, default 3). Accept iff ALL N exit 0.
- Seeded-bug run: same shape with `SEEDED_BUG_BASE_URL` override; assert it FAILS.
- Fresh subprocess + fresh browser context each run; argv list, no shell (T-03-15).
- **OOM sequencing** (RESEARCH Mechanism 4 / Pitfall 4): codegen WRITES the spec under graph_mode (neo4j up); then STOP neo4j and run stability + bug-run (need no graph). Planted-spec proof needs no neo4j.

### `services/scenario_service.py` (NEW — service, CRUD)

**Analog:** `services/run_service.py` (whole file).

- `VALID`-style status guard (`run_service.py:24-39`): `{"draft","approved","rejected"}`; `_validate_status` raises on unknown.
- `create_scenario`/`set_status`/`get`/`list` mirror `create_run`/`set_status`/`get_run`/`list_runs` (`select` + `db.scalar`/`db.scalars`, `await db.commit()/refresh()`).
- `list_approved(run_id)` filters `status=="approved"` in the query (D-01 — only approved feed codegen).

### `models/scenario.py` (NEW — model, CRUD)

**Analog:** `models/run.py` Run/Execution.

Copy the `Mapped[...] = mapped_column(...)` style + `created_at` `server_default=func.now()`. Fields (RESEARCH §Review Queue Model): `id` PK, `run_id` (String(64), index), `flow_id` (index), `feature_name`, `gherkin_text` (Text), `then_refs` (JSON), `status` (String(16), default "draft"), `edited` (bool), `stale` (bool), `created_at`/`updated_at`. Use SQLAlchemy `JSON` for `then_refs`.

### `alembic/versions/0006_scenarios.py` (NEW — migration)

**Analog:** `alembic/versions/0004_runs_executions.py` (`op.create_table` + `op.create_index`) and the `revision/down_revision` header from `0005_explore_stop_reason.py:18-19`.

`revision="0006"`, `down_revision="0005"`. Create `scenarios` table + index on `run_id` (and `flow_id`). Mirror the `sa.Column(..., server_default=sa.text('now()'))` shape from 0004. App tables only (the LangGraph checkpoint-table caveat from 0005's docstring carries).

### `schemas/scenario.py` (NEW — schema, request-response)

**Analog:** `schemas/kg.py` (Pydantic v2 `BaseModel` + `Field`, `from __future__ import annotations`).

List/detail/edit/approve schemas. The `then_refs` response shape mirrors the sidecar JSON (then_text, kind, ref). Keep field names aligned with `lib/api/scenarios.ts` zod (the kg.py ↔ kg.ts contract note at `schemas/kg.py:6-9`).

### `routers/scenarios.py` (NEW — route, CRUD)

**Analog:** `routers/kg.py:49-54` (auth-gated router) + `routers/executions.py` (list/get by id) + `routers/generate.py:41-45` (typed-exception → 422).

- `APIRouter(prefix="/api", tags=["scenarios"], dependencies=[Depends(get_current_user)])`.
- `GET /scenarios?status=draft`, `GET /scenarios/{id}`, `POST /scenarios/{id}/edit` (re-run BOTH gates → 422 on fail, no save; `edited=true` on success), `POST /scenarios/{id}/approve` (re-run both gates defense-in-depth → `status=approved`), `POST /scenarios/{id}/reject`.
- `GenerationError → HTTPException(422)` exactly like `generate.py:43-44`.

### `routers/generate.py` (UPGRADE — route)

**Analog:** itself. Add the scenario-generation + codegen entrypoints alongside the existing `/generate-bdd` / `/generate-scripts`. Same auth gate, same `_require_run` 404 guard (`generate.py:29-33`), same 422 translation.

### Templates (`templates/pages|steps/*.j2`, conftest/fixtures/utils/data) (NEW)

**Analog:** `templates/test_login.py.j2` (whole file).

Copy the header-comment contract ("LLM NEVER emits the whole .py; this template owns ALL structure and every selector") and the `{{ value | tojson }}` slot pattern (`test_login.py.j2:26-28`). Locators are TEMPLATE LOOKUPS from the repo, never slots. `steps.py.j2` emits `@given/@when/@then` bound via `scenarios("...feature")`; each `@then` calls a page-object assertion (1:1 home for the kg_ref). **Keep `test_login.py.j2` unchanged** — the planted-spec / deterministic-execute proofs use it.

### `app/(dashboard)/scenarios/page.tsx` (NEW — list)

**Analog:** `app/(dashboard)/graph/flows/page.tsx` (whole file).

`"use client"`, `useQuery({ queryKey, queryFn, retry: false })`, loading/empty/error states, table component. Map the `?status=` filter to the query (deep-linkable). Default sort risk-desc then updated-desc (06-UI-SPEC §1).

### `app/(dashboard)/scenarios/[id]/page.tsx` (NEW — detail/review)

**Analog:** `app/(dashboard)/graph/flows/[id]/page.tsx` for the detail-fetch shape; mutations via the `api.post` wrapper (`lib/api/client.ts:86-91`) with react-query invalidation on success (NO optimistic updates — the gate result is server-authoritative, 06-UI-SPEC). Gherkin editor is a token-styled native `<textarea>` (NOT a vendored shadcn block — 06-UI-SPEC §Design System). Per-Then indicators render strictly from server `then_refs` (never fabricated green).

### `lib/api/scenarios.ts` (NEW — zod client)

**Analog:** `lib/api/kg.ts` (whole file).

zod schemas mirroring `schemas/scenario.py`; fetchers via `api.get`/`api.post` (`./client`); the kg.ts ↔ kg.py alignment discipline. Add list/detail GETs + edit/approve/reject POSTs.

### `components/app-sidebar.tsx` (MODIFY)

**Analog:** itself (`app-sidebar.tsx:28-37` `NAV_ITEMS`). Append `{ icon: ListChecks, label: "Scenarios", href: "/scenarios" }` after "Knowledge graph"; active via the existing `pathname.startsWith(item.href)` (line 69). The file's own comment (`:21-24`) already anticipates a "Scenarios" item.

### `infra/targets/saucedemo/Dockerfile` (UPGRADE)

**Analog:** itself. Add an `ARG SEED_BUG=0`; when `1`, a final nginx-layer `sed` applies ONE deterministic DOM mutation (rename `.inventory_list` per Open-Q1) to the served `/usr/share/nginx/html`. Keep the pinned `SAUCEDEMO_SHA` build (`Dockerfile:22-25`) unchanged.

### `infra/docker-compose.yml` (MODIFY)

**Analog:** the `saucedemo` service block (`docker-compose.yml:130-143`). Add a `saucedemo-bug` sibling: `build: { context: ./targets/saucedemo, args: { SEED_BUG: "1" } }`, `mem_limit: 128m`, the SAME wget healthcheck shape, a DISTINCT host port (e.g. `8081:80`), and `profiles: [bugbuild]` so it is OFF by default (mirrors the `profiles: [graph]` gating at `:151`). Add `STABILITY_RUNS` + `SEEDED_BUG_BASE_URL` to the api env + `.env.example` (Phase-2 explicit-enumeration pattern).

---

## Shared Patterns

### Authentication (router gate)
**Source:** `routers/kg.py:49-54`, `routers/executions.py:20-24`
**Apply to:** `routers/scenarios.py`, the upgraded `routers/generate.py`
```python
router = APIRouter(prefix="/api", tags=["scenarios"],
                   dependencies=[Depends(get_current_user)])
```

### Read-only Cypher (no writes; single-write-path gate stays green)
**Source:** `services/kg/reader.py:30-39`
**Apply to:** `gates/assertion_gate.py`, `codegen/locators.py`, `codegen/examples.py`
```python
async def _read(cypher, params, *, driver=None):
    drv = driver or get_neo4j()
    async def _tx(tx): ...
    async with drv.session() as session:
        return await session.execute_read(_tx)   # never execute_write
```
Every query carries a `LIMIT` (DoS guard) and uses `kg/schema` constants for labels/edge types — never page/LLM-derived text interpolated into Cypher.

### Gateway-only LLM + deterministic no-key fallback
**Source:** `services/llm_gateway.py` `complete()`; `services/kg/flows.py:184-227`
**Apply to:** `generation.py` scenario generation
```python
try:
    async with SessionLocal() as db:
        result = await llm_gateway.complete(db, messages,
            operation_type="generate.bdd", run_id=run_id, max_tokens=...)
except (llm_gateway.BudgetExceeded, llm_gateway.KillSwitchActive):
    return _deterministic_minimal_pair(...)   # valid gherkin + one resolvable ref
except Exception:
    return _deterministic_minimal_pair(...)   # no-key provider error path
```

### Subprocess runner (never in-process pytest)
**Source:** `services/execution.py:49-92`
**Apply to:** `services/stability.py` (N-run + seeded-bug)
```python
proc = await asyncio.create_subprocess_exec("uv","run","pytest",spec_path,"-q",
    stdout=PIPE, stderr=STDOUT, cwd=_run_cwd())   # argv list, no shell
```

### Status lifecycle guard
**Source:** `services/run_service.py:24-39`
**Apply to:** `services/scenario_service.py`
```python
VALID = {"draft", "approved", "rejected"}
def _validate_status(s): 
    if s not in VALID: raise ValueError(...)
    return s
```

### Mocked-gateway / fake-driver unit testing (no keys, no spend)
**Source:** `tests/unit/conftest.py` `fake_gateway` (`:80-126`); `kg/reader` `driver=` kwarg injection
**Apply to:** `test_assertion_gate.py` (fake driver returning `exists=true/false`), `test_generate_scenarios.py` (`fake_gateway`), `test_examples_derivation.py` / `test_selector_gate.py` (pure fns on fixtures)

### Jinja2-owns-structure / value-via-tojson
**Source:** `templates/test_login.py.j2:1-14,26-28`; `generation.py:63-67,240-257`
**Apply to:** all new templates + `codegen/project.py`

---

## No Direct Analog (net-new mechanisms — closest reference + delta)

| File / Mechanism | Role | Closest Reference | The Delta (what's new) |
|------------------|------|-------------------|------------------------|
| `gates/assertion_gate.py` — structured Then→KG-reference resolution | service | `kg/reader.py` existence reads + `kg/schema` allow-list + risk-style pure fn | The *gate semantics* (a Then with no graph-backed outcome = vacuous) and the sidecar-JSON kg_ref schema are new; the Cypher/allow-list/read mechanics are copied |
| `gates/selector_gate.py` — freehand-selector AST static gate | utility | Phase-4 single-write-path grep test concept; `generation.py:248-252` `ast.parse` | AST-based selector-sink detection with a page-object allowlist is new; the "scan generated source, reject violations" concept is the grep-gate cousin |
| `services/stability.py` — N-run stability + seeded-bug acceptance | service | `services/execution.py` subprocess runner | The *orchestration* (run N times; run vs bug build; accept iff N-green-then-red) is new; each individual run reuses the Phase-3 runner verbatim |
| `services/codegen/examples.py` — KG→Examples derivation | utility | `kg/flows.py` pure-fn-over-KG | Deriving Outline `Examples:` columns/rows from forms + VERB_ENTITY_MAP + validation rules is new |
| `templates/steps/steps.py.j2` — pytest-bdd step-defs bound to `.feature` | config | `templates/test_login.py.j2` (plain pytest-playwright) | pytest-bdd `@given/@when/@then` + `scenarios()` binding + Outline auto-parametrize replaces the plain-spec choice (Phase-3 plain spec retained ONLY for planted proofs) |
| `app/(dashboard)/scenarios/` review queue | component | `graph/flows` pages | Edit-in-place + mutations + per-Then honest gate indicators are new vs the read-only graph pages |

---

## Metadata

**Analog search scope:** `apps/api/app/{services,services/kg,routers,models,schemas,templates,alembic/versions}`, `apps/api/tests/unit`, `apps/web/{app/(dashboard),lib/api,components}`, `infra/{docker-compose.yml,targets/saucedemo}`
**Files scanned:** ~30 read in full or targeted
**Pattern extraction date:** 2026-06-20
