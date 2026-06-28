# Phase 10: Dashboards, RBAC & Coverage/Traceability - Research

**Researched:** 2026-06-28
**Domain:** RBAC enforcement (FastAPI DI), dashboard read-aggregation, graph-derived coverage, cross-store traceability join, Elasticsearch 9.4 search — all over existing Phase 4-9 data. No new domain capability.
**Confidence:** HIGH (everything maps to existing, in-repo patterns; the only external unknown — the elasticsearch 9.4 async client + ES-9 security posture — is resolved below)

## Summary

Phase 10 is a **visualize + gate + search** phase: zero new agents, zero new domain logic. Every data source already exists in Postgres (`scenarios`, `test_runs`, `test_results`, `test_artifacts`, `classifications`, `defects`) and Neo4j (the discovered Page/Element/flow structure read via `kg/reader.py`). The four locked decisions (D-01..D-04) all extend established in-repo seams rather than introducing new mechanisms:

- **RBAC (PLAT-04):** A `role` column on `User` + a `require_role(*roles)` dependency that composes exactly like the existing `Depends(get_current_user)` router-level gate (scenarios/defects/heals all use it). The role is read off the `User` object `get_current_user` already resolves (the JWT `sub` is the user id, not email — so role lives on the row, not baked into a stale token). A static role→permission map gates routers and the frontend nav.
- **Coverage (DASH-04):** A pure join: discovered flows (mined via `kg/flows.mine_flows_from_neo4j`) × Postgres `scenarios.status='approved'` × `test_results.verdict='passed'`, keyed by `flow_id`. Genuinely separate from `kg/coverage.py` (which is ground-truth page/flow matching vs a committed fixture).
- **Traceability (DASH-05):** A read-time cross-store join keyed by the shared `run_id` + `flow_id` that thread through *every* Postgres lifecycle table plus the Neo4j flow id. No new graph writes — the keys already exist (Phase 9 wired them for exactly this).
- **Search (DASH-06):** `elasticsearch==9.4.*` (the one expected new backend dep), `AsyncElasticsearch` lifespan-managed like the neo4j driver, on-write dual-index hooks + a backfill command, graceful-degrade to an honest "search unavailable" mirroring the neo4j→503 handler in `main.py`.

**Primary recommendation:** Build five thin read-services (`rbac` helper, `coverage_dash`, `traceability`, `dashboards`, `search`) that mirror `exec_history.py`'s SQLAlchemy-2.0 `select/scalars` style, plus the `role` column (migration 0010), `require_role` in `core/security.py`, the ES client module (mirror `core/neo4j_driver.py`), and an ES exception handler (mirror the neo4j one). All deterministic, keyless, fixture-testable — except the ES *functional* path which needs the `search` profile up (or a fake client for the index/search contract). The one genuine design decision the planner must settle: **flow_id stability** (see Open Questions Q1).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01 (RBAC):** `role` enum column on User (Admin / QA Lead / QA Engineer / Developer) via migration; ADMIN_EMAIL seed defaults to Admin; admin-only role-assignment API; JWT carries role; `/me` returns it; `require_role(*roles)` DI built on get_current_user → 403 on mismatch; frontend gates nav/views off role from `/me`; STATIC role→permission map (NOT a permissions table): Admin = all; QA Lead = manage suites/scenarios + all dashboards; QA Engineer = run executions + QA dashboard; Developer = read + Developer dashboard.
- **D-02 (Coverage):** flow COVERED iff ≥1 approved scenario AND ≥1 passing execution; coverage% = covered/total discovered; GRAPH-DERIVED (kg/reader flows JOIN Postgres approved scenarios + passing results); definition DISPLAYED; SEPARATE from Phase-5 ground-truth coverage.
- **D-03 (Traceability):** cross-store JOIN on READ keyed by ANY artifact id (flow/scenario/run/defect); joins Neo4j flows (kg/reader) + Postgres scenarios/scripts/executions/test_results/defects (FK-linked, Phase-9); NO new graph writes; keyless, deterministic, fixture-testable.
- **D-04 (Elasticsearch):** ON-WRITE dual-index + backfill reindexer; elasticsearch 9.4 client GATED dep (client major == ES server 9.x); thin non-blocking failure-tolerant es.index alongside Postgres writes; graceful-degrade when ES down (profiles:[search] off → honest "search unavailable", mirror neo4j-503); search API + UI; structlog→ES log path.

### Claude's Discretion
- Dashboard AGGREGATION queries (DASH-01/02/03) computed ON-READ unless materialization needed.
- require_role endpoint→role matrix across all routers; admin role-assignment API + minimal admin UI vs API-only.
- ES index mappings + on-write hook points + backfill command + search ranking/highlighting.
- Traceability response shape + viewer interaction.
- Migration 0010 for role column (chains after 0009).
- UI-SPEC (built in SEPARATE ui-phase AFTER this research).

### Deferred Ideas (OUT OF SCOPE)
- K8s/CI/CD/Prometheus/Grafana ops stack → Phase 11.
- Granular permissions table / custom roles → REJECTED v1.
- Graph-native traceability (writing lifecycle into Neo4j) → REJECTED v1.
- Bi-directional Jira sync → out of v1.
- Real-time dashboard push (SSE/websocket tiles) → not required (TanStack Query polling).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAT-04 | Admin can assign roles (Admin/QA Lead/QA Engineer/Developer) that gate API endpoints AND dashboard views | RBAC section: `role` column + migration 0010 + `require_role` DI + admin role-assignment endpoint + static role→permission map + endpoint→role matrix + frontend nav gating off `/me` |
| DASH-01 | Executive dashboard: coverage, pass rate, defect counts, trends | Dashboard Aggregation: reuse `exec_history.pass_rate_trend`; new coverage% (DASH-04); defect counts via `defects`/`classifications` group-by; recharts cards (Phase-7 precedent) |
| DASH-02 | QA dashboard: execution history, failed tests, screenshots, videos | Dashboard Aggregation: `exec_history.list_runs`/`get_run_status` + `test_artifacts` (kind=screenshot/video) served via the existing artifact route |
| DASH-03 | Developer dashboard: root-cause groupings, error trends, module failure breakdowns | Dashboard Aggregation: group `classifications` by classification+fingerprint (root-cause); error trends per-day; failures per `flow_id` (module breakdown) |
| DASH-04 | Coverage engine: % discovered flows covered by approved scenarios AND passing executions (graph-derived, honest definition) | Coverage section: pure join of mined flows × approved scenarios × passing results; honest definition string; SEPARATE from `kg/coverage.py` |
| DASH-05 | Traceability engine: flow↔scenario↔script↔execution↔defect chain for any artifact | Traceability section: cross-store join on `run_id`+`flow_id`; entry by flow/scenario/run/defect id; response shape; NO graph writes |
| DASH-06 | Search across executions, failures, logs backed by Elasticsearch | Elasticsearch section: `elasticsearch==9.4.*` AsyncElasticsearch; index mappings; on-write dual-index; backfill; search API w/ highlighting; graceful-degrade |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Role storage + assignment | API / Backend (Postgres `users.role`) | — | RBAC is backend-owned (CLAUDE.md: "RBAC lives in YOUR backend"); the JWT only carries `sub` (user id) — role is read off the row each request, never trusted from a stale token |
| Endpoint authorization (`require_role`) | API / Backend (FastAPI DI) | — | Enforcement MUST be server-side; frontend gating is UX-only, never a security boundary |
| Dashboard view gating (nav/route visibility) | Frontend Server (Next.js) | API (`/me` returns role) | UX convenience — hides nav the user can't use; the API still 403s if they hit a forbidden endpoint |
| Coverage computation | API / Backend (read-service) | Database (Neo4j flows + Postgres) | Pure aggregation over two stores; computed on-read |
| Traceability join | API / Backend (read-service) | Database (Neo4j + Postgres) | Cross-store join is application-tier work; neither store can join the other |
| Dashboard aggregation queries | API / Backend (read-services) | Database (Postgres) | Mirror `exec_history.py`; computed on-read, cached client-side by TanStack Query |
| Full-text search | API / Backend (search-service) | Search store (Elasticsearch) | ES owns the inverted index; the API owns the query shape + graceful-degrade |
| Search indexing (on-write) | API / Backend (thin hook in write paths) | Search store (Elasticsearch) | Non-blocking dual-write alongside the Postgres commit |
| Chart rendering | Browser / Client (recharts) | — | Pure presentation |

## Standard Stack

### Core (new this phase)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| elasticsearch | 9.4.* | `AsyncElasticsearch` client for index/bulk/search/highlight (DASH-06) | The official client; **client major MUST match ES server major (9.x)** — CLAUDE.md + Elastic docs. `9.4.1` confirmed on PyPI, exactly matches `elasticsearch:9.4.1` in compose. `index()`/`bulk()`/`search()` all have async variants; `elasticsearch.helpers.async_bulk` for backfill. [VERIFIED: PyPI `pip index versions elasticsearch` → 9.4.1] [CITED: elasticsearch-py.readthedocs.io 9.4.1] |

### Supporting (already installed — reuse, ZERO new)
| Library | Version | Purpose | Reuse point |
|---------|---------|---------|-------------|
| SQLAlchemy (asyncio) | 2.0.* | All dashboard/coverage/traceability read queries | Mirror `exec_history.py` `select/scalars`, `func.sum/avg/count`, `date_trunc` |
| PyJWT | 2.13.* | Existing JWT mint/decode | No change — role is NOT added to the token (read off the row) |
| structlog | 26.* | Already JSON-renders; the ES log path consumes these events | `core/logging.py` redaction processor stays as-is |
| httpx | 0.28.* | Already present; **NOT needed for ES** (the elasticsearch client brings its own transport) | — |
| alembic | 1.18.* | Migration 0010 (role column) | Mirror `0009_defects.py` template |
| neo4j | 6.2.* | `kg/reader.flows_source` + `kg/flows.mine_flows` for the coverage/traceability flow side | No change |

### Frontend (already installed — ZERO new preferred)
| Library | Version | Purpose | Reuse point |
|---------|---------|---------|-------------|
| recharts | 3.8.* | All three dashboards' charts | Already installed Phase 7 (commit `bc47b9b`); Phase-7 executions trend cards are the precedent |
| @tanstack/react-query | 5.* | Dashboard polling/caching; `/me` role fetch | `app-sidebar.tsx` already uses `useQuery` for `/me` |
| @tanstack/react-table | 8.21.* | Execution-history / failure tables | Per CLAUDE.md |
| zod | 4.* | API response validation in `lib/api/*.ts` clients | Mirror existing `lib/api/executions.ts` etc. |
| lucide-react | 1.* | Nav icons | `app-sidebar.tsx` precedent |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `require_role` static map | A permissions table | REJECTED in CONTEXT (D-01) — 4 fixed roles need no table; CLAUDE.md: "no extra library needed for 4 static roles" |
| ES on-write dual-index | A Postgres→ES CDC/queue pipeline | Overkill for v1; on-write hook + backfill is the decided (D-04) and simplest correct approach |
| `elasticsearch` client | raw httpx against ES REST | The client gives the version-matched API surface, async helpers, and bulk — not worth hand-rolling |
| Live ES for index/search tests | a fake/stub client implementing `index`/`search` | Both used: a fake client for the **contract** unit tests (keyless, fast), the `functional`-marked tests under the `search` profile for the live path (Open Q3 resolved) |

**Installation:**
```bash
# Backend (GATED — checkpoint:human-verify before adding, per D-04 + the aio-pika/recharts precedent)
cd apps/api && uv add "elasticsearch==9.4.*"
# Frontend: NONE — recharts/react-query/react-table/zod all already present
```

**Version verification:**
- `elasticsearch` 9.4.1 — [VERIFIED: PyPI, queried 2026-06-28]. Matches `elasticsearch:9.4.1` server image in `infra/docker-compose.yml`. The client major (9) MUST equal the server major (9) — strict, per Elastic docs and CLAUDE.md.

## Package Legitimacy Audit

> One new backend package. slopcheck was not available in this environment; the package is a long-established official Elastic library and is GATED behind `checkpoint:human-verify` per D-04 regardless.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| elasticsearch | PyPI | ~12 yrs (1.0 in 2013) | very high (official client) | github.com/elastic/elasticsearch-py | n/a (unavailable) | Approved — GATED behind checkpoint:human-verify (D-04) |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none
**Frontend new packages:** NONE (zero-new-frontend-dep preference satisfied — recharts/react-query/react-table/zod all installed).

*slopcheck could not be installed/run in this session; `elasticsearch` is nonetheless safe — it is the canonical official Elastic Python client (github.com/elastic/elasticsearch-py), already named in CLAUDE.md's locked stack, and is independently gated behind a human-verify checkpoint. Treat the single dep as `[VERIFIED: PyPI + CLAUDE.md locked stack]`.*

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────────────────────┐
  Browser (Next.js)      │  app-sidebar reads /me → role            │
  role-gated nav/views   │  TanStack Query polls dashboard APIs     │
                         └───────────────┬─────────────────────────┘
                                         │ httpOnly cookie (access_token)
                                         ▼
   ┌──────────────────────── FastAPI (apps/api) ───────────────────────────┐
   │  require_role(*roles)  ← built on get_current_user (reads users.role)  │
   │        │ 403 on mismatch                                               │
   │        ▼                                                               │
   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
   │  │ dashboards   │  │ coverage_dash│  │ traceability │  │  search   │  │
   │  │ read-service │  │ read-service │  │ read-service │  │  service  │  │
   │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘  │
   │         │ select/scalars  │ join            │ join            │        │
   └─────────┼─────────────────┼─────────────────┼─────────────────┼───────┘
             │                 │                 │                 │
       ┌─────▼─────┐     ┌─────▼──────┐    ┌─────▼──────┐    ┌─────▼──────┐
       │ Postgres  │     │  Neo4j     │    │ both       │    │Elasticsearch│
       │ test_runs │     │ (flows via │    │ stores     │    │ (profile    │
       │ test_results    │  kg/reader)│    │ joined on  │    │  search;    │
       │ scenarios │     │            │    │ run_id +   │    │  503 if down)│
       │ defects   │     └────────────┘    │ flow_id    │    └─────▲──────┘
       │ classifications                   └────────────┘          │
       └─────▲─────┘                                               │ on-write
             │ commit                                              │ es.index()
             └──────── write paths (worker job.py, defect pipeline)┘ (non-blocking)
                                                                   │
                                                          backfill reindex cmd
```

Data flow for the primary use case (Exec dashboard load): browser sends cookie → `require_role(...)` resolves the user + checks role → `dashboards`/`coverage_dash` services run `select`s over Postgres + a mined-flows read from Neo4j → JSON back → recharts renders. Search load: browser → `search` service → `AsyncElasticsearch.search(...)` → highlighted hits, OR a clean 503 "search unavailable" if the `search` profile is off.

### Recommended Project Structure (additions only)
```
apps/api/app/
├── core/
│   ├── security.py          # + require_role(*roles) factory (extends get_current_user)
│   └── es_client.py         # NEW: init_es/get_es/close_es (mirror neo4j_driver.py)
├── models/user.py           # + role column
├── schemas/
│   ├── auth.py              # MeResponse + role; RoleAssignRequest
│   ├── dashboards.py        # NEW: response models for the 3 dashboards
│   ├── coverage_dash.py     # NEW: coverage response (incl. honest-definition string)
│   ├── traceability.py      # NEW: chain response shape
│   └── search.py            # NEW: search request/response (hits + highlights)
├── services/
│   ├── rbac.py              # NEW: static ROLE_PERMISSIONS map + helpers
│   ├── coverage_dash.py     # NEW: pure join (mined flows × approved scenarios × passing results)
│   ├── traceability.py      # NEW: cross-store join keyed by any artifact id
│   ├── dashboards.py        # NEW: exec/qa/dev aggregation reads (reuse exec_history)
│   └── search/
│       ├── indexer.py       # NEW: on-write index hooks + index mappings + backfill
│       └── query.py         # NEW: search() with highlighting + graceful-degrade
├── routers/
│   ├── users.py             # NEW: POST /api/users/{id}/role (Admin-only), GET /api/users
│   ├── dashboards.py        # NEW: GET /api/dashboards/{exec|qa|dev}, role-gated
│   ├── coverage_dash.py     # NEW: GET /api/coverage/flows (drill-down), role-gated
│   ├── traceability.py      # NEW: GET /api/traceability?{flow_id|scenario_id|run_id|defect_id}
│   └── search.py            # NEW: GET /api/search?q=...&index=...
└── alembic/versions/0010_user_role.py   # NEW: role column (chains after 0009)

apps/web/                    # UI-SPEC built in the SEPARATE ui-phase — inputs noted below
```

### Pattern 1: `require_role` composes on `get_current_user` (read role off the row)
**What:** A dependency factory returning a dependency that resolves the user then checks `user.role`.
**When to use:** Router-level `dependencies=[...]` (gates every route) or per-route `Depends(...)`.
**Why read off the row, not the token:** `create_token` puts only `{sub, type, iat, exp, jti}` in the JWT — `sub` is the user id. `get_current_user` already fetches the `User` row. Reading `user.role` there means an admin role change takes effect on the next request (no token reissue, no stale-role window). The CONTEXT line "JWT carries the role" is satisfiable two ways; **recommend role-on-row** as strictly safer and simpler — flag for the planner as a deviation-with-rationale (see Assumptions A1).
```python
# Source: pattern derived from apps/api/app/core/security.py get_current_user
# + apps/api/app/routers/executions.py require_user_or_ci_token (router-gate precedent)
from fastapi import Depends, HTTPException
from app.core.security import get_current_user
from app.models.user import User

def require_role(*allowed: str):
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user
    return _dep

# usage (mirrors routers/scenarios.py router-level Depends(get_current_user)):
# router = APIRouter(prefix="/api/dashboards",
#     dependencies=[Depends(require_role("admin", "qa_lead", "developer"))])
```

### Pattern 2: read-service mirrors `exec_history.py`
**What:** Module-level `async def` functions taking `db: AsyncSession`, returning plain dicts/lists, using SQLAlchemy-2.0 `select` + `func.*`.
**When to use:** Every dashboard/coverage aggregation.
```python
# Source: apps/api/app/services/exec_history.py pass_rate_trend (verbatim style)
day = func.date_trunc("day", TestRun.created_at).label("day")
rows = (await db.execute(select(day, func.sum(TestRun.total)).group_by(day).order_by(day))).all()
```

### Pattern 3: ES client lifespan-managed like the neo4j driver (lazy, boots when down)
**What:** `init_es()` in lifespan (lazy — does NOT connect/fail at boot), `get_es()` singleton, `close_es()` on shutdown. An `@app.exception_handler` for ES connection errors → clean 503.
**When to use:** All ES access; mirrors `core/neo4j_driver.py` + the `ServiceUnavailable` handler in `main.py`.
```python
# Source: pattern mirrors apps/api/app/core/neo4j_driver.py + main.py _neo4j_unavailable_handler
from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ConnectionError as ESConnectionError  # transport-level

_es: AsyncElasticsearch | None = None
def init_es() -> None:
    global _es
    _es = AsyncElasticsearch(settings.elasticsearch_url)  # lazy; no connect at construct
def get_es() -> AsyncElasticsearch: ...
async def close_es() -> None: ...

# in main.py:
@app.exception_handler(ESConnectionError)
async def _es_unavailable(request, exc):
    return JSONResponse(status_code=503,
        content={"detail": "Search is unavailable — start the search profile to use it."})
```

### Pattern 4: on-write dual-index — non-blocking, failure-tolerant
**What:** After the Postgres commit in a write path (worker `job.py` result persist; defect pipeline), call `es.index(...)` wrapped so an ES failure NEVER breaks the primary write.
```python
# Source: pattern derived from kg/flows.py categorize_flow broad-except degrade discipline
try:
    await get_es().index(index="executions", id=f"{run_id}:{flow_id}", document={...})
except Exception as exc:  # noqa: BLE001 — search is best-effort; never break the Postgres write
    log.info("es_index_skipped", error=str(exc))
```

### Anti-Patterns to Avoid
- **Baking role into the JWT:** creates a stale-role window on role change; read off the row instead.
- **Frontend-only gating:** nav hiding is UX, not security — the API MUST `require_role`.
- **Writing lifecycle data into Neo4j for traceability:** violates the single-writer discipline (D-03); join on read instead. The grep gate for "single write path" must stay green.
- **Conflating DASH-04 with `kg/coverage.py`:** they are different metrics; keep separate services + separate displayed definitions.
- **Blocking the execution write on ES:** any ES exception in the dual-index path must be swallowed + logged.
- **Synchronous `Elasticsearch` client in the async app:** use `AsyncElasticsearch` only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Full-text search / ranking / highlighting | A Postgres ILIKE/tsvector search | `AsyncElasticsearch.search` with `highlight` | D-04 decided ES; relevance ranking + highlight fragments are non-trivial |
| Bulk backfill of existing rows into ES | A hand-rolled index loop | `elasticsearch.helpers.async_bulk` | Chunking, error aggregation, retries handled |
| Role enforcement | A custom permissions table/engine | static map + `require_role` DI | 4 fixed roles (D-01); CLAUDE.md says no extra lib |
| Per-day trend bucketing | Python-side grouping | SQL `func.date_trunc` (see `exec_history.pass_rate_trend`) | Already proven in-repo; pushes work to the DB |
| Cross-store join | Duplicating Postgres data into Neo4j | read-time join on `run_id`+`flow_id` | Keys already exist (Phase 9); keeps stores clean |
| Service-down handling | per-endpoint try/except | one `@app.exception_handler` (mirror neo4j) | Consistent honest 503; no leaked 500s |

**Key insight:** Phase 10 adds NO new mechanism — every piece is a thin reuse of an existing in-repo pattern (`exec_history` reads, `get_current_user` gate, `neo4j_driver` lifespan + 503 handler, `kg/flows.py` degrade discipline). The risk is not "how do I build X" but "did I wire the existing seams correctly and keep the two coverage metrics distinct."

## Runtime State Inventory

> This is a feature phase (additive), not a rename/refactor. One migration adds a column to existing rows — that IS a data concern, so the relevant categories:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `users` table: existing rows (at least the seeded admin) gain a `role` column. New column needs a server_default OR a data backfill so existing rows are valid. The seeded admin MUST become `Admin`. | Migration 0010: add `role` with `server_default='admin'` for the existing single admin row, OR add nullable + backfill + set default. Recommend `server_default` matching the admin seed intent + update `seed_admin` to set role on create. |
| Live service config | Elasticsearch indices do not exist yet — created on first index/backfill. The `search` compose profile is OFF by default. | Plan: an index-create/ensure-mappings step (idempotent, like `ensure_constraints` for neo4j) + the backfill command. Document the index names. |
| OS-registered state | None — verified: no Task Scheduler / pm2 / systemd state touched by this phase. | None |
| Secrets/env vars | `ELASTICSEARCH_URL` (new setting) needed in `core/config.py` Settings + compose env. ES security: compose ES block currently has NO `xpack.security.enabled=false` → ES 9.x defaults security ON (see Pitfall 1). | Add `elasticsearch_url` to Settings; add the xpack-disable env vars to the compose ES service. |
| Build artifacts | `uv.lock` / `pyproject.toml` change when `elasticsearch` is added (gated). Frontend: none (zero new deps). | `uv add elasticsearch==9.4.*` (behind checkpoint:human-verify); reinstall in api image. |

## Common Pitfalls

### Pitfall 1: ES 9.x defaults security ON — the compose block doesn't disable it
**What goes wrong:** `AsyncElasticsearch("http://elasticsearch:9200")` fails (TLS/auth required) because the compose ES service sets only `discovery.type=single-node` + `ES_JAVA_OPTS` — **not** `xpack.security.enabled=false`. ES 9.x defaults security (HTTPS + auth) ON.
**Why it happens:** The compose block (`infra/docker-compose.yml:378-385`) was scaffolded minimally for "Phase 9/10" and never configured for unsecured local HTTP.
**How to avoid:** Add to the ES service environment: `xpack.security.enabled=false`, `xpack.security.http.ssl.enabled=false`, `xpack.security.enrollment.enabled=false`. Then the client connects over plain HTTP with no auth — correct for the local-dev-only posture (3GB cap, single operator). [CITED: elastic.co security-settings docs; multiple ES-9 docker reports]
**Warning signs:** `AuthenticationException` / TLS handshake errors on the first `es.info()`.

### Pitfall 2: flow_id is enumeration-index-based, not stable
**What goes wrong:** `kg/flows.build_flows` assigns `id = f"flow-{i}"` by the order paths are mined. A scenario/test row stored with `flow_id="flow-3"` may not correspond to the same journey after the graph changes and re-mining renumbers. The coverage join and traceability "enter by flow_id" can silently mismatch.
**Why it happens:** Flows are MINED on read (not persisted as identified nodes); the index is positional.
**How to avoid (planner decision — Open Q1):** For DASH-04/05, recommend keying the coverage/traceability join on **what is actually stored**: the `flow_id` strings present in `scenarios`/`test_results`/`defects` ARE the denominator-and-numerator source of truth for "flows that have lifecycle data." For the "total discovered flows" denominator, mine the current graph and use its `flow-{i}` set — but document that coverage is computed against the *current* mining. Surface this honestly (it's consistent with D-02's "honest definition shown"). DO NOT assume `flow-3` is the same journey across re-explorations.
**Warning signs:** coverage% that jumps when nothing changed but a re-exploration happened; traceability lookups returning empty for a flow_id that exists in test_results.

### Pitfall 3: ES indexing must never block or break the Postgres write
**What goes wrong:** An ES outage (profile off) makes the worker's result-persist throw, failing executions.
**How to avoid:** Wrap every on-write `es.index` in a broad try/except that logs and continues (Pattern 4). The Postgres commit is the source of truth; ES is a derived, rebuildable index (backfill restores it).
**Warning signs:** execution failures correlated with the `search` profile being down.

### Pitfall 4: client/server major mismatch
**What goes wrong:** an 8.x client against the 9.x server (or vice versa) fails handshake/compat checks.
**How to avoid:** pin `elasticsearch==9.4.*` to match `elasticsearch:9.4.1`. [CITED: CLAUDE.md "What NOT to Use" — ES client 8.x with 9.x server fails]

### Pitfall 5: the two coverage metrics get conflated in the UI
**What goes wrong:** DASH-04 (lifecycle coverage) and `kg/coverage.py` (ground-truth exploration completeness) shown as one number → misleading.
**How to avoid:** separate services, separate response fields, and the displayed honest-definition string per D-02. The Exec dashboard may show both, each labeled with its definition.

### Pitfall 6: migration 0010 must set the admin's role + be reversible
**What goes wrong:** adding a NOT NULL `role` with no default breaks existing rows; a non-reversible migration fails the phase gate (the `0009` precedent runs alembic up/down/up).
**How to avoid:** `server_default` on the column; `downgrade()` drops it. Update `seed_admin` so newly seeded admins get `role='admin'`.

## Code Examples

### Coverage join (DASH-04) — pure, fixture-testable
```python
# Source: composition of kg/flows.mine_flows_from_neo4j + exec_history select style
async def coverage(db: AsyncSession, *, driver=None) -> dict:
    mined = await mine_flows_from_neo4j(driver=driver)             # {"flows":[...], ...}
    discovered_ids = {f"flow-{i}" for i in range(len(mined["flows"]))}
    approved = set((await db.scalars(
        select(Scenario.flow_id).where(Scenario.status == "approved").distinct())).all())
    passing = set((await db.scalars(
        select(TestResult.flow_id).where(TestResult.verdict == "passed").distinct())).all())
    covered = discovered_ids & approved & passing
    total = len(discovered_ids)
    return {
        "definition": "A discovered flow is COVERED iff it has >=1 approved scenario AND "
                      ">=1 passing execution.",
        "total_discovered": total,
        "covered": len(covered),
        "coverage_percent": round(100.0 * len(covered) / total, 1) if total else 0.0,
        "covered_flow_ids": sorted(covered),     # per-flow drill-down
    }
```

### Traceability join (DASH-05) — entry by any artifact id
```python
# Source: shared run_id+flow_id keys across models (execution_history/scenario/defects)
async def chain(db: AsyncSession, *, flow_id=None, run_id=None, scenario_id=None, defect_id=None):
    # 1. resolve run_id/flow_id from whatever entry id was given (one small select each)
    # 2. flow side: mined flow record from kg/reader (name/steps) for flow_id
    # 3. scenarios: select * where flow_id (and run_id if known) -> incl. generated script path
    # 4. executions: TestRun + TestResult(run_id, flow_id); artifacts: TestArtifact(run_id, flow_id)
    # 5. defects: Classification + Defect(run_id, flow_id) incl. jira_key
    # returns {"flow": {...}, "scenarios": [...], "scripts": [...], "executions": [...],
    #          "artifacts": [...], "defects": [...]}  -- the viewer renders the chain
    ...
```

### Search with highlighting (DASH-06)
```python
# Source: elasticsearch-py 9.4 async docs (search() is the async-awaited REST mapping)
resp = await get_es().search(
    index="executions,failures,logs",
    query={"multi_match": {"query": q, "fields": ["error_text", "message", "feature_name"]}},
    highlight={"fields": {"error_text": {}, "message": {}}},
    size=50,
)
hits = [{"index": h["_index"], "id": h["_id"], "source": h["_source"],
         "highlight": h.get("highlight", {})} for h in resp["hits"]["hits"]]
```

### Backfill reindex command
```python
# Source: elasticsearch.helpers.async_bulk (official async helper)
from elasticsearch.helpers import async_bulk
async def backfill(db, es):
    async def actions():
        for r in (await db.scalars(select(TestResult))).all():
            yield {"_index": "executions", "_id": f"{r.run_id}:{r.flow_id}",
                   "_source": {"run_id": r.run_id, "flow_id": r.flow_id,
                               "verdict": r.verdict, "error_text": r.error_text}}
    ok, errors = await async_bulk(es, actions())
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ES type mapping types, `doc_type` | typeless indices; mappings only | ES 7+ | mappings have no `_doc` type nesting |
| `Elasticsearch` sync client in async apps | `AsyncElasticsearch` + `async_*` helpers | ES-py 7.8+ | use the async client + `elasticsearch.helpers.async_bulk` |
| ES security optional/off by default | security ON by default | ES 8+/9 | MUST explicitly disable for local HTTP (Pitfall 1) |
| NextAuth for frontend auth | backend JWT + httpOnly cookie + role on row | this project's locked stack | frontend gating is UX-only |

**Deprecated/outdated:**
- `elasticsearch` client 8.x against a 9.x server — fails (CLAUDE.md).
- Putting binary artifacts (screenshots/videos) in Postgres/ES — they live in MinIO/workspaces; ES indexes only searchable text. The QA dashboard links to artifacts via the existing `GET /api/executions/{run_id}/artifacts/...` route.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | "JWT carries the role" (D-01) is best satisfied by reading `user.role` off the row in `require_role` rather than baking it into the token. | RBAC / Pattern 1 | If the planner/user insist the role literally be a JWT claim, `create_token` + `get_current_user` must change to add/verify a `role` claim AND a reissue-on-role-change path — more code + a stale-role window. Low risk: row-read is strictly safer; flag for confirmation. |
| A2 | The role string vocabulary is `admin` / `qa_lead` / `qa_engineer` / `developer` (String(16), mirroring the project's String(16) status/class-vocab convention). | RBAC | Cosmetic; align exact strings with the frontend gating + the static map. |
| A3 | "total discovered flows" denominator = the count of flows mined from the CURRENT graph (`flow-{i}`), accepting that re-mining can renumber. | Coverage / Pitfall 2 | If a stable flow identity is required, a flow-id persistence scheme is needed (bigger change, arguably out of this phase's "visualize-only" scope). Surface to the user. |
| A4 | The "generated script path" for traceability is recoverable from the scenario/codegen output (Phase 6) by convention (flow_id/run_id-derived path), not a stored column. | Traceability | If no path is persisted, the chain shows scenario→execution directly and notes the script is derived; verify against the Phase-6 codegen output layout. |
| A5 | ES index set = `executions`, `failures`, `logs` (matching DASH-06's "executions, failures, and logs"). `failures` ⊇ classifications/defects text; `logs` ⊇ structlog JSON events. | Elasticsearch | Index naming is discretionary (D-04); confirm at plan time. |
| A6 | structlog→ES is a SEPARATE optional path (a log shipper or a structlog processor that indexes), lower priority than the on-write execution/failure indexing. | Elasticsearch | If logs-in-ES is required for DASH-06 search to be "complete," the log path must be built, not deferred. Confirm scope. |

**If this table is empty:** it is not — six assumptions need confirmation at discuss/plan time, A1 and A3 being the load-bearing ones.

## Open Questions

1. **flow_id stability (load-bearing).**
   - What we know: `flow_id` is `flow-{i}` assigned by mining order; it is what `scenarios`/`test_results`/`defects` store.
   - What's unclear: whether re-exploration renumbering breaks coverage/traceability joins.
   - Recommendation: compute coverage against the current mining and surface the honest definition; do NOT promise cross-run flow identity. Confirm acceptable with the user (A3). If unacceptable, a flow-id persistence task is needed — likely its own scope.

2. **Does "JWT carries the role" mean literally-in-the-token, or just "the authenticated identity determines role"?**
   - Recommendation: read role off the row (A1). Confirm at plan/discuss.

3. **ES search testing contract — RESOLVED.**
   - The index/search/highlight **contract** is unit-testable with a fake/stub `AsyncElasticsearch` (an object exposing async `index`/`search`/`bulk` returning canned dicts) — keyless, fast, no profile. The **live** path (real mappings, real relevance) is a `functional`-marked test that runs under the `search` compose profile. Both belong in the plan; the contract test is the default gate, the functional test is profile-gated (mirrors the existing `graph`-marked neo4j tests). No new marker needed beyond reusing `functional` (or adding a `search` marker analogous to `graph` — minor, planner's call).

4. **Generated-script path provenance (A4).**
   - Confirm whether Phase-6 codegen persists a script path or it's derived by convention; affects the traceability "script" link.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | all dashboard/coverage/traceability reads, role column | ✓ (default profile, Phase 1) | 16/17 | — (blocking; always up) |
| Neo4j | coverage + traceability flow side (kg/reader) | ✓ but profile-gated `[graph]` | server 9.x via neo4j 6.2 driver | graceful-degrade 503 already exists; coverage shows "graph unavailable" |
| Elasticsearch 9.4.1 | DASH-06 search + on-write index | ✗ by default (profile `[search]`, OFF) | server 9.4.1 / client 9.4.* | graceful-degrade: honest "search unavailable" 503; on-write index swallowed |
| `elasticsearch` py client | ES access | ✗ not in pyproject | add 9.4.* (gated) | none — required for DASH-06 |
| Redis | (unchanged; SSE/cache) | ✓ default | 8.x | — |

**Missing dependencies with no fallback:** `elasticsearch` py package — must be added (gated, checkpoint:human-verify) for DASH-06.
**Missing dependencies with fallback:** Elasticsearch *server* and Neo4j are profile-gated and BOTH have graceful-degrade paths — the dashboards/coverage/traceability/search all render honest "unavailable" states rather than crashing when their profile is off. This is intentional under the 3GB cap.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.* + pytest-asyncio 1.4.* (`asyncio_mode="auto"`) |
| Config file | `apps/api/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd apps/api && uv run python -m pytest tests/unit -x` |
| Full suite command | `cd apps/api && uv run python -m pytest` |
| Markers | `functional` (live HTTP), `integration` (real Postgres), `graph` (neo4j profile), `e2e` (Playwright). Reuse `functional`/add a `search` marker for the live-ES path. |

> Tests run via `uv run python -m pytest` (Windows AppControl — STATE.md). The `app` package resolves via `pythonpath=[".", "../.."]`.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAT-04 | `require_role` 403s wrong role, passes allowed role | unit | `uv run python -m pytest tests/unit/test_require_role.py -x` | ❌ Wave 0 |
| PLAT-04 | admin role-assignment endpoint sets role; non-admin gets 403 | integration | `uv run python -m pytest tests/integration/test_role_assign.py -x` | ❌ Wave 0 |
| PLAT-04 | migration 0010 up/down/up reversible; admin row gets role | integration | `uv run python -m pytest tests/integration/test_migration_0010.py -x` | ❌ Wave 0 |
| DASH-04 | coverage join returns correct % on a seeded flows/scenarios/results fixture | unit | `uv run python -m pytest tests/unit/test_coverage_dash.py -x` | ❌ Wave 0 |
| DASH-04 | DASH-04 metric distinct from kg/coverage.py (no shared code path) | unit | (same file — assert separate module/result shape) | ❌ Wave 0 |
| DASH-05 | traceability chain assembles flow↔scenario↔exec↔defect from each entry id | integration | `uv run python -m pytest tests/integration/test_traceability.py -x` | ❌ Wave 0 |
| DASH-01/02/03 | each dashboard endpoint returns the expected aggregate shape on seeded data; role-gated | integration | `uv run python -m pytest tests/integration/test_dashboards.py -x` | ❌ Wave 0 |
| DASH-06 | search index/search/highlight CONTRACT against a fake ES client | unit | `uv run python -m pytest tests/unit/test_search_contract.py -x` | ❌ Wave 0 |
| DASH-06 | on-write index swallows ES failure (write still succeeds when ES down) | unit | (in test_search_contract.py — inject a raising fake) | ❌ Wave 0 |
| DASH-06 | search-unavailable → clean 503 when ES connection errors | unit/integration | `uv run python -m pytest tests/integration/test_search_degrade.py -x` | ❌ Wave 0 |
| DASH-06 | live ES index→search round-trip | functional (search profile) | `uv run python -m pytest -m functional tests/functional/test_search_live.py` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd apps/api && uv run python -m pytest tests/unit -x`
- **Per wave merge:** `cd apps/api && uv run python -m pytest tests/unit tests/integration`
- **Phase gate:** full suite green; the `search`-profile functional test run once under the profile (sequenced — see Memory below); `/gsd:verify-work` after.

### Wave 0 Gaps
- [ ] `tests/unit/test_require_role.py` — PLAT-04 (role gate)
- [ ] `tests/integration/test_role_assign.py` — PLAT-04 (admin assignment)
- [ ] `tests/integration/test_migration_0010.py` — PLAT-04 (reversible migration)
- [ ] `tests/unit/test_coverage_dash.py` — DASH-04 (seeded fixture → known %)
- [ ] `tests/integration/test_traceability.py` — DASH-05 (chain from each entry id)
- [ ] `tests/integration/test_dashboards.py` — DASH-01/02/03
- [ ] `tests/unit/test_search_contract.py` — DASH-06 (fake-ES contract + swallow-on-fail)
- [ ] `tests/integration/test_search_degrade.py` — DASH-06 (503 when ES down)
- [ ] `tests/functional/test_search_live.py` — DASH-06 (live, search profile)
- [ ] Fake ES client helper (in `tests/fixtures/` or conftest) — async `index`/`search`/`bulk` stub
- [ ] Seed fixtures: flows (mined-shape) + scenarios(approved) + test_results(passed/failed) + defects

### Deterministic vs Manual-Only split
- **Fully deterministic + keyless:** RBAC, coverage, traceability, dashboard aggregation — all driven by seed/fixture data, no LLM, no provider keys.
- **Keyless but profile-gated:** ES search functional test (needs the `search` profile up; contract test uses a fake client and needs nothing).
- **Manual-Only (the ONLY slice):** live-data realism — a real end-to-end where actual explore→generate→execute→classify runs populate the dashboards/coverage/search with non-fixture data, eyeballed for plausibility. This is NOT automatable cheaply and is the sole Manual-Only item.

## Security Domain

> `security_enforcement` not disabled in config → included.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | reused | existing PyJWT + argon2 + httpOnly cookie (Phase 1) — unchanged |
| V3 Session Management | reused | existing access/refresh cookies; role read per-request (no stale-role window) |
| V4 Access Control | **YES (core of PLAT-04)** | `require_role(*roles)` DI server-side; admin-only role-assignment endpoint; deny-by-default (403 on mismatch); frontend gating is UX-only NOT a boundary |
| V5 Input Validation | yes | Pydantic request models for role-assign + search query; the search `q` is passed as an ES query param (parameterized, not string-built Cypher/SQL) |
| V6 Cryptography | reused | no new crypto; ES local HTTP is acceptable ONLY for the local-dev single-operator posture |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Privilege escalation via self-role-change | Elevation of Privilege | role-assignment endpoint gated `require_role("admin")`; a user cannot set their own role |
| Authorization bypass by hitting API directly (skipping the hidden nav) | Elevation of Privilege | server-side `require_role` on every gated router — nav hiding is never the control |
| Forged role in token | Spoofing/Tampering | role NOT in the token (read off the row) → nothing to forge; even if added, HS256 signature protects it |
| Search query injection | Tampering | pass user `q` as a structured ES query value (`multi_match.query`), never string-concatenate into a query DSL or Cypher |
| Path traversal on artifact links from QA dashboard | Tampering | reuse the existing hardened `execution_artifact` route (realpath containment, already in place) |
| Sensitive data leaking into ES/logs | Information Disclosure | structlog redaction processor already masks password/secret/token/credential keys before render; ensure the ES log path runs AFTER redaction |

## Sources

### Primary (HIGH confidence)
- In-repo code (authoritative for all reuse patterns): `apps/api/app/core/security.py`, `models/user.py`, `routers/auth.py`, `services/kg/reader.py`, `services/kg/coverage.py`, `services/kg/flows.py`, `models/execution_history.py`, `models/scenario.py`, `models/defects.py`, `routers/executions.py`, `services/exec_history.py`, `main.py`, `core/logging.py`, `alembic/versions/0009_defects.py`, `apps/web/components/app-sidebar.tsx`, `tests/conftest.py`, `infra/docker-compose.yml`, `apps/api/pyproject.toml`.
- PyPI: `elasticsearch` 9.4.1 confirmed current, matches the 9.4.1 server image [queried 2026-06-28].
- CLAUDE.md locked stack: elasticsearch 9.4.x (client major == server 9.x), recharts/react-query/react-table, PyJWT + Depends(require_role), structlog→ES, no permissions table for 4 roles.

### Secondary (MEDIUM confidence)
- elasticsearch-py 9.4.1 docs (async client: `index`/`bulk`/`search` are async; `elasticsearch.helpers.async_bulk` for backfill) — https://elasticsearch-py.readthedocs.io/
- Elastic connecting/async guide — https://www.elastic.co/docs/reference/elasticsearch/clients/python/async
- ES 9 security-disable for local dev (`xpack.security.enabled=false` + ssl/enrollment off) — https://www.elastic.co/docs/reference/elasticsearch/configuration-reference/security-settings ; corroborated by multiple ES-9 docker reports.

### Tertiary (LOW confidence)
- None load-bearing; all critical claims cross-checked against in-repo code or PyPI/official docs.

## Metadata

**Confidence breakdown:**
- RBAC: HIGH — every piece extends an in-repo seam (`get_current_user`, router-level `Depends`, the 0009 migration template); the only nuance (role-on-row vs in-token) is flagged A1.
- Coverage/Traceability/Dashboards: HIGH — all reuse `exec_history.py` query style + existing shared `run_id`/`flow_id` keys; the one risk (flow_id stability) is flagged (Pitfall 2 / A3 / Open Q1).
- Elasticsearch: MEDIUM-HIGH — client version + API surface verified; the compose-security gap (Pitfall 1) and the test contract (Open Q3) are resolved concretely; the structlog→ES path scope (A6) needs confirmation.
- Security: HIGH — V4 access control is the core deliverable and maps to a server-side DI gate.

**Research date:** 2026-06-28
**Valid until:** 2026-07-28 (stack is pinned/stable; re-verify only if the ES server image bumps major).
