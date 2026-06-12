# Stack Research

**Domain:** AI-driven autonomous web-application testing platform (agentic explorer, knowledge graph, BDD + Playwright generation, self-healing, defect intelligence, Jira integration, dashboards)
**Researched:** 2026-06-12
**Confidence:** HIGH (all versions verified live against PyPI/npm registries on research date; patterns verified against official docs/release notes)

All user-constrained technologies (Next.js, FastAPI, LangGraph, Playwright, PostgreSQL, Neo4j, Elasticsearch, RabbitMQ, Redis, Docker/K8s, GitHub Actions, Grafana+Prometheus, Jira Cloud) are treated as decided. This document pins versions, picks specific libraries within those constraints, and resolves the open questions (LLM abstraction, Jira client, queue client, dashboard libs, exporters).

## Recommended Stack

### Runtime Baselines

| Runtime | Version | Why |
|---------|---------|-----|
| Python | 3.13.x | Fully supported by every pinned package (neo4j 6.x dropped 3.9; greenlet/asyncpg/playwright all ship 3.13 wheels). Avoid 3.14 for now — some C-extension wheels in this stack still lag. |
| Node.js | 22 LTS | Next.js 16 requires Node ≥ 20.9; 22 is the active LTS through 2026. |

### Core Backend (Python)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| FastAPI | 0.136.x | REST API (`/explore`, `/execute`, `/heal`, ...) | The decided framework; 0.13x line has stable Pydantic v2 integration and lifespan-based startup needed for driver/pool management |
| Pydantic | 2.13.x | Schemas, validation, LLM structured output | v2 is the only line FastAPI 0.13x and LangChain 1.x target; `model_json_schema()` drives LLM tool/output schemas |
| pydantic-settings | 2.14.x | 12-factor config (env vars per service) | Standard companion; one `Settings` class per service keeps Compose/K8s config identical |
| Uvicorn | 0.49.x | ASGI server | Standard FastAPI production server; run with `--workers` in containers |
| SQLAlchemy | 2.0.x (≥2.0.50) | Async ORM for PostgreSQL (executions, results, RBAC, traceability) | 2.0-style `async_sessionmaker` + `AsyncSession` is the standard async pattern; mature, well-documented |
| asyncpg | 0.31.x | PostgreSQL async driver | Fastest asyncio Postgres driver; the canonical pairing with async SQLAlchemy (`postgresql+asyncpg://`) |
| Alembic | 1.18.x | Schema migrations | The only serious option with SQLAlchemy; supports async engines via `run_sync` in `env.py` |
| greenlet | 3.5.x | SQLAlchemy async bridge | Required transitive dep for SQLAlchemy asyncio; pin explicitly to avoid wheel surprises on Windows |
| neo4j | 6.2.x | Knowledge graph driver (official Bolt driver) | 6.x is current major: native `AsyncGraphDatabase` driver, Bolt 6 with vector types (useful for embedding-based locator similarity). Compatible with Neo4j server 4.4, 5.x, and 2025.x |
| elasticsearch | 9.4.x | Search client (logs, failure search, test artifact search) | Official client with `AsyncElasticsearch`; client major version MUST match ES server major (run ES server 9.x) |
| redis | 8.0.x | Cache + distributed locks + rate limiting | Official client; `redis.asyncio` is built in (aioredis was merged and is dead). Works against Redis server 7.x/8.x |
| aio-pika | 9.6.x | RabbitMQ client (work queues: explore jobs, execution jobs, healing jobs) | The standard asyncio AMQP client (built on aiormq); robust connection recovery (`connect_robust`), publisher confirms, QoS prefetch — exactly what long-running test-execution consumers need |
| httpx | 0.28.x | Async HTTP client (Jira REST v3, webhooks, target-app probing) | The standard async client; connection pooling, timeouts, HTTP/2 |

### Agent / LLM Layer

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| langgraph | 1.2.x | Agent orchestration (Explorer, Healing, Defect, Jira agents as graphs) | v1.0 GA'd Oct 2025 with zero breaking changes from 0.x; StateGraph + nodes/edges + checkpointing is unchanged and stable. Durable execution, streaming, and human-in-the-loop are first-class |
| langchain-core / langchain | 1.4.x / 1.x | `init_chat_model`, messages, tools, structured output | **This is the provider-agnostic LLM layer.** `init_chat_model("anthropic:claude-...")` vs `init_chat_model("openai:gpt-...")` swaps providers with a config string — no adapter code. Satisfies the "Anthropic or OpenAI without code changes outside the adapter" constraint out of the box |
| langchain-anthropic | 1.4.x | Anthropic provider package | Official provider integration consumed by `init_chat_model` |
| langchain-openai | 1.3.x | OpenAI provider package | Official provider integration consumed by `init_chat_model` |
| langgraph-checkpoint-postgres | 3.1.x | Durable agent state in PostgreSQL | You already run Postgres; checkpointing there gives resumable exploration runs and crash recovery for free — no extra infra |
| langsmith | 0.8.x | Agent tracing/observability (optional but cheap) | One env var enables full trace capture of agent runs; invaluable when debugging why the Explorer misclassified a workflow |
| tenacity | 9.1.x | Retry policies around LLM and external calls | Standard retry library; exponential backoff for 429/529 provider errors |

**LLM abstraction decision — `init_chat_model`, not LiteLLM, not a custom adapter (HIGH confidence):**
- Since LangGraph is decided, agents already speak LangChain's `BaseChatModel` interface. `init_chat_model` makes the provider a configuration value. Adding LiteLLM would insert a second abstraction layer that duplicates what LangChain already does and degrades provider-specific features (Anthropic prompt caching, extended thinking params) to a lowest common denominator.
- A custom adapter is justified only if you later need providers LangChain doesn't cover or token-level cost routing. Don't build it speculatively.
- Note: LangGraph 1.x deprecated the `create_react_agent` prebuilt in favor of `langchain.agents.create_agent` (middleware-based). Use `create_agent` for simple tool-loop agents; use raw `StateGraph` for the Explorer/Healing engines where you need explicit control of the loop.

### Browser Automation & BDD

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| playwright (Python) | 1.60.x | Exploration browser + generated test execution | The decided tool; async API for the Explorer agent (`async_playwright`), sync API inside generated pytest specs. Trace viewer, video, and screenshot capture feed the Jira agent's evidence attachments |
| pytest | 9.0.x | Test runner for generated suites | The ecosystem standard; generated Playwright specs target pytest |
| pytest-playwright | 0.8.x | Playwright fixtures for pytest (`page`, `context`, browser/channel CLI flags) | Official plugin; gives generated specs parallel-ready browser fixtures without boilerplate |
| pytest-bdd | 8.1.x | Executes generated Gherkin `.feature` files against generated step defs | Runs inside pytest (unlike behave), so you get one runner, one reporting pipeline, pytest-xdist parallelism, and pytest-playwright fixtures in BDD steps |
| pytest-xdist | latest | Flow-level parallelism (`-n auto`) | Standard pytest parallelization; combine with Playwright's per-worker browser contexts |
| gherkin-official | 40.x | Parse/validate LLM-generated Gherkin before writing to repo | Cucumber's official parser; reject malformed generated features at generation time, not execution time |
| Jinja2 | 3.1.x | Code-generation templates (page objects, specs, fixtures, conftest) | Deterministic skeleton generation beats raw-LLM file emission: LLM fills semantic slots, Jinja guarantees syntactically valid structure |

### Jira Integration

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| atlassian-python-api | 4.0.x | Jira Cloud REST v3 client (issue create, transitions, attachments, JQL) | Actively tracking Jira Cloud changes: supports `enhanced_jql` (the new `nextPageToken` pagination Atlassian forced in 2025) and v3/ADF endpoints. The older `jira` (pycontribs) package broke during the v2→v3 search migration |
| httpx (direct) | 0.28.x | Fallback for v3-only endpoints + async paths | atlassian-python-api is sync (requests-based). Call it via `anyio.to_thread.run_sync` from FastAPI, or hit `/rest/api/3/...` directly with httpx for hot paths. Auth is just basic auth with email + API token |

ADF note: Jira Cloud v3 requires Atlassian Document Format for description/comment bodies. Generate ADF JSON directly (it's a documented JSON schema — have the defect agent emit it, or build a small `text→ADF` helper). No mature Python ADF builder library exists; don't go looking for one (LOW availability, verified).

### Auth & RBAC

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| PyJWT | 2.13.x | Backend-issued JWT access/refresh tokens | RBAC (Admin/QA Lead/QA Engineer/Developer) lives in YOUR backend, so the backend must own auth. PyJWT is the maintained standard (python-jose is stagnant) |
| argon2-cffi | 25.1.x | Password hashing | Current OWASP-recommended algorithm; use directly — passlib is unmaintained and broke with newer bcrypt |
| fastapi (deps) | — | Role enforcement via dependency injection | `Depends(require_role("qa_lead"))` per route; no extra library needed for 4 static roles |

Frontend consumes the backend's JWT. Do NOT add NextAuth for this (see What NOT to Use).

### Observability & Ops

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| prometheus-client | 0.25.x | Custom domain metrics (healing success rate, classification confidence, coverage %) | Official client; your spec's success metrics (>90% healing, >85% classification) should be Prometheus gauges from day one |
| prometheus-fastapi-instrumentator | 8.0.x | HTTP metrics (`/metrics` endpoint, latency/status histograms) | The standard FastAPI instrumentation; one line in lifespan |
| structlog | 26.x | Structured JSON logging | JSON logs → Elasticsearch ingestion → developer dashboard root-cause search; structlog is the Python standard for this |
| sse-starlette | 3.4.x | Server-Sent Events for live execution/exploration progress | Simpler than WebSockets for one-way dashboard streaming; works through proxies; FastAPI-native |
| MinIO (server) + minio | 7.2.x | S3-compatible artifact store (screenshots, videos, traces) | Don't put binary artifacts in Postgres/ES. MinIO runs in Compose/K8s on Windows Docker Desktop and is the standard self-hosted S3 |

**Prometheus exporters (run as containers, version-pin the images):**

| Component | Exporter | Notes |
|-----------|----------|-------|
| FastAPI services | built-in via instrumentator | `/metrics` on each service |
| PostgreSQL | `prometheuscommunity/postgres-exporter` | Standard |
| Redis | `oliver006/redis_exporter` | Standard |
| RabbitMQ | built-in `rabbitmq_prometheus` plugin | No external exporter needed; enabled in the `rabbitmq:4-management` image, scrape port 15692 |
| Elasticsearch | `prometheuscommunity/elasticsearch-exporter` | Standard |
| Neo4j | **CAUTION** | Native Prometheus endpoint (`server.metrics.prometheus.enabled=true`, port 2004) is **Enterprise-only**. Options: (a) run `neo4j:enterprise` under the free Neo4j dev license for local dev, or (b) skip DB-level Neo4j metrics and emit app-level graph metrics (node/edge counts, query latency) from your own services via prometheus-client. Recommend (b) for simplicity unless you adopt Enterprise anyway |

**Infra service versions (Docker images):** PostgreSQL 17 (18 is fine too), Neo4j 2025.x (calendar versioning replaced 5.x), Elasticsearch 9.x (must match client major), RabbitMQ 4.1+, Redis 8.x, Prometheus 3.x, Grafana 12.x. (MEDIUM confidence on minor tags — pin exact digests when writing Compose files.)

### Core Frontend (Next.js)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| next | 16.2.x | App framework (App Router) | Current major (GA Oct 2025); ships stable React 19 support incl. React Compiler; 16.2 handles TypeScript 6 deprecations |
| react / react-dom | 19.2.x | UI runtime | Required by Next 16 |
| typescript | 5.9.x | Type system | Pin 5.9: Next 16 requires TS 5+; TS 6.0 works on Next 16.2+ but the plugin/ecosystem (ESLint, editor tooling) is still settling — upgrade deliberately later |
| tailwindcss | 4.3.x | Styling | v4 (CSS-first config) is current; the shadcn/ui ecosystem targets it |
| shadcn/ui | latest CLI | Component system (tables, cards, dialogs, role-gated nav) | Copy-in components (no runtime dep lock-in); the de facto standard for internal dashboards on Next + Tailwind |
| recharts | 3.8.x | Dashboard charts (coverage trends, pass rates, defect trends) | shadcn/ui's chart primitives are built on Recharts; v3 is current and composable. One chart lib for all three dashboards |
| @tanstack/react-query | 5.x (≥5.101) | Server state: polling executions, caching dashboard data | The standard data-fetching layer; built-in `refetchInterval` covers live execution views; pairs with SSE for push updates |
| @tanstack/react-table | 8.21.x | Execution-history / failure tables (sort, filter, paginate) | Headless standard; renders with shadcn/ui table components |
| zustand | 5.0.x | Light client state (filters, selected run, UI prefs) | Minimal; avoid Redux ceremony for a dashboard app |
| zod | 4.x | API response validation + form schemas | Runtime validation at the API boundary; mirror FastAPI's Pydantic schemas (consider openapi-typescript to generate types from FastAPI's OpenAPI spec instead of hand-syncing) |
| lucide-react | 1.x | Icons | shadcn/ui default |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Python package/env management | Rust-speed installs; first-class on Windows; replaces pip+venv+pip-tools. Use `uv sync` in CI and Docker builds |
| ruff | Python lint + format | Replaces black+isort+flake8 in one tool |
| mypy (or pyright) | Python type checking | Async-heavy codebase benefits; pyright if you want the same engine as VS Code |
| pytest-asyncio 1.4.x | Async unit tests for services/agents | `asyncio_mode = "auto"` in config; 1.x line works with pytest 9 |
| ESLint 9 + eslint-config-next | Frontend lint | Flat config; comes with `create-next-app` |
| openapi-typescript | Generate TS types from FastAPI OpenAPI | Keeps frontend/backend contracts in sync without manual duplication |
| Docker Compose v2 | Local orchestration of 8+ services | Use profiles (`infra`, `app`, `monitoring`) so you can boot subsets on Windows; healthchecks + `depends_on: condition: service_healthy` are mandatory with this many services |

## Installation

```bash
# ---- Backend (uv project) ----
uv add fastapi==0.136.* "uvicorn[standard]==0.49.*" pydantic==2.13.* pydantic-settings==2.14.* \
  "sqlalchemy[asyncio]==2.0.*" asyncpg==0.31.* alembic==1.18.* greenlet==3.5.* \
  langgraph==1.2.* langchain==1.* langchain-anthropic==1.4.* langchain-openai==1.3.* \
  langgraph-checkpoint-postgres==3.1.* langsmith==0.8.* tenacity==9.1.* \
  neo4j==6.2.* elasticsearch==9.4.* redis==8.0.* aio-pika==9.6.* httpx==0.28.* \
  playwright==1.60.* atlassian-python-api==4.0.* \
  pyjwt==2.13.* argon2-cffi==25.1.* \
  prometheus-client==0.25.* prometheus-fastapi-instrumentator==8.0.* structlog==26.* \
  sse-starlette==3.4.* minio==7.2.* jinja2==3.1.* gherkin-official==40.*

uv add --dev pytest==9.0.* pytest-asyncio==1.4.* pytest-playwright==0.8.* pytest-bdd==8.1.* \
  pytest-xdist ruff mypy

# Install browser binaries (also needed in the executor Docker image)
uv run playwright install chromium

# ---- Frontend ----
npx create-next-app@16 frontend --typescript --tailwind --eslint --app
cd frontend
npm install @tanstack/react-query@5 @tanstack/react-table@8 recharts@3 zustand@5 zod@4 lucide-react
npx shadcn@latest init
npm install -D openapi-typescript
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `init_chat_model` (LangChain) | LiteLLM | If you later need 20+ providers, a billing proxy, or non-LangChain consumers of the LLM layer. As a *proxy server* LiteLLM can sit in front without code changes — defer until needed |
| `init_chat_model` | Custom adapter over `anthropic` + `openai` SDKs | Only if you abandon LangGraph; otherwise you'd reimplement message formats, tool-calling, and streaming LangChain already normalizes |
| aio-pika (direct) | FastStream 0.7 | Nice decorator-based broker framework over aio-pika; adopt if consumer boilerplate grows painful. Direct aio-pika gives you explicit ack/nack and prefetch control, which matters for hour-long execution jobs |
| pytest-bdd | behave 1.3 | If you want a standalone BDD runner decoupled from pytest. You'd lose pytest-playwright fixtures and xdist parallelism — not worth it here |
| atlassian-python-api | raw httpx against REST v3 | If you only ever need create-issue + attach + transition, ~200 lines of httpx is arguably cleaner and natively async. Reasonable choice; the library wins once JQL search, links, and components enter scope |
| Recharts | Tremor / ECharts | Tremor if you want pre-styled KPI blocks fast; ECharts for very large series (10k+ points). Recharts + shadcn charts covers spec dashboards |
| SSE (sse-starlette) | FastAPI WebSockets | WebSockets if dashboards become bidirectional (e.g., interactive exploration steering). One-way progress streams don't justify them |
| neo4j driver + Cypher | neomodel OGM | Never for this project — async support is immature and an OGM fights the dynamic, LLM-driven schema of a discovered app graph |
| MinIO | Local volume mounts for artifacts | Acceptable for week 1; you'll want S3 semantics (presigned URLs in dashboards, Jira attachment streaming) quickly |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `jira` (pycontribs) package | Broke during Atlassian's 2025 v2→v3 search/pagination migration; community reports ongoing Cloud friction; v2-era design | atlassian-python-api 4.x (or raw httpx on REST v3) |
| `langgraph.prebuilt.create_react_agent` | Deprecated in LangGraph 1.x | `langchain.agents.create_agent` or raw `StateGraph` |
| LiteLLM as an in-process layer *under* LangChain | Double abstraction; loses Anthropic-specific features (prompt caching, thinking budgets); two places for provider bugs | `init_chat_model` with provider packages |
| NextAuth v4 / Auth.js v5 | v5 has been beta for 2+ years (currently 5.0.0-beta.31); v4 is legacy. Your RBAC lives in FastAPI anyway — frontend auth libs add a second source of truth | Backend-issued JWT (PyJWT) + httpOnly cookie; Next.js middleware checks the cookie |
| Celery | Sync-first worker model fights an asyncio codebase (Playwright async, async drivers); you already have RabbitMQ + aio-pika for queueing | aio-pika consumers in dedicated worker containers |
| psycopg2 / `databases` / aioredis / python-jose / passlib | All superseded or unmaintained: psycopg2→asyncpg (or psycopg3), `databases`→async SQLAlchemy 2.0, aioredis→`redis.asyncio`, python-jose→PyJWT, passlib→argon2-cffi directly | As listed |
| Selenium (even "just for one thing") | Playwright covers everything Selenium does with auto-waiting, trace viewer, and a far better async API | Playwright 1.60 |
| Elasticsearch client 8.x | Client major must match server major; mixing 8.x client with 9.x server fails | elasticsearch 9.4.x with ES server 9.x |
| TypeScript 6.0 (today) | Works on Next 16.2 but tooling ecosystem (lint plugins, codegen) is still catching up to 6.0's deprecations | TypeScript 5.9.x; revisit in a later milestone |
| Storing screenshots/videos in PostgreSQL or ES | Bloats backups/indexes; ES is for searchable text/logs | MinIO (S3 API) + URL references in Postgres/Neo4j |

## Stack Patterns by Variant

**Explorer/Healing agents (long-running, stateful):**
- Raw `StateGraph` with `langgraph-checkpoint-postgres` and explicit nodes (navigate → extract → classify → persist-to-Neo4j → decide-next).
- Because exploration must be resumable, budget-capped (max pages/LLM calls), and inspectable mid-run — prebuilt agent loops hide that control.

**Defect-classification / Jira agents (short, tool-driven):**
- `create_agent` with tools (`fetch_logs`, `compare_runs`, `create_jira_issue`) and structured output (Pydantic schema for classification + 0-100 confidence).
- Because these are bounded tool-loops where the prebuilt + middleware model fits.

**Test execution jobs:**
- API enqueues to RabbitMQ via aio-pika → executor containers (Playwright + browsers baked into image) consume with `prefetch_count` = parallel browser capacity → results to Postgres, artifacts to MinIO, progress events to Redis pub/sub → SSE to dashboards.
- Because executions are long, must survive API restarts, and need horizontal scaling in K8s.

**Generated test repository layout:**
- pytest project: `features/*.feature` (Gherkin) + `steps/` (pytest-bdd) + `pages/` (page objects with healing-priority locator metadata: data-testid → aria-label → role → text → xpath) + `conftest.py` (pytest-playwright fixtures).
- Because one pytest invocation then covers BDD execution, parallelism, and artifact capture.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| langgraph 1.2.x | langchain-core 1.4.x, langchain-anthropic 1.4.x, langchain-openai 1.3.x | All on the 1.x line released together; do not mix with 0.x langchain-core |
| langgraph-checkpoint-postgres 3.1.x | langgraph 1.x, psycopg 3 (its own dep) | It uses psycopg3 internally — fine alongside asyncpg used by SQLAlchemy |
| neo4j driver 6.2.x | Neo4j server 4.4, 5.x, 2025.x | Requires Python ≥3.10 (3.9 dropped); `neo4j-driver` package name is dead — install `neo4j` |
| elasticsearch 9.4.x | Elasticsearch server 9.x ONLY | Strict major-version match |
| SQLAlchemy 2.0.x asyncio | asyncpg 0.31.x + greenlet 3.5.x | greenlet must have a wheel for your Python — 3.5.x covers 3.13 |
| redis 8.0.x | Redis server 7.x / 8.x | `redis.asyncio` built in |
| pytest 9.0.x | pytest-asyncio 1.4.x, pytest-bdd 8.1.x, pytest-playwright 0.8.x | All current lines support pytest 9 |
| next 16.2.x | react 19.2.x, Node ≥20.9, TS ≥5.1 (6.0 tolerated on 16.2+) | React Compiler stable in Next 16 |
| tailwindcss 4.3.x | Next 16 via `@tailwindcss/postcss` | v4 config is CSS-first (`@theme`), not tailwind.config.js |
| playwright 1.60.x | Python 3.10–3.13; executor image needs `playwright install --with-deps chromium` | Match Playwright version in dev and executor images exactly — browser binaries are version-locked |

## Sources

- PyPI JSON API (all Python versions queried live 2026-06-12: langgraph 1.2.4, langchain-core 1.4.6, langchain-anthropic 1.4.5, langchain-openai 1.3.0, litellm 1.88.1, playwright 1.60.0, neo4j 6.2.0, fastapi 0.136.3, sqlalchemy 2.0.50, alembic 1.18.4, asyncpg 0.31.0, aio-pika 9.6.2, elasticsearch 9.4.1, redis 8.0.0, atlassian-python-api 4.0.7, pytest 9.0.3, pytest-bdd 8.1.0, etc.) — HIGH
- npm registry (queried live 2026-06-12: next 16.2.9, react 19.2.7, typescript 6.0.3, tailwindcss 4.3.0, @tanstack/react-query 5.101.0, recharts 3.8.1, zustand 5.0.14, zod 4.4.3, next-auth dist-tags showing v5 still beta.31) — HIGH
- [LangGraph v1 release notes](https://docs.langchain.com/oss/python/releases/langgraph-v1) + [LangGraph 1.0 GA announcement](https://changelog.langchain.com/announcements/langgraph-1-0-is-now-generally-available) — v1 stability, create_react_agent deprecation, init_chat_model provider-agnostic pattern — HIGH
- [Neo4j Python Driver 6.x breaking changes](https://neo4j.com/docs/api/python-driver/current/breaking_changes.html) + [upgrade guide](https://neo4j.com/docs/python-manual/current/upgrade/) — 6.x server compatibility (4.4/5.x/2025.x), Python 3.9 drop, Bolt 6 vectors — HIGH
- [Next.js 16 release](https://nextjs.org/blog/next-16) + [v16 upgrade guide](https://nextjs.org/docs/app/guides/upgrading/version-16) — React 19.2 stable support, Node/TS requirements, TS6 handling in 16.2 — HIGH
- [Jira Cloud REST API v3 docs](https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/) + [atlassian-python-api repo](https://github.com/atlassian-api/atlassian-python-api) + Atlassian community reports of `jira` package v3-migration breakage — MEDIUM-HIGH
- [Neo4j Prometheus metrics docs](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/expose/) + [Neo4j KB](https://neo4j.com/developer/kb/how-to-monitor-neo4j-with-prometheus/) — Prometheus endpoint is Enterprise-only — HIGH

---
*Stack research for: AI-driven autonomous web-app testing platform*
*Researched: 2026-06-12*
