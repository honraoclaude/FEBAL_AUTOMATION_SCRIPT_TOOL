# Phase 3: Tracer Bullet — Minimal End-to-End Loop - Pattern Map

**Mapped:** 2026-06-14
**Files analyzed:** 21 (new) + 2 (modified)
**Analogs found:** 19 with codebase analog / 23 (4 are net-new patterns with closest-reference only)

> Read order for the planner: this file assigns each new file an analog + concrete excerpts to copy.
> Excerpts cite real line numbers in the verified Phase 1-2 codebase. The 4 net-new patterns
> (Playwright-in-BackgroundTask, subprocess spec runner, Jinja2+gherkin, status state machine)
> have NO direct analog — their closest references and the RESEARCH pitfalls are flagged inline.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `apps/api/app/core/neo4j_driver.py` | provider (driver singleton) | request-response | `app/core/redis_client.py` | exact (lifespan singleton) |
| `apps/api/app/main.py` *(modify)* | config/wiring | — | `app/main.py` (self) | self — extend lifespan + includes |
| `apps/api/app/services/explorer.py` | service | event-driven (BackgroundTask) + file-I/O (browser) | `app/services/target_service.py` (service shape) + `health.py` (async resource use) | role-match; **net-new** crawl-in-task |
| `apps/api/app/services/generation.py` | service | transform (graph→LLM→file) | `app/services/llm_gateway.py` (gateway call) + `target_service.py` (service shape) | role-match; **net-new** Jinja2+gherkin |
| `apps/api/app/services/execution.py` | service | event-driven (subprocess) | `infra/scripts/reset_target.py` (subprocess+poll) | role-match; **net-new** async subprocess |
| `apps/api/app/services/run_service.py` | service | CRUD (status lifecycle) | `app/services/target_service.py` | exact (async-session-first-arg CRUD) |
| `apps/api/app/routers/explore.py` | router | request-response (202+poll) | `app/routers/targets.py` | role-match (router-auth + Depends) |
| `apps/api/app/routers/generate.py` | router | request-response | `app/routers/targets.py` | role-match |
| `apps/api/app/routers/execute.py` | router | request-response (202+poll) | `app/routers/targets.py` | role-match |
| `apps/api/app/routers/executions.py` | router | CRUD-read (GET list/by-id) | `app/routers/targets.py` (list/get + 404) | exact |
| `apps/api/app/routers/stubs.py` | router | request-response (501) | `app/routers/admin_llm.py` (small router) | role-match |
| `apps/api/app/models/run.py` | model | CRUD | `app/models/llm_usage.py` + `app/models/target.py` | exact (mapped_column style) |
| `apps/api/app/schemas/run.py` | schema | — | `app/schemas/target.py` + `app/schemas/llm.py` | exact (pydantic v2 style) |
| `apps/api/alembic/versions/0004_runs_executions.py` | migration | — | `alembic/versions/0003_llm_usage.py` | exact (chain down_revision='0003') |
| `shared/events/__init__.py` | schema (message) | pub-sub (schema-only) | `app/schemas/llm.py` (pydantic v2) | role-match |
| `infra/scripts/graph_mode.py` | utility (ops script) | event-driven (compose orchestration) | `infra/scripts/reset_target.py` | exact (stdlib subprocess+poll+exit-codes) |
| `infra/docker-compose.yml` *(modify)* | config | — | `infra/docker-compose.yml` (self, neo4j block) | self — trim dormant neo4j |
| `.env.example` + api env block *(modify)* | config | — | compose `api.environment` (self) | self — add `NEO4J_*` |
| `apps/api/tests/functional/test_explore.py` | test | — | `tests/functional/test_targets.py` | role-match (live-HTTP + new poll helper) |
| `apps/api/tests/functional/test_generation.py` | test | — | `tests/functional/test_targets.py` + `tests/unit/conftest.py` (fake_chat_model) | role-match |
| `apps/api/tests/functional/test_execute.py` | test | — | `tests/functional/test_targets.py` | role-match |
| `apps/api/tests/functional/test_surface.py` | test | — | `tests/functional/test_targets.py` (test_requires_auth shape) | role-match |
| `apps/api/tests/functional/test_run_thread.py` | test | — | `tests/functional/test_targets.py` | role-match |
| `apps/api/tests/conftest.py` *(modify)* | test fixture | — | `tests/conftest.py` (self) + `tests/unit/conftest.py` (host-URL rewrite) | self — add neo4j fixture + poll helper |

---

## Pattern Assignments

### `apps/api/app/core/neo4j_driver.py` (provider, lifespan singleton)

**Analog:** `app/core/redis_client.py` — EXACT shape. Copy the module-global + `init/close/get` triad verbatim, swapping `redis.from_url` for `AsyncGraphDatabase.driver`.

**Module-global singleton + init/close/get** (`redis_client.py` lines 18-49):
```python
_client: redis.Redis | None = None

def init_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client

async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None

def get_redis() -> redis.Redis:
    if _client is None:
        return init_redis()
    return _client
```
Neo4j equivalent: `_driver: AsyncDriver | None`; `init_neo4j()` → `AsyncGraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))`; `close_neo4j()` → `await _driver.close()`; `get_neo4j()` → lazy-open like `get_redis()`. The driver is a **pool** — never open one per request (RESEARCH Pattern 1 / Anti-pattern). `get_neo4j()` lazy-open mirrors `get_redis()` so a unit test importing the service outside the lifespan never gets `None`.

**Config additions** (`app/core/config.py` lines 20-43 show the typed-field style): add `neo4j_uri: str`, `neo4j_user: str`, `neo4j_password: str` (or parse `NEO4J_AUTH`). Follow the inline `# env NEO4J_*` comment convention. Provider-key optionality pattern (lines 39-43) is the model for any optional field.

---

### `apps/api/app/main.py` (modify — lifespan + router includes)

**Analog:** self. The lifespan already does the exact `init_redis()` / `close_redis()` dance.

**Lifespan** (`main.py` lines 46-53) — add neo4j init/close symmetrically:
```python
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    init_redis()       # ← add: init_neo4j()
    await seed_admin()
    yield
    await close_redis()  # ← add: await close_neo4j()
    await engine.dispose()
```
Place `init_neo4j()` next to `init_redis()`; `await close_neo4j()` next to `await close_redis()` before `engine.dispose()`.

**Model import for Alembic/Base discovery** (line 15): `from app.models.llm_usage import LLMUsage  # noqa: F401`. Add the same `# noqa: F401` import for `app.models.run` (Run, Execution) so `Base.metadata` sees the new tables.

**Router includes** (lines 17-20, 59-62): import each new router `as X_router` and `app.include_router(...)`. Add explore/generate/execute/executions/stubs routers following the existing block.

---

### `apps/api/app/services/run_service.py` (service, CRUD status lifecycle)

**Analog:** `app/services/target_service.py` — EXACT service-layer conventions.

**Conventions to copy** (`target_service.py`):
- Async function, `db: AsyncSession` as first arg (lines 44, 73, 80, 123).
- Typed module-level exceptions, not HTTPException (lines 21-26): `class TargetNotFoundError(Exception)`. Define `RunNotFoundError` similarly; routers translate to 404 (see router section).
- `select(...)` + `await db.scalar(...)` read; `db.add(...)` + `await db.commit()` + `await db.refresh(...)` write (lines 63-70, 80-81).

```python
async def get_target(db: AsyncSession, target_id: int) -> Target | None:
    return await db.scalar(select(Target).where(Target.id == target_id))
```
Build `create_run(db, kind, target_id) -> Run` (status="queued"), `set_status(db, run_id, status, error=None)`, `finish_execution(db, execution_id, status, exit_code, output)`, `get_run/list_executions` on this exact shape.

**Status state machine** (NET-NEW — closest ref is the typed-exception + commit discipline above). RESEARCH Code Example: `VALID = {"queued","running","passed","failed"}`. Keep it a tiny dict/set guard inside `set_status`; do NOT build an abstraction.

---

### `apps/api/app/services/explorer.py` (service, BackgroundTask + Playwright — **NET-NEW**)

**No direct analog.** Closest references:
- Service-layer + decrypt surface → `target_service.get_decrypted_credentials` (lines 123-128) — the ONLY decrypt path; call it, never re-implement Fernet:
  ```python
  async def get_decrypted_credentials(db, target_id) -> tuple[str, str]:
      target = await get_target(db, target_id)
      if target is None:
          raise TargetNotFoundError(target_id)
      return decrypt(target.encrypted_username), decrypt(target.encrypted_password)
  ```
- Fresh-session discipline → `main.py seed_admin` (lines 31-32) shows `async with SessionLocal() as session:` opened OUTSIDE a request.
- Async external-resource lifecycle → `health.py` (lines 25-37) shows `async with engine.connect()` open/use/close inside an async handler.
- Reuse the lifespan driver → `get_neo4j()` (the pool); open a fresh **session** per write, not a fresh driver.

**PITFALL 2 (RESEARCH) — fresh session, never the request's:** the BackgroundTask runs AFTER the response; `Depends(get_db)` is already closed. The task MUST open `async with SessionLocal() as db:` (RESEARCH Pattern 3). Reusing the request session → `Cannot operate on a closed database` / `Event loop is closed`. The neo4j driver + redis client ARE safe to reuse (pools).

**Cypher MERGE — parameterized only (Security: Cypher injection / Tampering):** use `$key`/`$url` params (RESEARCH Pattern 2), never f-string page text into the query. Mark the write a **tracer seam** in a comment (Phase 5 replaces it with the single-writer service). PLAT-07: never write decrypted creds into Neo4j nodes.

---

### `apps/api/app/services/generation.py` (service, transform — **NET-NEW** templating, gateway is exact)

**The LLM path is EXACT** — route through `llm_gateway.complete()` (the ONLY LLM path, D-07).

**Gateway call signature** (`llm_gateway.py` lines 291-302):
```python
async def complete(
    db: AsyncSession, messages, *,
    operation_type: str, run_id: str | None = None,
    model: str | None = None, temperature: float = 0,
    max_tokens: int, no_cache: bool = False,
    run_budget_overrides: dict | None = None,
) -> LLMResult:
```
Call with `operation_type="generate-bdd"` / `"generate-scripts"` and the slice's `run_id` (D-07). Returns `LLMResult` (`schemas/llm.py` lines 16-29); the generated text is `result.content`. Budgets/kill-switch/caching/ledger come free. Generation tests requiring a real provider → mark `live_llm`; deterministic parts use the `fake_chat_model` fixture.

**NET-NEW (no codebase analog):**
- **Jinja2 skeleton + LLM slots** — LLM fills selectors/steps only; Jinja owns structure (RESEARCH Pattern + Anti-pattern: never let the LLM emit the whole `.py`). PITFALL 5: constrain slots to selectors the crawl OBSERVED (`#user-name`, `#password`, `#login-button`, `.inventory_list`), not LLM-invented ones.
- **gherkin-official validation gate** (RESEARCH Pattern 5): `Parser().parse(TokenScanner(text))` before writing the `.feature`; reject/re-ask on `CompositeParserException`.
- **File write under `workspaces/<run_id>/`** keyed by run_id (gitignored). Record `executions.spec_path` for the run-id-derived subprocess argv.

Service shape (async, `db` first-arg, typed exceptions) still follows `target_service.py`.

---

### `apps/api/app/services/execution.py` (service, subprocess runner — **NET-NEW**, ref reset_target.py)

**Closest analog:** `infra/scripts/reset_target.py` — subprocess discipline + exit-code contract.

**Subprocess safety to copy** (`reset_target.py` lines 80-108, esp. the T-01-26 note lines 22-28, 85):
- argv as a **list**, NEVER `shell=True` (lines 87-94).
- Handle `FileNotFoundError` for the binary (lines 96-99).
- Branch on `result.returncode` (lines 100-105).
- **Security (Elevation):** `spec_path` is **registry/run_id-derived, never user-input** — mirror reset_target's "name is only a dict key, never interpolated into argv" rule.

**NET-NEW vs reset_target:** use **async** `asyncio.create_subprocess_exec("uv","run","pytest", spec_path, ...)` with `cwd="apps/api"` (RESEARCH Pattern 4), capture exit code + stdout, then open a fresh `SessionLocal()` to write the executions row.

**PITFALL 3 (RESEARCH):** the generated spec uses the SYNC Playwright API and CANNOT run in-process inside the API's asyncio loop. Subprocess ONLY — never `pytest.main()`.

---

### `apps/api/app/routers/{explore,generate,execute,executions}.py` (routers, request-response)

**Analog:** `app/routers/targets.py` — EXACT router conventions.

**Router-level auth gate** (`targets.py` lines 16-21) — copy verbatim per router:
```python
router = APIRouter(
    prefix="/api/...",
    tags=["..."],
    dependencies=[Depends(get_current_user)],   # no route reachable unauthenticated
)
```
Security V2: all new REAL endpoints carry this gate (no new auth code).

**404/409 translation** (`targets.py` lines 27-49) — service raises typed exception, router catches → HTTPException:
```python
target = await target_service.get_target(db, target_id)
if target is None:
    raise HTTPException(status_code=404, detail=_NOT_FOUND)
```
`executions.py` GET list/by-id is the closest 1:1 to `list_targets` (lines 36-49). For `/explore` + `/execute`: return **202** + `{"run_id", "status":"queued"}` and `bg.add_task(...)` (RESEARCH Pattern 3 router side) — net-new vs targets' synchronous 201, but the Depends/auth/translation frame is identical.

**Input validation (V5):** Pydantic request models per endpoint (`ExploreRequest{target_id:int}`, etc.) — see schema section.

---

### `apps/api/app/routers/stubs.py` (router, 501 honest contracts)

**Analog:** `app/routers/admin_llm.py` — small router with router-level auth + explicit status codes.

**Router frame** (`admin_llm.py` lines 19-24): same `APIRouter(prefix=..., dependencies=[Depends(get_current_user)])`.

**501 with documented OpenAPI contract** (RESEARCH Code Example — honest stub; admin_llm's explicit `status_code=` per route is the closest existing style):
```python
@router.post("/api/heal", status_code=501,
    summary="Self-heal a failed locator (Phase 8)",
    responses={501: {"description": "Documented contract; behavior lands in Phase 8"}})
async def heal(body: HealRequest) -> None:
    raise HTTPException(status_code=501, detail="heal: not implemented (Phase 8)")
```
Define a request/response Pydantic model per stub (`/heal /create-defect /flows /coverage /dashboard`) so the OpenAPI schema is COMPLETE. **Never fabricate results** — 501 only (CONTEXT Claude's Discretion + RESEARCH Anti-pattern).

---

### `apps/api/app/models/run.py` (model, CRUD)

**Analog:** `app/models/llm_usage.py` — EXACT `Mapped`/`mapped_column` style (+ `target.py` for nullable/JSON).

**Model style** (`llm_usage.py` lines 19-33):
```python
class LLMUsage(Base):
    __tablename__ = "llm_usage"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    ...
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
```
Build `Run` + `Execution` (RESEARCH Code Example, models block) on this shape: `run_id: String(64) index`, `status: String(16) server_default="queued"`, `error/output: nullable`, `exit_code: Integer nullable`, `created_at: DateTime(timezone=True) server_default=func.now()`. Nullable + `Text` columns: see `target.py` line 29 (`nullable=True`) for the convention. `from app.db.base import Base` (line 16).

---

### `apps/api/app/schemas/run.py` + `shared/events/__init__.py` (pydantic v2 schemas)

**Analog:** `app/schemas/target.py` + `app/schemas/llm.py` — EXACT pydantic v2 style.

**Response (ORM-readable) style** (`schemas/llm.py` lines 16-29 / `target.py` lines 51-65):
```python
class LLMResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    content: str | None
    run_id: str
    operation_type: str
```
Use `model_config = ConfigDict(from_attributes=True)` on Run/Execution **response** models (read straight from the ORM row, like `TargetResponse.model_validate(target)` in the router). **Request** models use `Field(...)` bounds like `CredentialsIn` (`target.py` lines 14-18, `min_length=1`); `ExploreRequest.target_id: int`.

**`shared/events/`** (D-05 — schemas only, NO broker): plain `BaseModel` message schemas `ExploreJob`/`ExecuteJob`/`RunStatusEvent` (RESEARCH Code Example). `uuid.uuid4().hex` default-factory for `run_id` mirrors the gateway's `run_id = run_id or uuid.uuid4().hex` (`llm_gateway.py` line 320). This is the FIRST content in `shared/events/` (README line 5 — "Populated in Phase 3").

---

### `apps/api/alembic/versions/0004_runs_executions.py` (migration)

**Analog:** `alembic/versions/0003_llm_usage.py` — EXACT migration style; chain after 0003.

**Revision chaining** (`0003_llm_usage.py` lines 15-18):
```python
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
```
New file: `revision='0004'`, `down_revision='0003'`. **PITFALL — chained down_revision:** must point at `'0003'` (the current head), not `'0002'`.

**Table + index DDL** (lines 24-39): `op.create_table(...)` with `sa.Column('run_id', sa.String(length=64), ...)`, `sa.Numeric`/`sa.Integer`/`sa.Boolean(server_default='false')`, `sa.DateTime(timezone=True), server_default=sa.text('now()')`; `op.create_index(op.f('ix_..._run_id'), ...)` for indexed columns. `downgrade()` drops indexes then table (lines 43-49).

---

### `infra/scripts/graph_mode.py` (utility, compose orchestration — ref reset_target.py)

**Analog:** `infra/scripts/reset_target.py` — EXACT scripted-helper shape.

**Copy verbatim:**
- Module docstring stating the exit-code contract (lines 10-29).
- Compose file resolved relative to `__file__` so cwd doesn't matter (line 42): `COMPOSE_FILE = (Path(__file__).resolve().parent.parent / "docker-compose.yml").resolve()`.
- **Stdlib only** — no third-party imports, runs on host Python without uv (lines 18-19, 31-38).
- Health poll loop (`_wait_for_health`, lines 60-77): `time.monotonic()` deadline + `urllib.request.urlopen` + `time.sleep(interval)`.
- argv lists, no `shell=True`, `FileNotFoundError` guard, returncode branch (lines 87-108).
- Exit codes `0/1/2` via `main()` → `SystemExit` (lines 134-145).

**PITFALL 4 (RESEARCH) — mandatory ordering (memory math, D-03):** `graph_mode.py` MUST: (1) `docker compose stop web`, (2) `docker compose --profile graph up -d neo4j` + poll-until-healthy, (3) run work, (4) `docker compose start web`. Starting neo4j while web is up → WSL OOM. Build each docker argv as a list of registry/literal constants (reset_target's T-01-26 rule).

---

### `infra/docker-compose.yml` (modify — trim dormant neo4j) + `.env.example`

**Analog:** self — the neo4j block at lines 119-123 (currently `image: neo4j:2025`, `profiles: [graph]`, `mem_limit: 2g`).

**Trim to (D-02 + RESEARCH Pitfall 1 exact env names):** `mem_limit: 1g`; add `environment:` `NEO4J_AUTH`, `NEO4J_server_memory_heap_initial__size: 512m`, `NEO4J_server_memory_heap_max__size: 512m` (**DOUBLE underscore** on `max__size`), `NEO4J_server_memory_pagecache_size: 256m` (single — no literal underscore); ports `7687`/`7474`; healthcheck (wget on 7474). Follow the existing healthcheck shape — saucedemo (lines 107-115) is the closest in-file pattern (wget `-q -O /dev/null`).

**api env block** (lines 47-62): add `NEO4J_URI: bolt://neo4j:7687`, `NEO4J_USER`, `NEO4J_PASSWORD` to the `api.environment` map. **PITFALL 6 + 02-01 deviation #2:** the api enumerates env explicitly (does NOT pass whole `.env`) — omitting these → `Settings()` fails → api unhealthy. Mirror the `DATABASE_URL`/`REDIS_URL` compose-host (`neo4j`) vs hybrid-host (`localhost`) split. **Do NOT** add `depends_on: neo4j` (RESEARCH Pitfall 6 / A6) — keeps plain `up` working; explore tests activate the profile via `graph_mode`. `.env.example` gets the same `NEO4J_*` keys (Runtime State Inventory).

---

### Tests: `tests/functional/test_{explore,generation,execute,surface,run_thread}.py` + `tests/conftest.py`

**Analog:** `tests/functional/test_targets.py` (live-HTTP shape) + `tests/unit/conftest.py` (fake_chat_model + host-URL rewrite).

**Live-HTTP functional shape** (`test_targets.py`): `pytestmark = pytest.mark.functional` (line 16); `authed_client`/`client` fixtures (from `tests/conftest.py` lines 55-72); unique names per test, never assert global counts (lines 9-10, 21-22).

**Auth-gate test pattern** for `test_surface.py` (`test_targets.py` lines 154-170 `test_requires_auth`): assert 401 on each real endpoint unauthenticated; assert 501 on each stub; assert `shared/events` schemas importable.

**Mocked-gateway determinism** for `test_generation.py` (`tests/unit/conftest.py` lines 40-77 `fake_chat_model`): patches `gateway.init_chat_model`; `.set(content=..., usage_metadata=...)` shapes the response. Use it for gherkin-validation/Jinja-render/file-write determinism (zero spend); mark real-provider runnable-spec `live_llm`.

**Host-URL rewrite** for the new `neo4j_session` fixture (`tests/unit/conftest.py` lines 110-111 rewrite redis host; `tests/conftest.py` lines 30-35 rewrite DATABASE_URL): the test driver connects to `bolt://localhost:7687` (host side), asserting `MATCH (a:Page)-[:NavigatesTo]->(b:Page) WHERE a.run_id=$rid RETURN count(*)` ≥ 1.

**NET-NEW test mechanics (no analog):**
- **Poll-until-terminal helper** (RESEARCH Validation): after a 202, poll `GET /executions/{run_id}` until `status in {passed,failed}` with bounded timeout — mirror `reset_target.py`'s `_wait_for_health` deadline loop (lines 60-77). NEVER assert immediately after the 202.
- **`graph` marker** — register in `pyproject.toml` markers list (lines 46-50, alongside `functional`/`e2e`/`live_llm`): `"graph: needs the neo4j graph profile active (run under graph_mode)"`.

---

## Shared Patterns

### Authentication (V2)
**Source:** `app/routers/targets.py` lines 16-21 (router-level `dependencies=[Depends(get_current_user)]`)
**Apply to:** explore, generate, execute, executions, stubs routers — every new REAL + stub route. No new auth code.

### Service layer (async, db-first-arg, typed exceptions)
**Source:** `app/services/target_service.py` lines 21-26 (typed exceptions), 44-70 (commit/refresh), 123-128 (single decrypt surface)
**Apply to:** run_service, explorer, generation, execution services. Routers translate typed exceptions to HTTPException.

### Lifespan-managed pooled resource
**Source:** `app/core/redis_client.py` lines 18-49 + `app/main.py` lines 46-53 wiring
**Apply to:** the new neo4j driver. Open once at startup, close at shutdown, reuse the pool across requests AND BackgroundTasks.

### Fresh session in background work
**Source:** `app/main.py seed_admin` lines 31-32 (`async with SessionLocal() as session:` outside a request) + `app/db/session.py` lines 13-19
**Apply to:** explorer + execution BackgroundTasks. NEVER reuse the request's `get_db` session (RESEARCH Pitfall 2).

### Metered LLM (the only LLM path)
**Source:** `app/services/llm_gateway.py` `complete()` lines 291-302
**Apply to:** generation service (`generate-bdd`, `generate-scripts`) — pass `operation_type` + `run_id`. Never a direct provider SDK call.

### Subprocess safety (argv list, no shell, exit codes)
**Source:** `infra/scripts/reset_target.py` lines 22-28 (T-01-26 note), 87-108 (argv + returncode + FileNotFoundError)
**Apply to:** graph_mode.py and the /execute subprocess runner. `spec_path` is run_id/registry-derived, never user input.

### Pydantic v2 schema style
**Source:** `app/schemas/llm.py` lines 16-29 (`ConfigDict(from_attributes=True)`) + `app/schemas/target.py` lines 14-18 (`Field` bounds)
**Apply to:** schemas/run.py (request + ORM-readable response models) and shared/events message schemas.

### Migration chaining
**Source:** `alembic/versions/0003_llm_usage.py` lines 15-18
**Apply to:** 0004 — `down_revision='0003'`; `op.create_table` + `op.create_index` + symmetric downgrade.

### Live-HTTP functional test
**Source:** `tests/conftest.py` lines 55-72 (`client`/`authed_client`) + `tests/functional/test_targets.py` lines 16, 154-170
**Apply to:** all 5 new functional test files. Mocked-gateway determinism reuses `tests/unit/conftest.py` `fake_chat_model`.

---

## No Analog Found (Net-New Patterns)

| Pattern | New File(s) | Closest Reference | RESEARCH Pitfall to thread |
|---------|-------------|-------------------|----------------------------|
| Async Playwright crawl INSIDE a FastAPI BackgroundTask (event-loop + fresh-session lifecycle) | `services/explorer.py` | `health.py` async resource use + `main.py seed_admin` fresh session + lifespan neo4j driver | **Pitfall 2** — fresh `SessionLocal()`, never the request session |
| Subprocess execution of a generated pytest-playwright spec (capture pass/fail) | `services/execution.py` | `infra/scripts/reset_target.py` subprocess+exit-code | **Pitfall 3** — sync-Playwright spec MUST run via subprocess, never in-process |
| Jinja2 skeleton render + gherkin-official validation of LLM output | `services/generation.py` | no templating/validation in codebase; gateway call is the only reused part | **Pitfall 5** — constrain LLM slots to OBSERVED selectors |
| FastAPI BackgroundTasks + queued→running→passed/failed status machine | `routers/explore.py`, `routers/execute.py`, `services/run_service.py` | `targets.py` router frame (synchronous) + typed-exception/commit discipline | **Pitfall 4** — graph_mode stop-web-BEFORE-start-neo4j (memory math) |

**Net-new infra env trap:** Neo4j Docker memory env-var underscore-doubling (`NEO4J_server_memory_heap_max__size`) — **Pitfall 1**, no codebase precedent; closest is the existing `ES_JAVA_OPTS` env on elasticsearch (compose line 135).

---

## Metadata

**Analog search scope:** `apps/api/app/{core,services,routers,models,schemas,db}/`, `apps/api/alembic/versions/`, `apps/api/tests/{,functional,unit}/`, `infra/{docker-compose.yml,scripts/}`, `shared/events/`
**Files scanned:** 27 (read 21 in full; verified pyproject markers + db/base)
**Pattern extraction date:** 2026-06-14
