# Phase 4: Explorer Agent - Pattern Map

**Mapped:** 2026-06-15
**Files analyzed:** 38 (created/modified across api, web, infra, shared, tests)
**Analogs found:** 33 with a strong in-repo analog / 38; 5 are NET-NEW patterns mapped to their closest structural reference

> **Framing — the Explorer EVOLVES the Phase-3 tracer seam.** Phase 3 shipped a deterministic, LLM-free SauceDemo crawl across `explorer.py` / `explore.py` / `neo4j_driver.py` / `run_service.py`. Phase 4 keeps every *invariant* that seam established and replaces only the *body* with a LangGraph StateGraph agent. The single most important reuse signal below is the column **REUSE vs NET-NEW**: planners should copy the invariant (fresh SessionLocal, managed `execute_write` + read-back, single decrypt surface, parameterized Cypher, router-level auth, graph-marked tests) verbatim and treat only the flagged NET-NEW modules as genuinely new code.

---

## Carried-Forward Phase-3 Invariants (apply to ALL backend explorer files)

These are NOT re-derived per file; they are the seam contract every new backend module inherits. Each is cited to its source line below and referenced per-file in the assignments.

| Invariant | Source (verified) | Applies to |
|-----------|-------------------|------------|
| **Fresh `SessionLocal()` per BackgroundTask** — never the request `get_db` session (closed after 202) | `explorer.py:106` (`async with SessionLocal() as db:`) | `explorer.py` driver entrypoint, every node that persists run state |
| **Managed `execute_write` + read-back guard** — a write that persists nothing FAILS the run, never reports passed (SC1 lesson) | `explorer.py:85-100`, `:148-149`; RESEARCH "Managed Neo4j write + read-back" | `nodes.py` persist node, all Neo4j writes |
| **Single decrypt surface** — creds ONLY via `target_service.get_decrypted_credentials`; never logged, never on a node | `explorer.py:114`; `target.py:38-40` | `auth.py`, `explorer.py` |
| **Parameterized Cypher only** — never f-string page-derived text into a query (T-03-05) | `explorer.py:74-97` | `nodes.py` persist, locator writes |
| **Router-level auth gate** — `dependencies=[Depends(get_current_user)]` on the router, no route reachable unauthenticated (T-03-07) | `explore.py:17-22`, `admin_llm.py:19-24`, `executions.py:20-24` | extended `explore.py`, new SSE route |
| **202 + run_id + BackgroundTask dispatch**, status set inside the task | `explore.py:25-35`, `explorer.py:103-156` | extended `explore.py` |
| **Status integrity via `run_service.set_status`** guarded by the 4-state VALID set; failure captured as `error`, never a silent crash (T-03-09) | `run_service.py:25,32-39,51-64`; `explorer.py:107-156` | `explorer.py`, terminal handling |
| **Lifespan singletons (lazy connect)** — one driver/client per process, opened in `lifespan`, closed at shutdown | `neo4j_driver.py:28-63`, `redis_client.py:21-49`, `main.py:53-62` | `checkpointer.py`, neo4j/redis reuse |
| **Graph-marked functional tests run under graph_mode** (neo4j up, web down — 3 GB cap); in-cluster host = `http://saucedemo:80`; never assert immediately after 202 — `poll_until_terminal` | `test_explore.py:22-65` | all new functional tests |

---

## File Classification

### Backend — `apps/api/`

| New/Modified File | Role | Data Flow | Closest Analog | Match | REUSE/NET-NEW |
|-------------------|------|-----------|----------------|-------|---------------|
| `app/services/explorer.py` (REPLACE body) | service | event-driven (agent loop) | itself (Phase-3 tracer) | exact (evolves) | REUSE seam + invariants |
| `app/services/explorer/graph.py` | service | event-driven | RESEARCH Pattern 1; no in-repo analog | role-match | **NET-NEW (LangGraph)** |
| `app/services/explorer/state.py` | model | transform | RESEARCH Pattern 1 TypedDict; `schemas/run.py` shape | partial | NET-NEW (pure schema) |
| `app/services/explorer/nodes.py` | service | event-driven | `explorer.py:52-156` (write+read-back, playwright) | role-match | REUSE write pattern; NET-NEW nodes |
| `app/services/explorer/perception.py` | utility | transform | none (aria_snapshot) | none | **NET-NEW (snapshot compaction)** |
| `app/services/explorer/actions.py` | utility | transform | none | none | **NET-NEW (constrained menu)** |
| `app/services/explorer/risk.py` | utility | transform (pure) | `run_service._validate_status:32-39` (pure guard) | partial | **NET-NEW (pure, unit-testable)** |
| `app/services/explorer/fingerprint.py` | utility | transform (pure) | `explorer._page_key:43-49` (the tracer key it replaces) | partial | **NET-NEW (THE experimental unknown)** |
| `app/services/explorer/locators.py` | utility | transform (pure) | none | none | **NET-NEW (locator chain)** |
| `app/services/explorer/auth.py` | service | request-response | `explorer.py:114-125` (login + decrypt surface) | role-match | REUSE decrypt; NET-NEW storageState/relogin |
| `app/services/explorer/budget.py` | utility | transform (pure) | `llm_gateway._effective_caps:239-261` (clamp/tighten) | partial | **NET-NEW (caps/loop/saturation)** |
| `app/services/explorer/progress.py` | service | pub-sub | `redis_client.py` + `llm_gateway` redis usage | partial | **NET-NEW (Redis pub/sub vs GET/SET)** |
| `app/core/checkpointer.py` | config | (lifespan resource) | `neo4j_driver.py`, `redis_client.py` (lifespan singleton) | role-match | **NET-NEW (AsyncPostgresSaver, psycopg3)** |
| `app/routers/explore.py` (EXTEND) | route | request-response + SSE | itself + `admin_llm.py`/`stubs.py` shape | exact | REUSE; NET-NEW SSE route |
| `app/main.py` (MODIFY) | config | — | itself (lifespan + includes) | exact | REUSE; add checkpointer.setup() |
| `app/core/config.py` (MODIFY) | config | — | itself (Settings) | exact | REUSE; add checkpoint_dsn + budget defaults |
| `alembic/versions/0005_*.py` (explore fields, if any) | migration | — | `0004_runs_executions.py` | exact | REUSE migration style |
| `app/models/run.py` (MAYBE extend) | model | — | `models/run.py` / `target.py` | exact | REUSE |

### Frontend — `apps/web/`

| New/Modified File | Role | Data Flow | Closest Analog | Match | REUSE/NET-NEW |
|-------------------|------|-----------|----------------|-------|---------------|
| `app/(dashboard)/explore/[runId]/page.tsx` | component (page) | streaming (SSE) | `(dashboard)/targets/page.tsx` | role-match | REUSE shell; **NET-NEW EventSource** |
| `lib/api/explore.ts` | utility (api client) | request-response | `lib/api/targets.ts` | exact | REUSE (zod + api wrapper) |
| `components/explore/*` (counter tile, feed row, status pill, terminal banner) | component | streaming | `components/targets/targets-table.tsx` | role-match | REUSE token/compose patterns |
| `components/targets/targets-table.tsx` (MODIFY — add "Explore" item) | component | event-driven | itself (DropdownMenu) | exact | REUSE |
| `components/app-sidebar.tsx` (MODIFY — add "Explorations") | component | — | itself (NAV_ITEMS) | exact | REUSE |

### Shared / Tests / Infra

| New/Modified File | Role | Data Flow | Closest Analog | Match | REUSE/NET-NEW |
|-------------------|------|-----------|----------------|-------|---------------|
| `shared/events/__init__.py` (EXTEND — `ExploreProgressEvent`) | model | — | `shared/events/__init__.py` (RunStatusEvent) | exact | REUSE Pydantic-v2 schema-only |
| `tests/unit/test_fingerprint.py` etc. (8 unit files) | test | — | `tests/unit/conftest.py` (fake_chat_model, redis isolation) | role-match | REUSE mock/isolation fixtures |
| `tests/functional/test_explore_discovery.py` / `_live.py` | test | — | `tests/functional/test_explore.py` | exact | REUSE graph-marked + poll pattern |
| `infra/docker-compose.yml` / api `pyproject.toml` (deps) | config | — | existing compose/pyproject | exact | REUSE; add 4 packages (human-verify gate) |

---

## Pattern Assignments

### `app/services/explorer.py` (service, event-driven) — REPLACE body, KEEP invariants

**Analog:** itself (Phase-3 tracer). The function `run_explore(run_id, target_id)` stays the BackgroundTask entrypoint; its body changes from a hardcoded crawl to `await build_explorer_graph(checkpointer).ainvoke(state, config={"configurable": {"thread_id": run_id}})`.

**KEEP verbatim — the BackgroundTask + status wrapper (`explorer.py:103-156`):**
```python
async def run_explore(run_id: str, target_id: int) -> None:
    # Pitfall 2: a FRESH session owned by this task — never the request's get_db session.
    async with SessionLocal() as db:
        try:
            await run_service.set_status(db, run_id, "running")
            target = await target_service.get_target(db, target_id)
            if target is None:
                raise target_service.TargetNotFoundError(target_id)
            user, password = await target_service.get_decrypted_credentials(db, target_id)  # single decrypt surface
            ...
            # NEW: drive the LangGraph agent instead of the hardcoded crawl
            ...
            await run_service.set_status(db, run_id, "passed")
        except Exception as exc:  # noqa: BLE001 — never crash the task silently (T-03-09)
            await run_service.set_status(db, run_id, "failed", error=str(exc))
            log.warning("explore_failed", run_id=run_id, target_id=target_id, error=str(exc))
```

**KEEP — managed write + read-back is moved into `nodes.py` persist but its shape is `explorer.py:85-100`:**
```python
async def _write(tx) -> int:
    result = await tx.run(cypher, **params)   # PARAMETERIZED — never f-string page text
    record = await result.single()
    return int(record["edges"]) if record else 0
async with driver.session() as session:
    written = await session.execute_write(_write)
if written < 1:
    raise RuntimeError("explore persisted nothing")   # fail the run, never report passed
```

**REPLACE — the tracer `_page_key` (`explorer.py:43-49`)** is the stand-in that `fingerprint.py` replaces. Slice 1 may keep a URL key as a clearly-marked temporary; Slice 2 swaps in `structural_fingerprint`.

**Note:** the lifespan neo4j driver IS safe to reuse across tasks (`explorer.py:144`); the redis client and checkpointer pool are likewise lifespan singletons — never construct a second one inside the task.

---

### `app/core/checkpointer.py` (config, lifespan resource) — NET-NEW

**Closest reference:** `core/neo4j_driver.py:28-63` and `core/redis_client.py:21-49` — the module-global-singleton-opened-in-lifespan pattern. Copy that exact shape (`init_*` / `close_*` / `get_*` with a `_module_global`).

**Reference lifespan shape to mirror (`neo4j_driver.py:25-63`):**
```python
_driver: AsyncDriver | None = None
def init_neo4j() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(settings.neo4j_uri, auth=(...), liveness_check_timeout=0)
    return _driver
async def close_neo4j() -> None:
    global _driver
    if _driver is not None:
        await _driver.close(); _driver = None
def get_neo4j() -> AsyncDriver:
    return init_neo4j() if _driver is None else _driver
```

**NET-NEW body (RESEARCH Pattern 2, lines 198-217):** open one `AsyncConnectionPool` (psycopg3) + `AsyncPostgresSaver(pool)`, call `await checkpointer.setup()` ONCE at startup.
```python
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
pool = AsyncConnectionPool(conninfo=settings.checkpoint_dsn, max_size=4, open=False,
                          kwargs={"autocommit": True, "row_factory": dict_row})
await pool.open()
checkpointer = AsyncPostgresSaver(pool)
await checkpointer.setup()   # creates checkpoint tables OUTSIDE Alembic — idempotent
```

**CRITICAL ties to RESEARCH pitfalls:**
- **Pitfall 1 (DSN collision):** `settings.database_url` is `postgresql+asyncpg://` (SQLAlchemy, `config.py:20`, `session.py:13`). The checkpointer needs a PLAIN `postgresql://` DSN — add a derived `checkpoint_dsn` in `config.py` that strips `+asyncpg`. Same DB, two drivers.
- **Pitfall 6 / Anti-pattern (`RESEARCH:252,414-416`):** the 4 checkpoint tables are owned by `.setup()`, NOT Alembic. Do NOT add them to the `0004→0005` migration chain.
- The package is `psycopg` NOT `psycopg3` (`RESEARCH:81,455`).

**Wiring in `main.py`:** mirror `main.py:53-62` lifespan — add `init`/`setup` after `init_neo4j()` and a `close` in shutdown.

---

### `app/services/explorer/graph.py` + `state.py` + `nodes.py` (service, event-driven) — NET-NEW (LangGraph)

**Closest reference:** RESEARCH Pattern 1 (lines 153-196) — there is no in-repo StateGraph. `state.py`'s TypedDict is structurally like the Pydantic schemas in `schemas/run.py` but uses LangGraph reducers (`Annotated[list, add]`).

**`graph.py` — copy the build/compile skeleton from RESEARCH:178-195** (nodes navigate→perceive→enumerate→decide→act→persist→converge; `add_conditional_edges("converge", should_continue, {"loop":"navigate","stop":END})`; `g.compile(checkpointer=checkpointer)`).

**`nodes.py` — the persist node REUSES `explorer.py:85-100`** (managed `execute_write` + read-back). The decide node REUSES the gateway call (see Shared Patterns → LLM gateway). The act node is gated by `risk.py` BEFORE the click (RESEARCH:106-112). Richer node/edge labels per RESEARCH:357-363 (`Page`/`Form`/`Button`/`Link`/`Table`/`Element`/`Workflow`).

---

### `app/services/explorer/fingerprint.py` (utility, pure) — NET-NEW (THE experimental unknown, EXPL-06)

**Closest reference:** `explorer._page_key` (`explorer.py:43-49`) — the URL-normalized tracer key this module *replaces*. The replacement is a structural-skeleton SHA-256 hash, tunable via `FingerprintConfig`, with sibling-subtree folding ON by default (RESEARCH:271-295).

**The tracer key being replaced (`explorer.py:43-49`):**
```python
def _page_key(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") or "/", "", ""))
```
**NET-NEW shape (RESEARCH:277-289):** pure `structural_fingerprint(tree, cfg) -> str`. Unit-test: template-equality (6-item vs 4-item list hash identical), instance-collapse, layout-difference. Pure → no browser/LLM/spend.

---

### `app/services/explorer/risk.py` (utility, pure) — NET-NEW (EXPL-07)

**Closest reference:** `run_service._validate_status` (`run_service.py:32-39`) — the project's existing pattern for a tiny pure, table-unit-testable guard (a set membership check, no session). `risk.py` is the same idea: a `DENY_VERBS` set + `is_destructive(action, *, sandbox) -> bool` (RESEARCH:323-338). `sandbox` lifts the deny, read from `Target.sandbox` (`target.py:28`). Deterministic, evaluated BEFORE the act (defense-in-depth vs prompt injection, RESEARCH:410-412).

---

### `app/services/explorer/budget.py` (utility, pure) — NET-NEW

**Closest reference:** `llm_gateway._effective_caps` (`llm_gateway.py:239-261`) — the tighten-only clamp pattern Phase 4 must mirror for `Target.budget_overrides`.
```python
def clamp(key, global_cap):
    override = o.get(key)
    return global_cap if override is None else min(override, global_cap)
```
**NET-NEW:** `ExploreBudget` dataclass (max_steps/depth/revisits/wall_clock/saturation_window — RESEARCH:343-351) + loop detector + saturation counter. **Token/USD spend is NOT tracked here** — every gateway call passes `run_id` and a `BudgetExceeded` ends the run (`stop_reason="budget"`). Do NOT duplicate spend (D-06).

---

### `app/services/explorer/auth.py` (service, request-response) — REUSE decrypt; NET-NEW storageState

**Closest reference:** the login block in `explorer.py:114-125`.
```python
user, password = await target_service.get_decrypted_credentials(db, target_id)  # SINGLE decrypt surface
...
await page.fill(_USER_SEL, user); await page.fill(_PASS_SEL, password); await page.click(_LOGIN_SEL)
```
**KEEP:** creds ONLY from `get_decrypted_credentials`, never logged/never on a node (PLAT-07). **NET-NEW (RESEARCH:316-321):** generalize hardcoded SauceDemo selectors to a `input[type=password]` heuristic; `context.storage_state()` capture to `workspaces/<run_id>/storage_state.json`; logout detection + relogin recovery as a node-level guard.

---

### `app/services/explorer/progress.py` (service, pub-sub) — NET-NEW (Redis pub/sub)

**Closest reference:** `redis_client.py` (the lifespan client) + `llm_gateway.py:323,332,407-416` (existing redis usage — GET/MGET/pipeline). **This is flagged NET-NEW usage:** Phase 1-3 redis is GET/SET/counters; Phase 4 introduces **pub/sub** (`get_redis().publish(f"explore:{run_id}", event_json)`) — the publish side of the SSE seam (RESEARCH:385, D-07). Same lifespan client (`get_redis()`), new verb. `decode_responses=True` is already set (`redis_client.py:29`), so payloads are str.

---

### `app/routers/explore.py` (route, request-response + SSE) — EXTEND

**Analog:** itself (`explore.py:1-35`) for the POST; `admin_llm.py:19-24` / `stubs.py:29-34` for the small-router shape; the auth gate is `dependencies=[Depends(get_current_user)]` (`explore.py:21`).

**KEEP the POST (`explore.py:25-35`):** 202 + `run_service.create_run(... kind="explore" ...)` + `bg.add_task(run_explore, run.run_id, body.target_id)`.

**NET-NEW SSE route (RESEARCH:367-388):**
```python
from sse_starlette.sse import EventSourceResponse
@router.get("/explore/{run_id}/events")
async def explore_events(run_id: str, request: Request, user=Depends(get_current_user)):
    async def gen():
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(f"explore:{run_id}")
        try:
            async for msg in pubsub.listen():
                if await request.is_disconnected(): break
                if msg["type"] == "message":
                    yield {"event": "step", "data": msg["data"]}
        finally:
            await pubsub.unsubscribe(f"explore:{run_id}")
    return EventSourceResponse(gen())
```
EventSource can't set headers → cookie auth is the only auth; the route still carries `Depends(get_current_user)` (UI-SPEC streaming section). A run-404 is resolved via the EXISTING `GET /api/executions/{run_id}` (`executions.py:42-51`) before opening the stream (UI-SPEC "unknown run / 404").

---

### `shared/events/__init__.py` (model) — EXTEND

**Analog:** `RunStatusEvent` (`shared/events/__init__.py:33-40`). Add a versioned-like `ExploreProgressEvent` in the same Pydantic-v2 schemas-only style (NO broker, NO aio-pika here).
```python
class ExploreProgressEvent(BaseModel):
    run_id: str; step: int; pages_found: int; actions_taken: int
    current_url: str; current_title: str; screenshot_path: str | None
    feed_line: str; cost_usd: float; elapsed_s: float; stop_reason: str | None = None
```
Fields are the exact contract the UI-SPEC streaming section consumes. Add to `__all__` (`:42`).

---

### `app/main.py` (config) — MODIFY

**Analog:** itself (`main.py:53-77`). Add to lifespan after `init_neo4j()`: open the checkpointer pool + `await checkpointer.setup()` (NET-NEW), and `await close_*` in shutdown. Add `app.include_router(...)` only if a new SSE router module is split out (the extended `explore_router` already included at `:72`). Pattern: lifespan startup at `:53-58`, shutdown at `:60-62`, router includes at `:68-77`.

---

### `app/core/config.py` (config) — MODIFY

**Analog:** itself (`config.py:13-97`). Add a `checkpoint_dsn` derived from `database_url` (strip `+asyncpg` — Pitfall 1) and the explore budget defaults (max_steps/depth/revisits/wall_clock/saturation_window) as `Settings` fields with env aliases, mirroring the LLM-cap fields at `:54-66`. Per-run overrides come from `Target.budget_overrides` (`target.py:29`), clamped tighten-only (see budget.py).

---

### `alembic/versions/0005_*.py` (migration) — REUSE STYLE (only if explore columns needed)

**Analog:** `0004_runs_executions.py:1-56`. Chain `down_revision = '0004'`. **DO NOT** add LangGraph checkpoint tables here — those are owned by `checkpointer.setup()` (Pitfall 6). Only explore-specific columns you design (e.g. a `stop_reason` on `runs`) go through Alembic, using the exact `op.create_*` / `op.f` index style at `:23-48`.

---

### `app/(dashboard)/explore/[runId]/page.tsx` (component, streaming) — REUSE shell; NET-NEW EventSource

**Analog:** `(dashboard)/targets/page.tsx:1-142` (the `"use client"` + TanStack Query page shell) and the dashboard layout `(dashboard)/layout.tsx` (`<main className="p-6">`, QueryClientProvider, sonner). The full visual/state contract is in **04-UI-SPEC.md** (every state, copy, color token).

**REUSE (targets/page.tsx:31-39):** `"use client"`, `useQuery` for the mount-once 404 check (`GET /api/executions/{run_id}` via the api client), success-only sonner toasts.

**NET-NEW (UI-SPEC streaming section):** `new EventSource('/api/explore/${runId}/events')` — same-origin via the existing Next rewrite (`next.config.ts:13-20`) so the httpOnly cookie rides automatically (consistent with `lib/api/client.ts:1-16`). Parse each event into `ExploreProgressEvent`; cap feed to 200 rows; auto-scroll discipline; ≤150ms screenshot cross-fade; `eventSource.close()` on terminal `stop_reason`. ARIA live region `role="log" aria-live="polite"` on the feed.

---

### `lib/api/explore.ts` (utility, api client) — REUSE

**Analog:** `lib/api/targets.ts:1-112` — copy verbatim: zod schema at the boundary + `api.post`/`api.get` from `./client`. Add `startExplore(target_id): Promise<{run_id: string}>` → `api.post("/api/explore", {target_id})`. Note `budgetOverridesSchema` (`targets.ts:16-23`) already exists for Phase 4. The `ExploreProgressEvent` zod schema mirrors the backend Pydantic shape.

---

### `components/targets/targets-table.tsx` (MODIFY) + `components/app-sidebar.tsx` (MODIFY) — REUSE

**targets-table.tsx:174-204** — add an "Explore" `DropdownMenuItem` ABOVE "Edit" (UI-SPEC copy: "Explore"; disabled with tooltip "Activate this target to explore it" when `!is_active`). The `tooltip` component is already installed. Selecting it calls `startExplore`, fires the "Exploration started" toast, navigates to `/explore/{run_id}`.

**app-sidebar.tsx:26-31** — append `{ icon: Telescope/Radar, label: "Explorations", href: "/explore" }` to `NAV_ITEMS` (the file's own comment at `:22-25` says later phases append "Explorations"). Active state via `pathname.startsWith` (`:62`).

---

### Tests — REUSE fixtures

**Unit (8 files — `test_fingerprint.py`, `test_risk.py`, `test_convergence.py`, `test_locators.py`, `test_safety.py`, `test_auth_detect.py`, `test_workflow_detect.py`, `test_explore_events.py`):**
**Analog:** `tests/unit/conftest.py:30-77` (the `fake_chat_model` / `FakeChatModel` mock of `init_chat_model`) and `:80-162` (the autouse redis-isolation + `test:llm:` prefix). Extend `fake_chat_model` into a `fake_gateway` returning scripted action indices for the deterministic two-run convergence test (RESEARCH:355,529). Pure modules (fingerprint/risk/budget/locators) need NO stack, NO spend.

**Functional (`test_explore_discovery.py` graph, `test_explore_live.py` live_llm):**
**Analog:** `tests/functional/test_explore.py:1-65` — copy verbatim: `pytestmark = [pytest.mark.functional, pytest.mark.graph]`, in-cluster `http://saucedemo:80`, unique target name per test, `poll_until_terminal` (NEVER assert after 202), assert nodes only for THIS `run_id`. The live convergence proof is `live_llm`-marked (real spend, phase-gate only).

---

## Shared Patterns

### LLM gateway — the ONLY LLM path (apply to `nodes.py` decide)
**Source:** `app/services/llm_gateway.py:291-302` (the `complete()` signature). RESEARCH:421-431.
```python
result = await llm_gateway.complete(
    db, messages,
    operation_type="explore.decide",   # or "explore.perceive"
    run_id=state["run_id"],            # binds the per-run token budget (D-06)
    temperature=0,                      # deterministic + cacheable
    max_tokens=256,
)
```
NEVER call `init_chat_model` directly from the explorer (CLAUDE.md; `llm_gateway.py:44-45`). A `BudgetExceeded`/`KillSwitchActive` from the gateway (`llm_gateway.py:86,99`) is caught and ends the run gracefully.

### Untrusted-observation delimiting (apply to every decide prompt)
**Source:** RESEARCH Pattern 4 (lines 239-247). Page-derived text is DATA, never instructions — wrap in `<<<UNTRUSTED_OBSERVATION>>> ... <<<END>>>`; the LLM returns ONLY an action index. Defense-in-depth with the deterministic `risk.py` gate (EXPL-08).

### Managed Neo4j write + read-back (apply to `nodes.py` persist + any KG write)
**Source:** `explorer.py:85-100,148-149`. `execute_write` (managed, commits on success) + `RETURN count(*)`; `if written < 1: raise` → fail the run. Parameterized Cypher only. This phase MERGEs on fingerprint as a real-but-minimal seam; the canonical single-writer KG is Phase 5 (RESEARCH:357-363).

### Lifespan singleton resource (apply to `checkpointer.py`)
**Source:** `neo4j_driver.py:25-63` / `redis_client.py:18-49`. `_module_global` + `init_*`/`close_*`/`get_*`, opened in `main.py` lifespan (`:53-62`), lazy-safe for unit tests.

### Router-level auth gate (apply to extended `explore.py` + SSE)
**Source:** `explore.py:17-22`, `admin_llm.py:19-24`, `executions.py:20-24`. `dependencies=[Depends(get_current_user)]` on the `APIRouter(prefix="/api", ...)`.

### Same-origin proxy + cookie auth (apply to the live page + EventSource)
**Source:** `next.config.ts:13-20` (the `/api/:path*` rewrite) + `lib/api/client.ts:1-16` (same-origin, cookies ride automatically, never reads token values). EventSource hits the proxied `/api/explore/{runId}/events` path → cookie auth works with zero token handling.

### zod-at-the-boundary API client (apply to `lib/api/explore.ts`)
**Source:** `lib/api/targets.ts:29-99`. zod parse on every response; `api.get/post` from `./client`.

### Pydantic-v2 schemas-only event contract (apply to `shared/events`)
**Source:** `shared/events/__init__.py:1-43`. No broker/transport here; just the versioned message shape.

---

## NET-NEW Patterns Summary (closest reference + RESEARCH pitfall tie)

| NET-NEW Pattern | Closest in-repo reference | RESEARCH pitfall / section |
|-----------------|---------------------------|-----------------------------|
| LangGraph raw StateGraph + compile(checkpointer) | RESEARCH Pattern 1 (no in-repo) | Anti-pattern: hand-rolled while-loop; CLAUDE.md raw StateGraph |
| AsyncPostgresSaver (psycopg3, name `psycopg`; `.setup()` OUTSIDE Alembic; coexists with asyncpg) | `neo4j_driver.py`/`redis_client.py` lifespan singleton | Pitfall 1 (DSN collision), Pitfall 6 (Alembic), `:81/:455` (package name) |
| Redis pub/sub for SSE (vs GET/SET) + sse-starlette EventSourceResponse | `redis_client.py` + `llm_gateway.py` redis usage | SSE section (`:365-388`); `redis_client.py` flagged NET-NEW usage |
| aria_snapshot DOM/aria compaction | none | Pitfall 4 (aria_snapshot ≠ locators); D-01 |
| Structural-skeleton fingerprint (the experimental unknown) | `explorer._page_key:43-49` (the key it replaces) | Fingerprint section (`:271-295`); A3 |
| Deterministic risk classifier + origin allowlist + untrusted delimiting | `run_service._validate_status:32-39` (pure guard) | Pitfall 5; Pattern 4; D-03/D-04 |
| Locator-chain extraction (data-testid→aria-label→role→text→xpath) | none | Locator section (`:297-314`); note SauceDemo uses `data-test` |
| Budget/loop/convergence/saturation controller (pure) | `llm_gateway._effective_caps:239-261` (tighten-only clamp) | Convergence section (`:340-355`); D-05/D-06 |
| storageState capture/reuse + logout→relogin recovery | `explorer.py:114-125` (login + decrypt) | Auth section (`:316-321`); EXPL-02 |

---

## No Analog Found (planner uses RESEARCH patterns directly)

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `explorer/graph.py` | service | event-driven | No StateGraph exists; use RESEARCH Pattern 1 |
| `explorer/perception.py` | utility | transform | No aria_snapshot usage exists; RESEARCH Pattern 3 |
| `explorer/actions.py` | utility | transform | No constrained-menu enumeration exists; RESEARCH Pattern 3 |
| `explorer/locators.py` | utility | transform | No locator-chain extraction exists; RESEARCH locator section |

All four are pure-or-near-pure modules with RESEARCH code examples; the surrounding invariants (test fixtures, write-back, gateway) DO have analogs above.

---

## Metadata

**Analog search scope:** `apps/api/app/{services,routers,core,models,schemas,db}`, `apps/api/alembic/versions`, `apps/api/tests/{unit,functional}`, `apps/web/{app,components,lib}`, `shared/events`, `infra`.
**Files scanned (read in full):** explorer.py, explore.py, neo4j_driver.py, redis_client.py, run_service.py, main.py, llm_gateway.py, target.py, config.py, db/session.py, schemas/run.py, executions.py, admin_llm.py, stubs.py, 0004_runs_executions.py, shared/events/__init__.py, tests/unit/conftest.py, tests/functional/test_explore.py, web targets/page.tsx, lib/api/client.ts, lib/api/targets.ts, app-sidebar.tsx, targets-table.tsx, (dashboard)/layout.tsx, next.config.ts.
**Migration chain head:** `0004` → new explore migration (if any) is `0005`.
**Pattern extraction date:** 2026-06-15
```