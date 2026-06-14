# Phase 3: Tracer Bullet — Minimal End-to-End Loop - Research

**Researched:** 2026-06-13
**Domain:** End-to-end vertical slice — Neo4j async writes, deterministic Playwright crawl, LLM-gateway-backed code generation, in-process async job model, spec execution
**Confidence:** HIGH (stack is CLAUDE.md-locked and registry-verified; integration mechanics verified against official docs + existing codebase)

## Summary

Phase 3 is a deliberately thin end-to-end slice: `POST /explore` runs a deterministic Playwright login+crawl against self-hosted SauceDemo and writes minimal `Page`/`NavigatesTo` nodes to a memory-trimmed local Neo4j; `POST /generate-bdd` and `POST /generate-scripts` route through the existing `llm_gateway.complete()` to emit one Gherkin scenario and one runnable pytest-playwright spec from the explored graph; `POST /execute` runs that spec via subprocess and lands a result row in Postgres retrievable via `GET /executions`. All 10 PLAT-02 endpoints exist — real where the slice covers them, honest 501 stubs with documented OpenAPI contracts elsewhere — and `shared/events/` gets Pydantic message schemas (no broker). A single `run_id` threads the whole slice.

The work is overwhelmingly *integration*, not novel algorithm design. Every heavy decision is locked in `03-CONTEXT.md` (D-01..D-08) and the stack is fixed in `CLAUDE.md`. The genuine technical risks are four mechanical ones: (1) Neo4j Docker memory-env-var naming (the underscore-doubling rule is a silent-failure trap), (2) running async Playwright + async Neo4j/DB writes **inside** a FastAPI BackgroundTask without reusing the request's DB session, (3) making the LLM-generated spec reliably *runnable* against SauceDemo (Jinja2 skeleton + narrow LLM slots + gherkin validation), and (4) the container memory choreography (`graph_mode` helper must stop `web` BEFORE starting `neo4j` to fit the 3 GB WSL cap).

**Primary recommendation:** Build three dependency-ordered slices — (A) Neo4j up + `graph_mode` helper + deterministic explore → Page/NavigatesTo + the `runs`/`executions` model + `GET /executions`; (B) generate-bdd + generate-scripts via the gateway → validated artifacts under `workspaces/<run_id>/`; (C) `/execute` runs the spec → result row, plus the full 10-endpoint surface (501 stubs) and `shared/events/` schemas. Add the new packages (`neo4j`, `pytest-bdd`, `gherkin-official`; `Jinja2` likely transitive) behind a plan-time legitimacy checkpoint.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Deterministic explore (login + crawl) | API / Backend (BackgroundTask) | Browser (Playwright Chromium) | Explorer is server-side orchestration driving a headless browser; no client tier involved |
| Page/NavigatesTo graph writes | Database / Storage (Neo4j) | API service (Cypher MERGE) | Tracer-seam direct driver writes from the service layer (explicitly NOT the Phase-5 single-writer) |
| run/execution status persistence | Database / Storage (Postgres) | API service (SQLAlchemy) | Status lifecycle + result rows are relational, chain after Alembic 0003 |
| BDD + spec generation | API / Backend (llm_gateway) | LLM provider (via gateway only) | D-07: generation is the right place to exercise the metered gateway end-to-end |
| Artifact storage (.feature + .py) | Filesystem (`workspaces/<run_id>/`) | API service | Generated data, gitignored; keyed by run_id for traceability |
| Spec execution | API / Backend (subprocess pytest) | Browser (Playwright) | `/execute` shells out to `uv run pytest`, captures exit code → executions row |
| Job dispatch (202 + run_id, poll) | API / Backend (BackgroundTasks) | — | In-process now; Phase 7 swaps to RabbitMQ workers with no API-contract change (D-04) |
| Queue message schemas | shared/events (Pydantic) | — | Schemas only, no broker (D-05); the contract the in-process path produces and Phase-7 publishes |

## Standard Stack

All core runtime libraries are already installed (Phase 1-2). Phase 3 adds three Python packages, all named in the authoritative `CLAUDE.md` stack tables.

### Core (already installed — verified in `apps/api/pyproject.toml` / `uv pip list`)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.136.* | Routers + `BackgroundTasks` for async-style jobs | The decided framework; `BackgroundTasks` is the in-process job mechanism (D-04) [VERIFIED: pyproject.toml] |
| sqlalchemy[asyncio] | 2.0.* | `runs`/`executions` async ORM models | Locked async ORM; `async_sessionmaker`/`AsyncSession` pattern [VERIFIED: pyproject.toml] |
| alembic | 1.18.* | New migrations chain after `0003` | Schema migration tool; async `env.py` already wired [VERIFIED: alembic/versions] |
| playwright | 1.60.0 | Deterministic SauceDemo login + crawl (async API) | Locked tool; `async_playwright` runs in the BackgroundTask loop (D-06) [VERIFIED: uv pip list] |
| pytest-playwright | 0.8.0 | `page`/`context` fixtures the GENERATED spec consumes | Official plugin; generated spec is a pytest-playwright test [VERIFIED: uv pip list] |
| pytest | 9.0.* | Runner the executor subprocess invokes | Ecosystem standard; `asyncio_mode=auto` set [VERIFIED: pyproject.toml] |

### Supporting (NEW this phase — registry-verified, CLAUDE.md-sanctioned)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| neo4j | 6.2.0 | Official async Bolt driver (`AsyncGraphDatabase.driver`) | Lifespan-managed singleton; service-layer Cypher MERGE for Page/NavigatesTo [VERIFIED: PyPI 6.2.0; CITED: neo4j.com/docs/python-manual] |
| gherkin-official | 40.0.0 | Parse/validate LLM-generated Gherkin before writing it | Reject malformed `.feature` at generation time, not execution time (D-07) [VERIFIED: PyPI 40.0.0] |
| pytest-bdd | 8.1.0 | (Optional this phase) BDD step execution if the spec is BDD-shaped | CLAUDE.md slots it for generation; tracer may emit a plain pytest-playwright spec and defer BDD-step wiring — see Open Q1 [VERIFIED: PyPI 8.1.0] |
| Jinja2 | 3.1.6 | Skeleton template for the runnable spec (LLM fills narrow slots) | Deterministic syntactically-valid structure; LLM fills selectors/steps only [VERIFIED: PyPI 3.1.6 — likely already transitive via langchain] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Subprocess `uv run pytest <path>` | pytest in-process via `pytest.main()` | In-process pollutes the API process's import/asyncio state and the generated spec uses the SYNC Playwright API (cannot run in the API's running loop). Subprocess is isolation-correct and matches Phase-7's worker model. **Use subprocess.** |
| `neo4j` async driver + raw Cypher | neomodel OGM | CLAUDE.md: "Never for this project — async support immature, OGM fights the dynamic graph." **Use the driver.** |
| BackgroundTasks | Celery / aio-pika now | D-04/D-05 explicitly defer the broker to Phase 7; BackgroundTasks mirror the caller-gets-id-then-polls contract. **Use BackgroundTasks.** |
| Jinja2 skeleton + LLM slots | Raw LLM emits the whole `.py` | Raw emission risks syntactically-invalid files; skeleton guarantees structure, LLM fills semantic slots (CLAUDE.md generation pattern). **Use Jinja2.** |

**Installation:**
```bash
# from apps/api/ — add to [project.dependencies], then `uv sync`
uv add neo4j==6.2.* gherkin-official==40.* pytest-bdd==8.1.*
# Jinja2: confirm whether it is already resolved transitively before adding explicitly
uv pip list | grep -i jinja2 || uv add jinja2==3.1.*
```

**Version verification (run live 2026-06-13):**
- `neo4j` → PyPI **6.2.0** (matches CLAUDE.md 6.2.x; compatible with neo4j server 4.4 / 5.x / 2025.x — [CITED: neo4j.com/docs/python-manual/current/upgrade/])
- `gherkin-official` → PyPI **40.0.0** (matches CLAUDE.md 40.x)
- `pytest-bdd` → PyPI **8.1.0** (matches CLAUDE.md 8.1.x)
- `Jinja2` → PyPI **3.1.6** (matches CLAUDE.md 3.1.x)
- `playwright` 1.60.0, `pytest-playwright` 0.8.0 already installed [VERIFIED: uv pip list]

## Package Legitimacy Audit

> slopcheck could NOT be installed in this read-only research session (install was correctly denied as scope creep). Per the graceful-degradation protocol, every NEW package below is tagged `[ASSUMED]` and the planner MUST gate each install behind a `checkpoint:human-verify` task before `uv add`. All four are named explicitly in the authoritative `CLAUDE.md` stack tables (an additional legitimacy signal beyond bare registry existence) and exist on PyPI at the pinned versions.

| Package | Registry | Version | Source Repo | slopcheck | Disposition |
|---------|----------|---------|-------------|-----------|-------------|
| neo4j | PyPI | 6.2.0 | github.com/neo4j/neo4j-python-driver | not run | `[ASSUMED]` — planner checkpoint before install (official Neo4j driver; CLAUDE.md-locked) |
| gherkin-official | PyPI | 40.0.0 | github.com/cucumber/gherkin | not run | `[ASSUMED]` — planner checkpoint (Cucumber's official parser; CLAUDE.md-locked) |
| pytest-bdd | PyPI | 8.1.0 | github.com/pytest-dev/pytest-bdd | not run | `[ASSUMED]` — planner checkpoint (CLAUDE.md-locked; may be deferred — see Open Q1) |
| Jinja2 | PyPI | 3.1.6 | github.com/pallets/jinja | not run | `[ASSUMED]` — likely already transitive; confirm before adding explicitly |

**Packages removed due to slopcheck [SLOP] verdict:** none (slopcheck not run)
**Packages flagged as suspicious [SUS]:** none (slopcheck not run)

Python packages have no npm-style `postinstall` network-execution vector; the cross-ecosystem-confusion check is satisfied by verifying each on PyPI (the correct registry), done above.

## Architecture Patterns

### System Architecture Diagram

```
                          POST /explore (202 + run_id)            GET /executions, /executions/{id}
                                  │                                         ▲
                                  ▼                                         │ poll status
            ┌──────────────────────────────────────────┐                   │
            │  explore router  → create run(queued)     │───────────────────┘
            │  add BackgroundTask(run_id, target_id)    │
            └───────────────┬──────────────────────────┘
   (response already sent)  │  task runs AFTER response, SAME process, fresh session
                            ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ explore task:                                                          │
   │  open NEW SessionLocal()  →  run status=running                        │
   │  get_decrypted_credentials(db, target_id) → (user, pass)               │
   │  async_playwright(): login SauceDemo :8080 → landing page              │
   │     capture (url, title, page_key);  click 1 link → 2nd page           │
   │  neo4j driver session: MERGE (:Page{key})  + MERGE (a)-[:NavigatesTo]->(b)
   │  run status=passed (or failed + error on exception)                    │
   └──────────────────────────────────────────────────────────────────────┘
                            │  graph now has Page/NavigatesTo for run_id
                            ▼
   POST /generate-bdd (run_id) ──► read graph (Page/NavigatesTo for run_id)
        llm_gateway.complete(operation_type="generate-bdd", run_id=...) ──► provider
        gherkin-official validate ──► write workspaces/<run_id>/login.feature
                            │
                            ▼
   POST /generate-scripts (run_id) ──► Jinja2 skeleton + llm_gateway.complete(
        operation_type="generate-scripts", run_id=...) fills selectors/steps
        ──► write workspaces/<run_id>/test_login.py  (pytest-playwright, SYNC API)
                            │
                            ▼
   POST /execute (202 + run_id) ──► create execution(queued); BackgroundTask:
        subprocess: `uv run pytest workspaces/<run_id>/test_login.py`
        capture exit code + stdout/stderr ──► execution(passed|failed, output)
                            │
                            ▼
   GET /executions, GET /executions/{id} ──► rows from Postgres

   shared/events/ : ExploreJob, ExecuteJob, RunStatusEvent (Pydantic v2) — the
   shapes the in-process path produces now; Phase 7 publishes them to RabbitMQ.

   5 honest stubs (501 + OpenAPI contract): /heal, /create-defect,
   /flows, /coverage, /dashboard.
```

### Recommended Project Structure
```
apps/api/app/
├── routers/
│   ├── explore.py          # POST /explore (202 + run_id, BackgroundTask)
│   ├── generate.py         # POST /generate-bdd, /generate-scripts
│   ├── execute.py          # POST /execute (202 + run_id, BackgroundTask)
│   ├── executions.py       # GET /executions, GET /executions/{id}
│   └── stubs.py            # 501 contracts: /heal /create-defect /flows /coverage /dashboard
├── services/
│   ├── explorer.py         # deterministic Playwright crawl + Neo4j MERGE (tracer seam)
│   ├── generation.py       # gateway calls + gherkin validate + Jinja2 render + file write
│   ├── execution.py        # subprocess pytest runner + result capture
│   └── run_service.py      # run/execution status lifecycle CRUD
├── core/
│   └── neo4j_driver.py     # lifespan singleton (mirror redis_client.py)
├── models/
│   └── run.py              # Run + Execution SQLAlchemy models
├── schemas/
│   └── run.py              # RunResponse, ExecutionResponse, request bodies
└── alembic/versions/
    └── 0004_runs_executions.py   # down_revision='0003'

shared/events/__init__.py       # ExploreJob, ExecuteJob, RunStatusEvent (Pydantic v2)
infra/scripts/graph_mode.py     # stop web → neo4j up+healthy → run work → restore web
workspaces/<run_id>/            # login.feature + test_login.py (gitignored)
```

### Pattern 1: Lifespan-managed Neo4j async driver (mirror `redis_client.py`)
**What:** One long-lived `AsyncGraphDatabase.driver` opened at startup, closed at shutdown, reused across all requests/tasks. The driver is a connection pool — never open one per request.
**When to use:** Always for the API; the BackgroundTask reuses this same driver (the driver is thread/loop-safe for concurrent sessions; you open a fresh *session* per unit of work, not a fresh driver).
**Example:**
```python
# Source: neo4j.com/docs/python-manual/current/ (async section) — adapted to redis_client.py shape
# app/core/neo4j_driver.py
from neo4j import AsyncGraphDatabase, AsyncDriver
from app.core.config import settings

_driver: AsyncDriver | None = None

def init_neo4j() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,                       # "bolt://neo4j:7687" (compose) / "bolt://localhost:7687" (hybrid)
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver

async def close_neo4j() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None

def get_neo4j() -> AsyncDriver:
    return _driver or init_neo4j()
```
Wire into `app/main.py` lifespan exactly like `init_redis()`/`close_redis()`:
```python
init_redis(); init_neo4j()
...
await close_redis(); await close_neo4j(); await engine.dispose()
```

### Pattern 2: Minimal Cypher MERGE (tracer seam — NOT the Phase-5 single-writer)
**What:** Idempotent-ish writes for Page nodes + one NavigatesTo edge, keyed by a stable page identifier.
```python
# Source: neo4j.com/docs/python-manual/current/query-simple/ (async run pattern)
async def write_page_graph(driver, run_id: str, landing: dict, second: dict) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (a:Page {key: $a_key})
              ON CREATE SET a.url=$a_url, a.title=$a_title, a.run_id=$run_id
            MERGE (b:Page {key: $b_key})
              ON CREATE SET b.url=$b_url, b.title=$b_title, b.run_id=$run_id
            MERGE (a)-[:NavigatesTo]->(b)
            """,
            a_key=landing["key"], a_url=landing["url"], a_title=landing["title"],
            b_key=second["key"],  b_url=second["url"],  b_title=second["title"],
            run_id=run_id,
        )
```
Mark this clearly as a tracer seam (a comment) — Phase 5 replaces it with the single-writer service + fingerprint MERGE.

### Pattern 3: Async Playwright + Neo4j/DB writes INSIDE a BackgroundTask
**What:** The task opens its OWN resources. It runs after the response in the SAME process/loop. Critically: do NOT reuse the request's `get_db` session (it is closed when the response returns); open a fresh `SessionLocal()`. The lifespan Neo4j driver and Redis client ARE safe to reuse (they're pools).
```python
# Source: fastapi.tiangolo.com/tutorial/background-tasks + existing SessionLocal pattern
from playwright.async_api import async_playwright
from app.db.session import SessionLocal
from app.services import target_service, run_service
from app.core.neo4j_driver import get_neo4j

async def run_explore(run_id: str, target_id: int) -> None:
    async with SessionLocal() as db:                      # FRESH session — never the request's
        try:
            await run_service.set_status(db, run_id, "running")
            user, pw = await target_service.get_decrypted_credentials(db, target_id)
            async with async_playwright() as p:           # async API — runs in the task's loop
                browser = await p.chromium.launch()
                page = await browser.new_page()
                # ... login + capture landing + click one link + capture second ...
                await browser.close()
            await write_page_graph(get_neo4j(), run_id, landing, second)
            await run_service.set_status(db, run_id, "passed")
        except Exception as exc:                            # capture failure → status, never crash silently
            await run_service.set_status(db, run_id, "failed", error=str(exc))
```
Router side:
```python
@router.post("/api/explore", status_code=202)
async def explore(body: ExploreRequest, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    run = await run_service.create_run(db, kind="explore", target_id=body.target_id)  # status=queued
    bg.add_task(run_explore, run.run_id, body.target_id)
    return {"run_id": run.run_id, "status": "queued"}
```

### Pattern 4: Spec execution via subprocess (NOT in-process pytest)
**What:** `/execute` shells out so the generated SYNC-Playwright spec runs in its own process/loop, isolated from the API's running event loop.
```python
# Source: existing reset_target.py subprocess pattern (argv list, no shell=True)
import asyncio
async def run_execution(execution_id: str, spec_path: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        "uv", "run", "pytest", spec_path, "-q",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        cwd="apps/api",                          # so `uv run` resolves the project env
    )
    out, _ = await proc.communicate()
    status = "passed" if proc.returncode == 0 else "failed"
    async with SessionLocal() as db:
        await run_service.finish_execution(db, execution_id, status, output=out.decode()[-8000:])
```
`spec_path` is built from `run_id` (registry-derived path), never interpolated from user input — mirror `reset_target.py`'s T-01-26 argv-safety note.

### Pattern 5: gherkin-official validation gate before writing the .feature
```python
# Source: PyPI gherkin-official 40.x — Parser + TokenScanner
from gherkin.parser import Parser
from gherkin.token_scanner import TokenScanner

def validate_gherkin(text: str) -> None:
    Parser().parse(TokenScanner(text))   # raises CompositeParserException on malformed input
```
Reject (or one-shot re-ask the gateway) on parse failure — do not write an invalid `.feature`.

### Anti-Patterns to Avoid
- **Reusing the request's DB session in a BackgroundTask** — it's closed once the response is sent; you get `Event loop is closed` / detached-instance errors. Open a fresh `SessionLocal()`.
- **Opening a Neo4j driver per request** — the driver is a pool; open once in lifespan, open a *session* per unit of work.
- **Running the generated spec in-process** (`pytest.main()`) — the spec uses SYNC Playwright which cannot run inside the API's already-running asyncio loop. Subprocess only.
- **Letting the LLM emit the whole `.py` file** — non-deterministic, frequently unparseable. Jinja2 owns structure; the LLM fills narrow slots.
- **Faking results in the 5 stub endpoints** — return 501 with a documented OpenAPI contract; never a plausible-looking fake payload.
- **Starting neo4j while web is still up** — blows the 3 GB WSL cap. `graph_mode` stops web FIRST.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bolt protocol / connection pooling | A custom socket client | `neo4j.AsyncGraphDatabase` | Official driver handles pooling, retries, Bolt versions, 2025-server compat |
| Gherkin syntax validation | Regex/line parsing | `gherkin-official` Parser | The Cucumber-official parser catches every malformed-feature case |
| Spec-file structure | LLM-emitted whole file | Jinja2 skeleton + LLM slots | Guarantees a syntactically valid, importable pytest module |
| Metered LLM calls | Direct provider SDK call | `llm_gateway.complete()` | Budgets/kill-switch/caching/cost-ledger come for free (D-07; PLAT-05/06/07) |
| Credential decryption | Re-reading Fernet keys | `target_service.get_decrypted_credentials` | Single decrypt surface (T-01-21); never duplicate the decrypt path |
| Container health-wait in helper | `sleep`-and-hope | `docker compose ... --wait` / poll-until-healthy (reset_target pattern) | Deterministic readiness, exit-code contract |

**Key insight:** Phase 3 builds almost nothing from scratch — it wires verified components through a single `run_id`. The only bespoke logic is the deterministic crawl (a dozen Playwright calls) and the status lifecycle (a tiny state machine). Resist building abstractions (no queue layer — D-05; no single-writer service — Phase 5; no LangGraph — D-08).

## Runtime State Inventory

> Phase 3 is greenfield-additive (new tables, new nodes, new files), not a rename/refactor. This inventory covers the new runtime state it INTRODUCES, for operational awareness.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data (Postgres) | New `runs`/`executions` tables (Alembic 0004) | New migration chaining after 0003 |
| Stored data (Neo4j) | `Page` nodes + `NavigatesTo` edges, tagged `run_id` | Tracer-seam direct writes; Neo4j data volume NOT yet declared in compose — **add a named volume or accept ephemeral graph** (acceptable for a tracer; flag for Phase 5) |
| Live service config | neo4j service env (heap/pagecache/AUTH) lives in compose + repo `.env` (in git via `.env.example`) | Add `NEO4J_*` to compose + `.env.example` |
| OS-registered state | None — no Task Scheduler / pm2 / systemd registration | None |
| Secrets/env vars | New: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` (or `NEO4J_AUTH`) in `.env` + compose `environment:` block | Add to `.env.example` and the api service env (api enumerates env explicitly — see 02-01 deviation #2) |
| Build artifacts | `workspaces/<run_id>/` generated `.feature`+`.py` (gitignored) | None — gitignore already covers `workspaces/*` |

**Note:** The api container enumerates env vars explicitly in compose (it does NOT pass the whole `.env` — see `02-01-SUMMARY` deviation #2). The new `NEO4J_*` vars MUST be added to the api service `environment:` block or `Settings()` will fail to instantiate and the api becomes unhealthy.

## Common Pitfalls

### Pitfall 1: Neo4j Docker memory env-var underscore-doubling
**What goes wrong:** Setting `NEO4J_server_memory_heap_max_size` (single underscore on `max_size`) is silently ignored; Neo4j keeps its default heap and may exceed `mem_limit: 1g`, OOM-killing the container on a 3 GB host.
**Why it happens:** The Docker entrypoint conversion rule doubles literal underscores: `server.memory.heap.max_size` → `NEO4J_server_memory_heap_max__size` (note `max__size`). Periods become single underscores.
**How to avoid:** Use these EXACT names [CITED: neo4j.com/docs/operations-manual/current/docker/configuration/]:
```yaml
neo4j:
  image: neo4j:2025
  profiles: [graph]
  mem_limit: 1g
  environment:
    NEO4J_AUTH: ${NEO4J_AUTH:-neo4j/please-change}    # username/password
    NEO4J_server_memory_heap_initial__size: 512m       # heap.initial_size
    NEO4J_server_memory_heap_max__size: 512m           # heap.max_size  (DOUBLE underscore)
    NEO4J_server_memory_pagecache_size: 256m           # pagecache.size (NO doubling — no literal underscore)
  ports:
    - "7687:7687"   # Bolt
    - "7474:7474"   # HTTP browser (optional, handy for manual inspection)
  healthcheck:
    test: ["CMD-SHELL", "wget -q -O /dev/null http://localhost:7474 || exit 1"]
    interval: 10s
    timeout: 5s
    retries: 10
    start_period: 30s
```
**Warning signs:** `docker stats` shows neo4j RSS near/over 1 g; container restarts; `docker compose logs neo4j` shows heap-larger-than-mem_limit warnings.

### Pitfall 2: BackgroundTask reuses the request DB session
**What goes wrong:** `Cannot operate on a closed database` / detached-instance / `Event loop is closed` once the task runs after the response.
**Why it happens:** FastAPI runs the BackgroundTask AFTER the response is sent; the `Depends(get_db)` session was already closed in the request teardown.
**How to avoid:** The task opens its own `async with SessionLocal() as db:`. The lifespan Neo4j driver and Redis client are pools and ARE safe to reuse. (Pattern 3.)
**Warning signs:** Errors only on the polled status update, never on the 202 response.

### Pitfall 3: Generated spec uses sync Playwright but is run in-process
**What goes wrong:** `It looks like you are using Playwright Sync API inside the asyncio loop` — the spec can't run inside the API's loop.
**Why it happens:** pytest-playwright's `page` fixture is the SYNC API; the API process already runs an asyncio loop.
**How to avoid:** Always execute via subprocess (Pattern 4). The generated spec stays sync (standard pytest-playwright); the API never imports or runs it in-process.
**Warning signs:** `/execute` works from a standalone `pytest` shell but raises inside the API.

### Pitfall 4: graph_mode starts neo4j before stopping web → OOM
**What goes wrong:** web (1.5 g) + neo4j (1 g) + postgres + redis + api + saucedemo > 3 GB → WSL OOM, wedged stack.
**Why it happens:** Ordering. Memory math (D-03) only fits with web DOWN: 512m + 256m + 1g(api) + 1g(neo4j) + 128m ≈ 2.9 g.
**How to avoid:** `graph_mode.py` ordering is mandatory: (1) `docker compose stop web`, (2) `docker compose --profile graph up -d neo4j` + poll-until-healthy, (3) run the work, (4) `docker compose start web`. Mirror `reset_target.py` (stdlib-only, argv lists, no shell=True, health poll, exit codes).
**Warning signs:** Docker engine becomes unresponsive during explore tests; matches the STATE.md `.wslconfig` wedge symptom.

### Pitfall 5: LLM-generated selectors don't match SauceDemo → spec fails
**What goes wrong:** The generated spec is runnable Python but the test fails because the LLM invented selectors.
**Why it happens:** Free-hand LLM selectors (the exact failure GEN-05 forbids later).
**How to avoid (tracer-pragmatic):** Constrain the LLM's slots to selectors the deterministic crawl actually OBSERVED (SauceDemo's stable ids: `#user-name`, `#password`, `#login-button`, `.inventory_list`). Feed observed selectors into the prompt/Jinja context so the LLM fills from a known set, not from imagination. Success criterion 2 only needs ONE spec that passes.
**Warning signs:** Generated spec imports/parses fine but `/execute` returns `failed` with locator-timeout in the captured output.

### Pitfall 6: api container can't reach neo4j (URI host)
**What goes wrong:** Bolt connection refused from the api container.
**Why it happens:** Compose-internal hostname is `neo4j:7687`; hybrid host mode uses `localhost:7687`. Same split as `DATABASE_URL` (`postgres` vs `localhost`) and `REDIS_URL`.
**How to avoid:** `NEO4J_URI=bolt://neo4j:7687` in the compose api env; `.env` (hybrid) uses `bolt://localhost:7687`. Mirror the existing DATABASE_URL/REDIS_URL convention. Add `depends_on: neo4j: condition: service_healthy` ONLY if the api is in the `graph` profile too — otherwise the api must tolerate neo4j being absent on a plain `up` (it is: only /explore touches neo4j). **Recommendation:** do NOT hard-depend api on neo4j; the tracer's explore test activates the graph profile via `graph_mode`.

## Code Examples

### Run/Execution status lifecycle (the state machine)
```python
# queued ──(task starts)──► running ──(success)──► passed
#                                   └─(exception)─► failed
VALID = {"queued", "running", "passed", "failed"}
# run_service.create_run -> queued; set_status(running) at task start;
# set_status(passed|failed, error=...) at task end. GET reads the row.
```

### Run + Execution models (chain after 0003)
```python
# app/models/run.py — Source: existing llm_usage.py model shape
class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # threads the slice
    kind: Mapped[str] = mapped_column(String(16))            # "explore" | "execute"
    target_id: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    error: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Execution(Base):
    __tablename__ = "executions"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)   # same thread
    spec_path: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    exit_code: Mapped[int | None] = mapped_column(nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

### shared/events Pydantic message schemas (D-05 — schemas only, no broker)
```python
# shared/events/__init__.py — Pydantic v2; the shapes the in-process path produces
from pydantic import BaseModel, Field
import uuid

class ExploreJob(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    target_id: int

class ExecuteJob(BaseModel):
    run_id: str
    spec_path: str

class RunStatusEvent(BaseModel):
    run_id: str
    kind: str          # "explore" | "execute"
    status: str        # queued | running | passed | failed
    error: str | None = None
```

### Honest 501 stub with documented contract
```python
# app/routers/stubs.py — real OpenAPI contract, explicit not-implemented behavior
@router.post("/api/heal", status_code=501,
    summary="Self-heal a failed locator (Phase 8)",
    response_description="Not implemented in the tracer slice",
    responses={501: {"description": "Documented contract; behavior lands in Phase 8"}})
async def heal(body: HealRequest) -> None:
    raise HTTPException(status_code=501, detail="heal: not implemented (Phase 8)")
```
Define request/response Pydantic models for each stub so the OpenAPI schema is COMPLETE (the contract is real even though the behavior is 501).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `neo4j-driver` package name | `neo4j` package (driver 6.x) | 6.x line | CLAUDE.md notes `neo4j-driver` is dead; install `neo4j` |
| Sync-only Neo4j access | `AsyncGraphDatabase` native async | 5.x+, mature in 6.x | Driver runs natively in the FastAPI/Playwright async loop |
| Celery for background work | FastAPI BackgroundTasks (then RabbitMQ Phase 7) | — | D-04: in-process now, broker later, no API-contract change |
| `langgraph.create_react_agent` | `langchain.agents.create_agent` / raw StateGraph | LangGraph 1.x | Irrelevant this phase (D-08: no LangGraph) but noted for Phase 4 |

**Deprecated/outdated:**
- `neo4j-driver` PyPI package — superseded by `neo4j`.
- BackgroundTasks are NOT durable: they die with the process and do not survive an api restart. **Acceptable for the tracer** (document it; Phase 7's RabbitMQ workers add durability). A run left in `running` after an api crash is a known, accepted tracer limitation.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `neo4j`, `gherkin-official`, `pytest-bdd`, `Jinja2` are legitimate (slopcheck not run) | Package Legitimacy Audit | Low — all CLAUDE.md-named + PyPI-verified; planner checkpoint gates install |
| A2 | Jinja2 is already resolved transitively (via langchain) | Standard Stack | Low — `uv add jinja2` if not; pin 3.1.* |
| A3 | A plain pytest-playwright spec (not full pytest-bdd step wiring) satisfies success criterion 2 | Standard Stack / Open Q1 | Medium — if the criterion demands BDD-step execution, add pytest-bdd step defs (more LLM surface). See Open Q1 |
| A4 | SauceDemo login form is `#user-name`/`#password`/`#login-button` and inventory `.inventory_list` | Pitfall 5 | Low — standard Swag Labs markup; the deterministic crawl observes actual selectors anyway |
| A5 | neo4j data can be ephemeral this phase (no named volume declared) | Runtime State Inventory | Low — tracer graph is regenerated per explore; flag a volume for Phase 5 |
| A6 | api should NOT hard-depend on neo4j (graph profile only active during explore) | Pitfall 6 | Low — keeps plain `up` working; explore tests activate graph_mode |

## Open Questions

1. **Does success criterion 2 require a BDD-executed spec or a plain pytest-playwright spec?**
   - What we know: D-07 says "one Gherkin scenario AND one runnable Playwright spec." CLAUDE.md slots pytest-bdd for generation. The criterion is "produce one Gherkin scenario and one runnable Playwright spec … /execute runs that spec."
   - What's unclear: whether the runnable spec must be *driven by* the `.feature` via pytest-bdd step defs, or whether the `.feature` is generated as an artifact and a separate plain pytest-playwright `.py` is what `/execute` runs.
   - Recommendation: For a tracer, generate BOTH artifacts but have `/execute` run a **plain pytest-playwright spec** (smallest reliable path to a passing run). Keep the `.feature` as a generated, gherkin-validated artifact. If the planner wants true BDD execution, add pytest-bdd step defs (a second Jinja2 template + LLM slot set) — more LLM surface, more fragility. **Tracer favors the plain spec.**

2. **Neo4j data volume — declare now or defer to Phase 5?**
   - What we know: compose currently declares neo4j with no volume; `pgdata` is the only named volume.
   - Recommendation: Acceptable to run ephemeral this phase (the tracer regenerates the graph on each explore). Note it for Phase 5 sizing. If the planner wants persistence for inspection, add a `neo4jdata` named volume mounting `/data`.

3. **Where does `/execute` find the spec — DB-stored path or convention?**
   - Recommendation: Convention `workspaces/<run_id>/test_login.py`, recorded ALSO in the `executions.spec_path` column for traceability and to keep the subprocess argv registry-derived (not user-input-derived).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Compose | neo4j activation, graph_mode | ✓ | v2 | — |
| Playwright Chromium | deterministic crawl + spec execution | ✓ | installed Phase 1 | — |
| `uv` | subprocess `uv run pytest` | ✓ | Phase 1 | `python -m pytest` if uv unavailable in subprocess cwd |
| neo4j:2025 image | graph writes | ✓ (compose, profile `graph`) | 2025 | — |
| SauceDemo :8080 | explore target | ✓ (default profile) | SHA-pinned | — |
| Provider API key (Anthropic/OpenAI) | generate-bdd/scripts (real LLM) | ✗ (empty placeholder in `.env`) | — | Mark generation tests `live_llm`; gateway works without keys only for non-LLM paths |
| Host RAM headroom | neo4j(1g)+stack under 3 GB WSL cap | ✓ ONLY with web stopped (D-03) | 5.7 GB host / 3 GB WSL | graph_mode stops web first — mandatory, not optional |

**Missing dependencies with no fallback:** none that block the slice's structure.
**Missing dependencies with fallback:** real provider keys — generate-bdd/generate-scripts tests that hit a live provider must be marked `live_llm` (skipped on the default gate, run manually with keys). The `complete()` call path, gherkin validation, Jinja2 render, and file write can be unit-tested with a mocked gateway (the `fake_chat_model` fixture pattern from 02-01).

## Validation Architecture

> nyquist_validation is enabled (no `workflow.nyquist_validation: false` found). Section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.* + pytest-asyncio 1.4.* (`asyncio_mode=auto`) + pytest-playwright 0.8.0 |
| Config file | `apps/api/pyproject.toml` (`[tool.pytest.ini_options]`, markers: functional, e2e, live_llm) |
| Quick run command | `cd apps/api && uv run pytest -m "not live_llm and not e2e" -q` |
| Full suite command | `cd apps/api && uv run pytest -q` (functional sorted before e2e per conftest) |
| New marker needed | `graph` — functional tests that require the neo4j `graph` profile active (so the default gate can exclude/include them deliberately) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAT-02 SC1 | POST /explore → real Page/NavigatesTo in Neo4j | functional (graph) | `uv run pytest tests/functional/test_explore.py -q` | ❌ Wave 0 |
| PLAT-02 SC2 | generate-bdd → valid Gherkin; generate-scripts → runnable spec | functional (mocked gateway) + live_llm | `uv run pytest tests/functional/test_generation.py -q` | ❌ Wave 0 |
| PLAT-02 SC3 | /execute runs spec → result row → GET /executions | functional (graph) | `uv run pytest tests/functional/test_execute.py -q` | ❌ Wave 0 |
| PLAT-02 SC4 | all 10 endpoints exist; 5 return 501 w/ contract; schemas in shared/events | functional | `uv run pytest tests/functional/test_surface.py -q` | ❌ Wave 0 |
| PLAT-02 | run_id threads explore→generate→execute→result | functional (graph) | `uv run pytest tests/functional/test_run_thread.py -q` | ❌ Wave 0 |

### How to test the hard parts
- **BackgroundTasks deterministically:** POST returns 202+run_id; then **poll `GET /executions/{run_id}` until status is terminal** (`passed`/`failed`) with a bounded timeout (e.g. 60s, 1s interval — mirror `reset_target.py`'s health-poll shape). Never assert immediately after the 202.
- **Assert Neo4j nodes exist:** after explore reaches a terminal status, open a driver session in the test and run `MATCH (a:Page)-[:NavigatesTo]->(b:Page) WHERE a.run_id=$rid RETURN count(*)` — assert ≥ 1. (Test gets the driver via a host Bolt URI `bolt://localhost:7687`.)
- **graph profile in tests:** the functional `graph` tests assume neo4j is up (web stopped) — the test harness invokes `infra/scripts/graph_mode.py` (or the suite documents "run under graph_mode"). Mark these `@pytest.mark.graph` so the default `not live_llm` gate can opt in/out.
- **Real LLM:** generate-bdd/generate-scripts against a live provider → mark `live_llm` (skipped by default). The deterministic parts (gherkin validation, Jinja2 render, file write, status transitions) test with a mocked gateway (`fake_chat_model` pattern from 02-01) so the default gate stays zero-spend.
- **Spec execution:** assert the executions row has `status in {passed, failed}` and a non-empty `output`; for SC2's "passes" claim, assert `status == passed` in the live_llm/graph path.

### Sampling Rate
- **Per task commit:** `uv run pytest -m "not live_llm and not e2e and not graph" -q` (fast, zero-spend, no neo4j needed)
- **Per wave merge:** under graph_mode, `uv run pytest -m "not live_llm" -q` (includes graph functional tests)
- **Phase gate:** full suite green (functional + graph + one live_llm generation run with real keys) before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/functional/test_explore.py` — covers SC1 (poll-to-terminal + Neo4j assert)
- [ ] `tests/functional/test_generation.py` — covers SC2 (mocked-gateway determinism + live_llm runnable-spec)
- [ ] `tests/functional/test_execute.py` — covers SC3 (subprocess run → executions row)
- [ ] `tests/functional/test_surface.py` — covers SC4 (10 endpoints, 501 contracts, shared/events importable)
- [ ] `tests/functional/test_run_thread.py` — run_id traceability across the slice
- [ ] `tests/conftest.py` additions — a `neo4j_session` host-driver fixture; a poll-until-terminal helper; register the `graph` marker in pyproject
- [ ] Framework: no install needed (pytest stack present); add `neo4j`/`gherkin-official`/`pytest-bdd` to deps (gated)

## Security Domain

> `security_enforcement` not explicitly `false` → included.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Router-level `Depends(get_current_user)` on all new real endpoints — mirror `targets.py` (no new auth code) |
| V3 Session Management | no | No new session surface; existing JWT cookie unchanged |
| V4 Access Control | partial | RBAC is Phase 10; this phase only enforces authenticated access (the existing gate) |
| V5 Input Validation | yes | Pydantic v2 request models for every new endpoint (`ExploreRequest` with `target_id: int`, etc.) |
| V6 Cryptography | yes (reuse) | Credentials decrypted ONLY via `get_decrypted_credentials` (Fernet) — never re-implement |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cypher injection via page-derived strings | Tampering | Parameterized Cypher ONLY (`$key`, `$url`) — never f-string interpolate observed page text into queries (Pattern 2 uses parameters) |
| Subprocess command injection (spec path) | Elevation | argv list, no `shell=True`, `spec_path` registry/run_id-derived not user-input-derived (mirror reset_target.py T-01-26) |
| Credential leakage into graph/artifacts/logs | Info Disclosure | PLAT-07: never write decrypted creds into Neo4j nodes, generated specs, or logs; structlog redaction already covers password/secret/token keys |
| SSRF via explore target URL | Tampering | Explore only the registered target's `origin_allowlist`; the deterministic crawl visits SauceDemo only (full allowlist enforcement is Phase 4 EXPL-08) |
| LLM prompt injection from page content | Tampering | Tracer feeds only deterministic observed selectors to the LLM (not raw page DOM); full untrusted-input sanitization is Phase 4 EXPL-08 |
| Provider key exposure in generated code | Info Disclosure | Generation routes through the gateway; keys never enter prompts/artifacts (PLAT-07, existing control) |

## Sources

### Primary (HIGH confidence)
- `apps/api/` codebase (read directly): `app/main.py`, `services/llm_gateway.py`, `services/target_service.py`, `core/redis_client.py`, `core/security.py`, `routers/targets.py`, `models/{target,llm_usage}.py`, `alembic/versions/0003_llm_usage.py`, `tests/conftest.py`, `pyproject.toml`, `infra/docker-compose.yml`, `infra/scripts/reset_target.py`, `shared/events/README.md`, `workspaces/README.md` — VERIFIED current code
- `03-CONTEXT.md` (D-01..D-08), `REQUIREMENTS.md` (PLAT-02), `STATE.md` (environment facts), `CLAUDE.md` (locked stack) — binding inputs
- PyPI registry (queried live 2026-06-13): `neo4j` 6.2.0, `gherkin-official` 40.0.0, `pytest-bdd` 8.1.0, `Jinja2` 3.1.6 — VERIFIED versions
- `uv pip list`: playwright 1.60.0, pytest-playwright 0.8.0 already installed — VERIFIED
- [neo4j.com/docs/python-manual/current/upgrade/](https://neo4j.com/docs/python-manual/current/upgrade/) — driver 6.x compatible with server 4.4/5.x/2025.x — HIGH
- [neo4j.com/docs/operations-manual/current/docker/configuration/](https://neo4j.com/docs/operations-manual/current/docker/configuration/) — env-var underscore-doubling rule; exact `NEO4J_server_memory_heap_max__size` / `NEO4J_server_memory_pagecache_size` / `NEO4J_AUTH` forms; ports 7687/7474 — HIGH
- [fastapi.tiangolo.com/tutorial/background-tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) — BackgroundTasks run after response, same process — HIGH

### Secondary (MEDIUM confidence)
- WebSearch (verified against the official docs above): neo4j Docker healthcheck via cypher-shell / wget; BackgroundTasks same-process/event-loop limitations — MEDIUM

### Tertiary (LOW confidence)
- None relied upon — all load-bearing claims trace to codebase, PyPI, or official docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package is CLAUDE.md-locked and PyPI-version-verified; 2 already installed.
- Architecture: HIGH — patterns mirror existing, verified code (redis_client lifespan, reset_target subprocess, target_service decrypt, llm_gateway call path).
- Pitfalls: HIGH — Neo4j env-var rule and BackgroundTask session lifecycle confirmed against official docs; memory math from D-03.
- Validation: HIGH — maps directly to the 4 success criteria and existing functional-test philosophy.
- Open questions: 3, all low/medium risk, all with a recommended default.

**Research date:** 2026-06-13
**Valid until:** 2026-07-13 (stack is pinned; neo4j 6.x / FastAPI patterns are stable — 30 days)
