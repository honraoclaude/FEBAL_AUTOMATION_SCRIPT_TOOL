# Phase 5: Knowledge Graph & Flow Learning - Pattern Map

**Mapped:** 2026-06-19
**Files analyzed:** 24 new/modified (10 backend modules, 5 fixtures/tests-as-deliverable, 7 web, 2 shared/wiring)
**Analogs found:** 22 / 24 (2 net-new with closest-reference only)

> **The phase is a REFACTOR first, a build second.** The single most important fact: the inline Cypher in `apps/api/app/services/explorer/nodes.py` (`_build_persist_cypher` / `_write_workflow_step` / `_write_form_validation` + their `execute_write` bodies) is **lifted verbatim** into a new single-writer module `app/services/kg/writer.py`. The explorer's `persist_to_neo4j` node becomes a thin delegate that calls `writer.upsert_*` / `writer.link_*` and **holds zero `MERGE/CREATE/SET/DELETE` Cypher** (KG-05, grep-enforced). Every new write keeps the Phase-3/4 invariant intact INSIDE the writer: managed `execute_write` + a `RETURN count(*) AS n` read-back guard (a 0-count write raises), parameterized Cypher only. The MERGE key changes from `key` → `fingerprint` (one-time `DETACH DELETE` of any pre-existing live Phase-4 graph documented in RESEARCH Runtime State Inventory).

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/services/kg/writer.py` (NEW) | service (single write path) | CRUD / transform | `explorer/nodes.py` persist Cypher + `target_service.py` shape | role-match (lifted source) |
| `app/services/kg/schema.py` (NEW) | config (label/edge/constraint constants) | config | `explorer/risk.py` `DENY_VERBS` frozenset + `core/checkpointer.py` setup pattern | role-match |
| `app/services/kg/reader.py` (NEW) | service (read-only Cypher) | request-response | `explorer/nodes.py` `execute_read`-shaped queries + `run_service.py` query shape | role-match |
| `app/services/kg/flows.py` (NEW) | service (path-mining + LLM categorize) | batch / transform | `explorer/nodes.py` `decide` (gateway) + `budget.py` pure traversal logic | partial (net-new mining) |
| `app/services/kg/risk.py` (NEW) | utility (pure formula) | transform | `explorer/budget.py` `ExploreBudget` dataclass + pure functions | role-match (closest ref) |
| `app/services/kg/coverage.py` (NEW) | utility (pure metric) | transform | `explorer/budget.py` pure funcs + `fingerprint.py` purity discipline | role-match |
| `app/services/kg/__init__.py` (NEW) | module export | — | `explorer/__init__.py` | exact |
| `app/services/explorer/nodes.py` (MODIFIED) | service (persist node → delegate) | CRUD | itself (remove inline Cypher) | refactor in place |
| `app/routers/kg.py` (NEW) | route (read-only, auth-gated) | request-response | `routers/executions.py` + `routers/explore.py` | exact |
| `app/routers/stubs.py` (MODIFIED) | route (remove /flows + /coverage 501s) | request-response | itself | refactor in place |
| `app/schemas/kg.py` (NEW) | model (Pydantic response schemas) | — | `schemas/stub.py` (`FlowsResponse`/`CoverageResponse`) + `schemas/run.py` | exact |
| `app/main.py` (MODIFIED) | config (lifespan: KG constraint setup + include kg_router) | config | itself (`init_checkpointer` + `include_router` lines) | exact |
| `tests/fixtures/ground_truth/saucedemo.json` (NEW) | fixture (committed ground truth) | file-I/O | none (JSON shape in RESEARCH) | no analog (data file) |
| `tests/fixtures/kg/*.json` (NEW) | fixture (KG snapshots) | file-I/O | none | no analog (data file) |
| `tests/unit/test_single_write_path.py` (NEW) | test (grep enforcement) | — | `tests/unit/` pure tests + `Grep` over `app/` | partial |
| `tests/unit/test_flow_mining.py` (NEW) | test | — | `tests/unit/conftest.py` + pure budget tests | role-match |
| `tests/unit/test_risk.py` (NEW) | test | — | pure-function table tests (budget) | role-match |
| `tests/unit/test_flow_categorize.py` (NEW) | test | — | `tests/unit/conftest.py` `fake_gateway` | exact |
| `tests/unit/test_coverage.py` (NEW) | test | — | pure-function table tests | role-match |
| `tests/functional/test_kg_idempotency.py` (NEW) | test (graph-marked) | — | `tests/functional/test_explore_discovery.py` + `neo4j_session` | exact |
| `tests/functional/test_kg_schema.py` / `test_element_repo.py` / `test_kg_endpoints.py` (NEW) | test (graph) | — | `test_explore_discovery.py` (graph marker, neo4j_session) | exact |
| `apps/web/lib/api/kg.ts` (NEW) | client (zod + fetchers) | request-response | `lib/api/explore.ts` + `lib/api/targets.ts` | exact |
| `apps/web/app/(dashboard)/graph/**` (NEW) | component (browse pages) | request-response | `app/(dashboard)/targets/page.tsx` | exact |
| `apps/web/components/graph/*` (NEW) | component (tables/badges) | — | `components/targets/targets-table.tsx` | exact |
| `apps/web/components/app-sidebar.tsx` (MODIFIED) | component (nav append) | — | itself (`NAV_ITEMS` array) | exact |

---

## Pattern Assignments

### `app/services/kg/writer.py` (service, single write path — THE refactor)

**Analog:** `apps/api/app/services/explorer/nodes.py` (persist Cypher) — lift `_build_persist_cypher`, `_write_workflow_step`, `_write_form_validation`, and their `_write(tx)` bodies INTO this module. Service-layer shape (module-level functions, no class) mirrors `target_service.py` / `run_service.py`.

**Driver acquisition + read-back guard pattern** (lift from `explorer/nodes.py:461-469` — preserve EXACTLY):
```python
from app.core.neo4j_driver import get_neo4j

async def _write(tx) -> int:
    result = await tx.run(cypher, **params)   # parameterized ONLY (T-04-14)
    record = await result.single()
    return int(record["n"]) if record else 0  # RETURN count(*) AS n read-back

async with get_neo4j().session() as session:
    written = await session.execute_write(_write)
if written < 1:
    raise RuntimeError("kg_writer.upsert_page persisted nothing")  # SC1: 0-count FAILS
```
- **Reuse the lifespan `get_neo4j()` singleton** (`core/neo4j_driver.py`) — NEVER a second driver (RESEARCH anti-pattern; the driver IS the pool).
- The new MERGE keys on `$fingerprint` with the freshness split (RESEARCH Pattern 1): `ON CREATE SET first_seen=$now` / `ON MATCH SET last_verified=$now` + a `coalesce(last_verified,$now)` so a freshly-created node also carries freshness. **`first_seen` is NEVER touched on `ON MATCH`** (Pitfall 2).
- One `upsert_*` per canonical label (`upsert_page`/`upsert_button`/`upsert_form`/`upsert_workflow`/`upsert_element`/`upsert_business_entity`) and one `link_*` per edge (`link_navigates_to`/`link_submits`/`link_creates`/...). All keep the read-back guard.

**The current inline Cypher being lifted** (`explorer/nodes.py:386-402`, `508-514`, `535-541`) — these strings move here and become the fingerprint-keyed canonical versions; the `key`→`fingerprint` MERGE-property change is the only semantic edit.

---

### `app/services/kg/schema.py` (config — one source of truth for labels/edges/constraints)

**Analog:** `explorer/risk.py` `DENY_VERBS: frozenset[str]` (module-level constant set as a code source of truth) + `core/checkpointer.py` `setup()` pattern (DDL at startup, NOT Alembic).

**Constraint-at-startup pattern** (mirror `checkpointer.init_checkpointer()` → run once in the lifespan; Neo4j schema is NOT Alembic, RESEARCH Runtime State Inventory). Constants like RESEARCH Pattern 1:
```python
PAGE_FP_CONSTRAINT = (
    "CREATE CONSTRAINT page_fp IF NOT EXISTS "
    "FOR (p:Page) REQUIRE p.fingerprint IS UNIQUE"
)
# Button/Form/Workflow/Element/BusinessEntity analogous
```
- An idempotent `async def ensure_constraints(driver)` runs these `IF NOT EXISTS` constraints at lifespan startup — the analog is `init_checkpointer()` which calls `setup()` once. **NOTE:** `core/neo4j_driver.init_neo4j()` is LAZY (no connect at boot, graph profile may be down) — so constraint creation must tolerate an unreachable neo4j at startup OR run on first write; decide at plan time (RESEARCH: api must boot when neo4j absent). The `core/checkpointer.py` analog connects eagerly; the KG constraint setup must NOT, to preserve the graceful-boot contract.
- Label/edge name constants live here so the grep test (KG-05) can exempt exactly `kg/writer.py` + `kg/schema.py`.

---

### `app/services/kg/risk.py` (utility, pure transform — NET-NEW, deterministic)

**Closest reference:** `apps/api/app/services/explorer/budget.py` — the `@dataclass(frozen=True) ExploreBudget` + pure, no-I/O, table-unit-testable functions (`cap_reason`, `is_loop`). Risk follows the same shape: a frozen `RiskWeights` dataclass + a pure `risk_score(signals, w=DEFAULT_WEIGHTS) -> int` clamped to 0-100 (RESEARCH Pattern 3). Also mirrors `explorer/risk.py`'s "PURE CODE, NEVER LLM JUDGMENT" discipline (D-04).

**Pure dataclass + clamped weighted sum** (RESEARCH Pattern 3; weights LOW-confidence, tune against SauceDemo). Tier thresholds (>=67 high / 34-66 medium / <34 low) feed the UI badge.

---

### `app/services/kg/flows.py` (service, batch/transform — NET-NEW path-mining + gateway categorize)

**Analog (mining):** `explorer/budget.py` pure traversal/ledger logic for the BOUNDED simple-path enumeration (MAX_PATH_LENGTH, dedup-by-node-set, MAX_FLOWS cap — RESEARCH Pattern 2/Pitfall 3). Read traversal uses `get_neo4j().session().execute_read` (the read counterpart of the writer's `execute_write`).

**Analog (categorize):** `explorer/nodes.py:235-244` `decide` node — the EXACT gateway call pattern to copy:
```python
from app.db.session import SessionLocal
from app.services import llm_gateway

async with SessionLocal() as db:                       # fresh session per gateway call (Pitfall 2)
    result = await llm_gateway.complete(
        db, messages,
        operation_type="flow.categorize",             # was "explore.decide"
        run_id=run_id, temperature=0, max_tokens=128,
    )
```
- **Untrusted-observation fencing** (copy `_DECIDE_SYSTEM` discipline, `nodes.py:49-55`): wrap steps as `<<<UNTRUSTED_STEPS>>>...<<<END_UNTRUSTED_STEPS>>>`, data-only system prompt.
- **Deterministic fallback** (copy the `BudgetExceeded`/`KillSwitchActive` catch from `nodes.py:245-252`): on no key, name flows `"Flow: <start> → <end>"` so flows + risk still render WITHOUT keys (only the semantic NAME is Manual-Only).
- `llm_gateway.complete` signature confirmed (`llm_gateway.py:303-314`): `(db, messages, *, operation_type, run_id=None, model=None, temperature=0, max_tokens, ...)`.

---

### `app/services/kg/reader.py` (service, read-only Cypher)

**Analog:** `explorer/nodes.py` query bodies (same `tx.run` + `result` pattern, but `execute_read`); Element Repository query is given verbatim in RESEARCH Code Examples (`ELEMENT_REPO`). The repository builds on the Phase-4 `:Element {chain_json, history_json}` nodes written by `explorer/locators.py` (the locator-chain/history seam) — the reader deserializes those JSON columns for the UI.

**Read pattern:** `LIMIT` on every query (DoS guard, RESEARCH Security Domain); parameterized; no client-supplied Cypher.

---

### `app/routers/kg.py` (route, read-only, auth-gated)

**Analog:** `apps/api/app/routers/executions.py` — the cleanest read-router shape to copy:
```python
router = APIRouter(
    prefix="/api",
    tags=["kg"],
    dependencies=[Depends(get_current_user)],   # router-level auth gate (T-03-07, V4)
)

@router.get("/flows", response_model=FlowsResponse)
async def flows(...) -> FlowsResponse: ...
```
- `GET /flows`, `GET /coverage`, `GET /graph` (or `/pages`), `GET /elements` — all read-only, all behind the existing `Depends(get_current_user)` gate (V4 access control; 401-unauth tests).
- `routers/explore.py` is the secondary ref for path-param routes (`/{run_id}/...`) if drill-in endpoints take a fingerprint/key path param.
- **Coverage trigger decision** (RESEARCH Open Q3): compute flows/coverage ON-DEMAND in the GET handlers (read-only, no write needed); optionally persist `:Workflow` category/risk via the writer when keys are present. Decide at plan time.

---

### `app/routers/stubs.py` (MODIFIED — remove /flows + /coverage 501s)

**Refactor in place:** delete the `flows()` and `coverage()` 501 handlers (`stubs.py:66-87`) and their imports; they move to `routers/kg.py` as real endpoints. **Leave** `heal` (Phase 8), `create-defect` (Phase 9), `dashboard` (Phase 10) untouched — they stay honest 501s. The `FlowsResponse`/`CoverageResponse` in `schemas/stub.py` are superseded by richer models in `schemas/kg.py` (the stub versions can be removed once nothing imports them).

---

### `app/schemas/kg.py` (model, Pydantic response schemas)

**Analog:** `schemas/stub.py` (`FlowSummary`/`FlowsResponse`/`CoverageResponse` are the minimal seed shapes to expand) + `schemas/run.py` style. The web `zod` schemas mirror these (boundary validation), so keep field names aligned with `lib/api/kg.ts`.

**Seed shapes already in repo** (`schemas/stub.py:59-83`): `FlowsResponse{flows:[FlowSummary]}`, `CoverageResponse{screens_total, screens_covered, flows_total, flows_covered, coverage_percent}`. Expand with risk_score, category, first_seen/last_verified, page/element repository shapes.

---

### `apps/web/lib/api/kg.ts` (client, zod + fetchers)

**Analog:** `apps/web/lib/api/explore.ts` (zod-at-boundary + `api.get` from `./client`) and `lib/api/targets.ts` (list-fetcher + `z.array(...).parse`). Copy the exact zod-mirror-of-Pydantic discipline:
```typescript
import { z } from "zod";
import { api } from "./client";

export const flowSchema = z.object({ flow_id: z.string(), name: z.string(), risk_score: z.number().int(), category: z.string().nullable(), step_count: z.number().int() });
export async function listFlows() { return z.array(flowSchema).parse(await api.get("/api/flows")); }
```
- All fetches ride the same-origin `/api/*` rewrite + httpOnly cookie (`lib/api/client.ts` handles 401→refresh→/login). No token handling.

---

### `apps/web/app/(dashboard)/graph/**` + `components/graph/*` (browse pages + tables)

**Analog (page):** `app/(dashboard)/targets/page.tsx` — `useQuery({queryKey, queryFn})`, header block (`flex items-center justify-between`, Heading 20px/600), no mutations here (read-only — drop the `useMutation`/`toast` parts).
**Analog (table):** `components/targets/targets-table.tsx` — the canonical table to copy verbatim:
- shadcn `Table/TableHeader/TableBody/TableRow/TableHead/TableCell`, 12px `font-normal` column headers, `font-mono text-sm` for URLs/fingerprints/locators.
- `LoadingRows()` skeleton + `EmptyState()` (copy both patterns; UI-SPEC requires loading/empty/error/populated states).
- **Risk badge** = copy `StatusBadge`/`SandboxBadge` (`targets-table.tsx:48-88`): `Badge variant="outline"` + `size-1.5 rounded-full bg-[var(--status-*)]` colored dot + tier WORD + mono numeric score (never color-alone — WCAG 1.4.1). Map high→`--status-fail`, medium→`--status-quarantine`, low→`--status-pass`, unscored→`--status-neutral` (UI-SPEC risk mapping).
- React default escaping only — no `dangerouslySetInnerHTML` (T-01-24).

---

### `apps/web/components/app-sidebar.tsx` (MODIFIED — nav append)

**Analog:** itself — append ONE entry to the `NAV_ITEMS` flat list (`app-sidebar.tsx:28-34`) following the `{icon, label, href}` contract, after "Explorations":
```typescript
{ icon: Workflow, label: "Knowledge graph", href: "/graph" },  // active via pathname.startsWith("/graph")
```
Icon `Workflow` or `Share2` from lucide (UI-SPEC). Active-state logic (`pathname.startsWith(item.href)` + `data-[active=true]` border) is already generic.

---

### `app/main.py` (MODIFIED — lifespan + router wiring)

**Analog:** itself — the `init_checkpointer()` line (`main.py:61`) is the model for adding KG constraint setup in the lifespan; the `app.include_router(stubs_router)` block (`main.py:73-81`) is where `app.include_router(kg_router)` is added. Constraint setup must NOT break the graceful-boot-without-neo4j contract (see schema.py note).

---

## Shared Patterns

### Single write path (KG-05) — the load-bearing invariant
**Source:** `explorer/nodes.py:461-469` (the `execute_write` + read-back body).
**Apply to:** ALL writes — they exist ONLY in `kg/writer.py`. Enforced by `tests/unit/test_single_write_path.py`: a `Grep`/ripgrep over `apps/api/app/` for `MERGE|CREATE \(|SET |DETACH DELETE|REMOVE ` failing on any hit outside `kg/writer.py` + `kg/schema.py` (RESEARCH Anti-pattern / Pitfall 6).

### Parameterized Cypher only (T-04-14)
**Source:** `explorer/nodes.py` (every `tx.run(cypher, **params)`; JSON-serialized `chain_json`/`history_json` as params, never f-strung).
**Apply to:** writer + reader + flows mining. Labels/edge-types are code constants (`kg/schema.py`), never interpolated from page text (Cypher injection mitigation, V5).

### Fresh `SessionLocal` per gateway call (Pitfall 2)
**Source:** `explorer/nodes.py:236` (`async with SessionLocal() as db:` around `llm_gateway.complete`).
**Apply to:** `kg/flows.py` categorize — never reuse a request/BackgroundTask session for the metered LLM call.

### Lifespan singletons, never per-request (driver = pool)
**Source:** `core/neo4j_driver.py` `get_neo4j()` + `core/redis_client.py`.
**Apply to:** writer, reader, flows — all acquire short-lived `session()` from the one lifespan driver.

### Gateway is the ONLY LLM path (PLAT-05/06)
**Source:** `services/llm_gateway.complete` signature (`llm_gateway.py:303`); explorer `decide` is the only caller pattern.
**Apply to:** `kg/flows.py` categorize — `operation_type="flow.categorize"`, `run_id` threaded; NEVER `init_chat_model` directly. (RESEARCH A7: gateway has no op-type allowlist — verify.)

### Pure, frozen-dataclass, table-tested logic (no I/O)
**Source:** `explorer/budget.py` (`ExploreBudget` + pure funcs) and `explorer/fingerprint.py` (purity discipline).
**Apply to:** `kg/risk.py`, `kg/coverage.py`, the deterministic core of `kg/flows.py` — unit-tested with NO keys, NO stack.

### Fingerprint is the MERGE key (do not re-hash)
**Source:** `explorer/fingerprint.py` `fingerprint(tree, cfg)` — the existing converge/persist dedup seam.
**Apply to:** the writer's `MERGE (p:Page {fingerprint:$fingerprint})` — the value MUST be the SAME `fingerprint(...)` output (RESEARCH Don't-Hand-Roll), backed by the uniqueness constraint.

### graph-marked functional tests under graph_mode
**Source:** `tests/functional/test_explore_discovery.py` (`pytestmark = [functional, graph, live_llm]`, `neo4j_session` fixture from `tests/conftest.py:52`, in-cluster host, per-run assertions).
**Apply to:** `test_kg_idempotency.py` / `test_kg_schema.py` / `test_element_repo.py` / `test_kg_endpoints.py`. NOTE: the deterministic KG proofs (idempotency/schema) are `graph` but NOT `live_llm` (no keys needed — they drive the writer over fixtures, not a live crawl), unlike `test_explore_discovery.py` which IS live_llm.

### Mocked-gateway unit fixture
**Source:** `tests/unit/conftest.py` `fake_gateway` (scripts `complete()` returns, records `operation_type`/`run_id`).
**Apply to:** `test_flow_categorize.py` — assert `operation_type="flow.categorize"` + the deterministic fallback path with no key.

### Read-router auth gate + 401 tests (V4)
**Source:** `routers/executions.py` / `routers/explore.py` (`dependencies=[Depends(get_current_user)]`).
**Apply to:** `routers/kg.py` — every endpoint; `test_kg_endpoints.py` asserts 401 unauth.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/fixtures/ground_truth/saucedemo.json` | fixture (data) | file-I/O | Hand-authored ground-truth data — no code analog; shape given in RESEARCH Code Examples (D-07). |
| `tests/fixtures/kg/*.json` | fixture (data) | file-I/O | Hand-built fixture KG snapshots for deterministic coverage/mining/idempotency tests — no code analog. |

> Net-new LOGIC (`kg/writer.py` idempotent-MERGE+freshness, `kg/flows.py` bounded path-mining, `kg/risk.py` formula, `kg/coverage.py` metric) has a closest reference per the assignments above — none is fully green-field. The genuinely novel design (freshness `ON CREATE`/`ON MATCH` reconciliation) is specified concretely in RESEARCH Pattern 1; planner should use RESEARCH code examples there, anchored to the lifted `explorer/nodes.py` write discipline.

---

## Metadata

**Analog search scope:** `apps/api/app/services/explorer/`, `apps/api/app/core/`, `apps/api/app/routers/`, `apps/api/app/services/`, `apps/api/app/schemas/`, `apps/api/tests/`, `apps/web/lib/api/`, `apps/web/app/(dashboard)/`, `apps/web/components/`.
**Files scanned (read in full or targeted):** ~22.
**Pattern extraction date:** 2026-06-19
