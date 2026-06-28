# Phase 10: Dashboards, RBAC & Coverage/Traceability - Pattern Map

**Mapped:** 2026-06-28
**Files analyzed:** 30 new/modified (15 backend, 1 migration, 1 compose, ~13 frontend)
**Analogs found:** 26 / 30 (4 are NET-NEW assemblies with a strong shape-analog but no exact copy-from)

> **Headline (from 10-RESEARCH):** Phase 10 adds NO new mechanism. Every piece is a thin reuse of an in-repo seam. The risk is "did I wire the existing seams correctly," not "how do I build X." This map is concrete about which seam each new file copies.

---

## File Classification

### Backend (apps/api)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality | NET-NEW? |
|-------------------|------|-----------|----------------|---------------|----------|
| `app/models/user.py` (MOD: +`role` col) | model | — | `models/scenario.py` `status` String(16) col | exact | DIRECT-REUSE |
| `alembic/versions/0010_user_role.py` | migration | — | `alembic/versions/0009_defects.py` | exact | DIRECT-REUSE |
| `app/core/security.py` (MOD: +`require_role`) | middleware (DI) | request-response | `core/security.py` `get_current_user` + `routers/scenarios.py` router-gate | exact | NET-NEW fn (on direct-reuse seam) |
| `app/services/rbac.py` | service (static map) | — | (no analog — pure constant map) | none | NET-NEW |
| `app/schemas/auth.py` (MOD: +role / RoleAssign) | schema | — | `schemas/auth.py` `MeResponse` | exact | DIRECT-REUSE |
| `app/routers/users.py` | router | CRUD (role assign) | `routers/scenarios.py` router-gate + `routers/auth.py` `/me` | role-match | NET-NEW (thin) |
| `app/services/coverage_dash.py` | service | transform (cross-store join) | `services/exec_history.py` select-style + `kg/flows.mine_flows_from_neo4j` | role-match | NET-NEW (DASH-04 metric) |
| `app/schemas/coverage_dash.py` | schema | — | `schemas/auth.py` BaseModel style | role-match | NET-NEW |
| `app/routers/coverage_dash.py` | router | request-response | `routers/scenarios.py` router-gate | role-match | NET-NEW (thin) |
| `app/services/traceability.py` | service | transform (cross-store join) | `services/exec_history.py` + the FK-linked models | partial (shape only) | NET-NEW (pure join) |
| `app/schemas/traceability.py` | schema | — | `schemas/auth.py` BaseModel style | role-match | NET-NEW |
| `app/routers/traceability.py` | router | request-response | `routers/scenarios.py` router-gate | role-match | NET-NEW (thin) |
| `app/services/dashboards.py` | service | CRUD/transform (aggregation) | `services/exec_history.py` (verbatim style) | exact | DIRECT-REUSE style |
| `app/schemas/dashboards.py` | schema | — | `schemas/auth.py` BaseModel style | role-match | NET-NEW |
| `app/routers/dashboards.py` | router | request-response | `routers/executions.py` history routes + `routers/scenarios.py` gate | exact | DIRECT-REUSE style |
| `app/core/es_client.py` | config (lifespan) | — | `core/neo4j_driver.py` (lazy singleton) | exact (mirror) | NET-NEW (mirror) |
| `app/services/search/indexer.py` | service | file-I/O (on-write index + backfill) | `kg/flows.py` `categorize_flow` broad-except degrade | partial (degrade discipline) | NET-NEW |
| `app/services/search/query.py` | service | request-response (ES search) | `kg/reader.py` read style + 10-RESEARCH ES examples | partial | NET-NEW |
| `app/schemas/search.py` | schema | — | `schemas/auth.py` BaseModel style | role-match | NET-NEW |
| `app/routers/search.py` | router | request-response | `routers/scenarios.py` router-gate | role-match | NET-NEW (thin) |
| `app/main.py` (MOD: ES lifespan + 503 handler + include routers) | config | — | `main.py` neo4j lifespan + `_neo4j_unavailable_handler` | exact | DIRECT-REUSE |
| `app/core/config.py` (MOD: +`elasticsearch_url`) | config | — | `config.py` `neo4j_uri` Setting | exact | DIRECT-REUSE |
| `infra/docker-compose.yml` (MOD: ES xpack env) | config | — | `docker-compose.yml` elasticsearch block | exact | DIRECT-REUSE (gap fix) |

### Frontend (apps/web)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality | NET-NEW? |
|-------------------|------|-----------|----------------|---------------|----------|
| `components/app-sidebar.tsx` (MOD: role-gated NAV) | component | — | `components/app-sidebar.tsx` NAV_ITEMS + `/me` query | exact | DIRECT-REUSE |
| `lib/api/{dashboards,coverage,traceability,search,users}.ts` | utility (zod client) | request-response | `lib/api/executions.ts` (zod + `api.get`) | exact | DIRECT-REUSE style |
| `app/(dashboard)/dashboards/{executive,qa,developer}/page.tsx` | component | request-response | `app/(dashboard)/executions/page.tsx` (useQuery + states) | exact | DIRECT-REUSE style |
| `components/dashboards/*-chart.tsx` (recharts) | component | — | `components/executions/trend-charts.tsx` | exact | DIRECT-REUSE |
| `app/(dashboard)/{coverage,traceability,search}/page.tsx` | component | request-response | `executions/page.tsx` + `runs-table.tsx` | exact | DIRECT-REUSE style |
| `components/**/*-table.tsx` (all P10 tables) | component | — | `components/executions/runs-table.tsx` (shadcn `table`) | exact | DIRECT-REUSE |
| `app/(dashboard)/admin/users/page.tsx` | component | CRUD (role mutation) | `executions/page.tsx` useMutation + sonner | role-match | NET-NEW (thin) |

---

## Pattern Assignments

### `app/models/user.py` (MOD: +`role` column) — model

**Analog:** `apps/api/app/models/scenario.py` (the `status` String(16) + `server_default` convention)

**Copy the `status`-style enum-string column** (`scenario.py:43`):
```python
# draft | approved | rejected — guarded at the service layer (scenario_service.VALID).
status: Mapped[str] = mapped_column(String(16), server_default="draft")
```
**Apply to user.py** — a `role: Mapped[str] = mapped_column(String(16), server_default="admin")`. Vocab `admin | qa_lead | qa_engineer | developer` (10-RESEARCH A2: String(16) mirrors the project status/class-vocab convention; `defects.py:42` is the same String(16) class-vocab precedent). The current `User` model (`user.py:11-19`) has only id/email/password_hash/created_at — `role` is the single addition.

---

### `alembic/versions/0010_user_role.py` — migration

**Analog:** `apps/api/alembic/versions/0009_defects.py` (the reversible-migration template; 0010 chains `down_revision='0009'`)

**Copy the revision-header + up/down structure** (`0009_defects.py:36-46, 89-98`):
```python
revision: str = '0010'                  # <- bump
down_revision: Union[str, Sequence[str], None] = '0009'   # <- chain after 0009
```
**Copy the `add_column` op** (`0009_defects.py:46`) for the role column — but with `server_default` (10-RESEARCH Pitfall 6 / Runtime State Inventory): existing rows (the seeded admin) MUST get a valid role.
```python
def upgrade() -> None:
    op.add_column('users', sa.Column('role', sa.String(length=16),
                  server_default='admin', nullable=False))
def downgrade() -> None:
    op.drop_column('users', 'role')
```
**Reversibility is a phase gate** (`0009_defects.py:24-26` note — the up/down/up alembic command). Also update `seed_admin` (`main.py:47-65`) so a newly-seeded admin gets `role='admin'` on create.

**Migrations live in `apps/api/alembic/versions/` (NOT `app/alembic`)** — confirmed: the 0001–0009 chain is all there.

---

### `app/core/security.py` (MOD: +`require_role`) — middleware/DI (NET-NEW fn on a direct-reuse seam)

**Analog:** `apps/api/app/core/security.py` `get_current_user` (`security.py:120-141`) + the router-level gate in `routers/scenarios.py:50-55`

**`get_current_user` already fetches the `User` row** (`security.py:138`): `user = await db.scalar(select(User).where(User.id == user_id))`. The JWT carries only `{sub, type, iat, exp, jti}` (`security.py:50-67`) — `sub` is the user id, NOT the role. So **read `user.role` off the row** (10-RESEARCH A1 / Pattern 1 — strictly safer than baking into the token; no stale-role window). Flag this as a deviation-with-rationale for the planner against CONTEXT's "JWT carries the role."

**The new factory composes on `get_current_user`:**
```python
def require_role(*allowed: str):
    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user
    return _dep
```

**Router-gate usage** mirrors `scenarios.py:50-55` (router-level `dependencies=[...]`):
```python
router = APIRouter(prefix="/api/dashboards",
    dependencies=[Depends(require_role("admin", "qa_lead", "developer"))])
```

---

### `app/routers/auth.py` (MOD: `/me` returns role) + `app/schemas/auth.py`

**Analog:** `routers/auth.py:69-71` (`/me`) + `schemas/auth.py:11-12` (`MeResponse`)

**Current `/me`** (`auth.py:69-71`): `return MeResponse(id=user.id, email=user.email)`. Add `role=user.role`. **`MeResponse`** (`schemas/auth.py:11-12`) gains `role: str`. Add a `RoleAssignRequest(BaseModel)` with `role: str` alongside (same file, same `BaseModel` style as `LoginRequest`).

---

### `app/routers/users.py` (NET-NEW, thin) — router, CRUD

**Analog:** `routers/scenarios.py:50-55` (Admin-gated router) + `routers/auth.py` (the User-row read/write idiom)

- Router-level gate `dependencies=[Depends(require_role("admin"))]` (the privilege-escalation mitigation, 10-RESEARCH Security: a user cannot set their own role).
- `GET /api/users` → list `User` rows (`select(User)` per `security.py:138` style).
- `POST /api/users/{id}/role` → set role on the row; **self-demote guard** (the current admin cannot change their own role — 10-RESEARCH Security V4).

---

### `app/services/dashboards.py` (DIRECT-REUSE style) — service, aggregation

**Analog:** `apps/api/app/services/exec_history.py` (VERBATIM query style — `exec_history.py` already documents "the dashboard history UI (Phase 10)")

**Copy the `date_trunc` per-day trend bucketing** (`exec_history.py:32-37`, the "Don't Hand-Roll" SQL bucketing):
```python
day = func.date_trunc("day", TestRun.created_at).label("day")
total = func.sum(TestRun.total).label("total")
passed = func.sum(TestRun.passed).label("passed")
rows = (await db.execute(select(day, total, passed).group_by(day).order_by(day))).all()
```
**Copy the group-by-count idiom** (`exec_history.py:85-93`, `flaky_leaderboard`) for:
- DASH-03 root-cause groupings → group `Classification` by `classification` + `fingerprint` (from `defects.py:34-50`), order by count desc.
- DASH-03 module breakdown → group `TestResult`/`Classification` by `flow_id` (from `execution_history.py:65`), order by failure count desc.
- DASH-01 defect counts → count `Defect` rows (`defects.py:53-76`) by status/class.

**Reuse `exec_history.list_runs` / `get_run_status` directly** (`exec_history.py:97-138`) for the DASH-02 QA history + per-flow results. Module-level `async def fn(db: AsyncSession)` returning plain dicts/lists — no raw SQL, no ORM lazy loads (the documented exec_history discipline).

---

### `app/services/coverage_dash.py` (NET-NEW DASH-04 metric) — service, cross-store join

**Analog (composition):** `kg/flows.mine_flows_from_neo4j` (`flows.py:274-285`) for the flow set + `exec_history.py` select-style for the Postgres side. **Shape-analog (NOT a copy-from):** `kg/coverage.py` — a SEPARATE metric (Pitfall 5).

**This is a DISTINCT module from `kg/coverage.py`.** `kg/coverage.py:92-134` computes ground-truth exploration completeness (matched GT pages ÷ committed fixture). DASH-04 is lifecycle coverage (approved scenario AND passing execution). Keep separate services + separate displayed definitions (10-RESEARCH Pitfall 5; DASH-04 test asserts "no shared code path").

**Pure join** (10-RESEARCH Code Examples — composition of `mine_flows_from_neo4j` + the `exec_history` select style):
```python
mined = await mine_flows_from_neo4j(driver=driver)            # {"flows":[...]}
discovered_ids = {f"flow-{i}" for i in range(len(mined["flows"]))}   # flows.py:262 id convention
approved = set((await db.scalars(
    select(Scenario.flow_id).where(Scenario.status == "approved").distinct())).all())  # scenario.py:35,43
passing = set((await db.scalars(
    select(TestResult.flow_id).where(TestResult.verdict == "passed").distinct())).all())  # execution_history.py:65,68
covered = discovered_ids & approved & passing
```
**flow_id stability caveat (Pitfall 2 / A3):** `flow-{i}` is positional (`flows.py:262`, `id=f"flow-{i}"`). Compute against the CURRENT mining and surface the honest definition. The honest `"definition"` string ships IN the response payload (the `kg/coverage.py:126-133` "return the figures + the matched set" precedent — never a fabricated percent; `coverage_percent` is `0.0` when total is 0).

---

### `app/services/traceability.py` (NET-NEW pure join) — service, cross-store join

**Analog:** `exec_history.get_run_status` (`exec_history.py:104-138`, the "resolve a key → assemble related rows → return a dict" shape) + the FK-linked models.

**The join keys already exist** (Phase 9 wired them — `defects.py:18-20`: "run_id/flow_id ARE the test<->flow<->execution link (JIRA-04): the Defect row joins to TestRun/TestResult + the kg/flows id; Phase 10 renders the chain"). Every lifecycle table threads `run_id` (String(64)) + `flow_id` (String(255)): `scenario.py:33-35`, `execution_history.py:63-65, 87-88`, `defects.py:39-40, 58-59`.

**Assembly** (10-RESEARCH Code Examples — entry by any artifact id flow/scenario/run/defect):
- flow side: `kg/reader.flows_source` / `mine_flows_from_neo4j` (`reader.py:188-214`, `flows.py:274`) for the flow name/steps.
- scenarios: `select(Scenario).where(flow_id ...)` incl. the generated script path.
- executions/artifacts: `TestRun` + `TestResult` + `TestArtifact` by `run_id`+`flow_id` (`execution_history.py`).
- defects: `Classification` + `Defect` by `run_id`+`flow_id` incl. `jira_key` (`defects.py:68`).

**Script path is convention-derived, NOT a stored column (A4 — CONFIRMED):** `codegen/project.py:4-14` documents the layout `workspaces/<run_id>/<target>/{pages,steps,features,...}` via `core.workspaces.run_dir`. Derive the path from the Scenario's `run_id`; if no path is persisted, the chain shows scenario→execution directly and notes the script is derived.

**NO new graph writes** (D-03 / 10-RESEARCH Anti-Patterns): the single-write-path grep gate must stay green — `reader.py:7-8` and `flows.py:26-29` both document "this module holds NO write-Cypher." Traceability joins on read; it does NOT write lifecycle nodes into Neo4j.

---

### `app/core/es_client.py` (NET-NEW, mirror) — config, lifespan singleton

**Analog:** `apps/api/app/core/neo4j_driver.py` (MIRROR verbatim — lazy singleton, init/get/close)

**Copy the lazy-singleton lifespan shape** (`neo4j_driver.py:25-63`):
```python
_es: AsyncElasticsearch | None = None
def init_es() -> AsyncElasticsearch:        # lazy — no connect at construct (neo4j_driver.py:28-44)
    global _es
    if _es is None:
        _es = AsyncElasticsearch(settings.elasticsearch_url)
    return _es
async def close_es() -> None: ...           # neo4j_driver.py:47-52
def get_es() -> AsyncElasticsearch: ...      # neo4j_driver.py:55-63 (opens lazily if init not run)
```
**Graceful-boot contract** (`neo4j_driver.py:13-18`): the driver opens LAZILY so `init_es()` at startup never blocks/fails when ES is down (the `search` profile is OFF by default). Use `AsyncElasticsearch` ONLY (never the sync client — 10-RESEARCH Anti-Patterns).

---

### `app/main.py` (MOD) — ES lifespan + 503 handler

**Analog:** `main.py:68-103` (the neo4j lifespan calls + `_neo4j_unavailable_handler`)

**Copy the lifespan init/close pair** (`main.py:71-85`): add `init_es()` next to `init_neo4j()` (line 72) and `await close_es()` next to `close_neo4j()` (line 83).

**Copy the 503 exception handler** (`main.py:91-103`) — mirror it for ES:
```python
@app.exception_handler(ESConnectionError)   # from elasticsearch.exceptions import ConnectionError
async def _es_unavailable(request, exc):
    log.warning("es_unavailable", path=str(request.url.path))    # main.py:99
    return JSONResponse(status_code=503,
        content={"detail": "Search is unavailable — start the search profile to use it."})
```
**Include the new routers** mirroring `main.py:107-129` — BEFORE `stubs_router` if any path overlaps (the kg/scenarios/heals/defects precedent at `main.py:115-128`).

---

### `app/services/search/indexer.py` (NET-NEW) — service, on-write index + backfill

**Analog:** `kg/flows.py` `categorize_flow` broad-except degrade discipline (`flows.py:218-225`)

**Copy the swallow-and-log degrade** (the on-write dual-index must NEVER break the Postgres write — 10-RESEARCH Pitfall 3 / Pattern 4):
```python
try:
    await get_es().index(index="executions", id=f"{run_id}:{flow_id}", document={...})
except Exception as exc:  # noqa: BLE001 — search is best-effort; never break the Postgres write
    log.info("es_index_skipped", error=str(exc))
```
This is exactly the `flows.py:218-225` pattern ("ANY gateway failure degrades... rather than breaking the read path"). **Hook points:** after the Postgres commit in the worker result-persist (`job.py`) + the defect pipeline. **Backfill:** `elasticsearch.helpers.async_bulk` over `select(TestResult)` etc. (10-RESEARCH Code Examples — Don't Hand-Roll the bulk loop). **Index-create/ensure-mappings** step is idempotent like `ensure_constraints` (`main.py:76` — graceful when the store is down).

---

### `app/services/search/query.py` (NET-NEW) — service, ES search

**Analog:** `kg/reader.py` read-service style + 10-RESEARCH ES search example

**Copy the parameterized-query discipline** (`reader.py:5-8`: "All Cypher is parameterized; page-derived text is NEVER interpolated"): pass the user `q` as a structured ES query VALUE (`multi_match.query`), never string-concatenated into the DSL (10-RESEARCH Security — search query injection mitigation):
```python
resp = await get_es().search(index="executions,failures,logs",
    query={"multi_match": {"query": q, "fields": ["error_text", "message", "feature_name"]}},
    highlight={"fields": {"error_text": {}, "message": {}}}, size=50)
```
Connection errors bubble to the `main.py` ES 503 handler (graceful-degrade, never an empty list pretending zero hits).

---

### `app/core/config.py` (MOD) + `infra/docker-compose.yml` (MOD)

**Analog:** `config.py:73-75` (`neo4j_uri` required Setting) + `docker-compose.yml:378-385` (the ES block)

- **config.py:** add `elasticsearch_url: str` next to the neo4j block (`config.py:68-75` style). Compose enumerates env explicitly (the documented "compose does NOT pass the whole .env" rule, `config.py:138`).
- **compose:** the ES block (`docker-compose.yml:378-385`) currently sets only `discovery.type` + `ES_JAVA_OPTS` — **add `xpack.security.enabled=false`, `xpack.security.http.ssl.enabled=false`, `xpack.security.enrollment.enabled=false`** (10-RESEARCH Pitfall 1: ES 9.x defaults security ON; the client connects over plain HTTP only with these). Keep `profiles: [search]`, `mem_limit: 1536m`, the `-Xms512m -Xmx1g` heap (the 3GB-cap discipline).

---

### Frontend: `components/app-sidebar.tsx` (MOD) — component

**Analog:** `apps/web/components/app-sidebar.tsx` (the SAME file — extend it)

**The NAV_ITEMS flat-list contract already anticipates appended Dashboards items** (`app-sidebar.tsx:29-55`). Append the new items (Dashboards, Coverage, Traceability, Search, Users) AFTER "Defects" (`app-sidebar.tsx:54`), each `{icon, label, href}` (`app-sidebar.tsx:35`). **Role-filter off `/me`:** the `/me` useQuery already exists (`app-sidebar.tsx:62-66`); extend the `Me` type (`app-sidebar.tsx:57`) with `role: string` and render each new item only when the static map permits. Add the role badge to the `SidebarFooter` beneath the email (`app-sidebar.tsx:106-111`).

---

### Frontend: `lib/api/{dashboards,coverage,traceability,search,users}.ts` — utility (zod client)

**Analog:** `apps/web/lib/api/executions.ts` (zod-at-the-boundary + `api.get`)

**Copy the zod-parse-on-read idiom** (`executions.ts:108-116`):
```python
export async function listRuns(): Promise<TestRun[]> {
  return z.array(testRunSchema).parse(await api.get("/api/executions"));
}
```
All reads go through the `api` wrapper (`lib/api/client.ts:82-107`) over the same-origin `/api/*` rewrite (httpOnly cookie rides automatically — `client.ts:5-8`). The admin role mutation uses `api.post` (`client.ts:86-91`) with `["users"]` + `["auth","me"]` invalidation, NO optimistic update.

---

### Frontend: dashboard/coverage/traceability/search/admin pages — component

**Analog:** `apps/web/app/(dashboard)/executions/page.tsx` (useQuery + the full state machine)

**Copy the page state machine** (`executions/page.tsx:43-180`): `useQuery` (`retry: false`, line 46) → render `isError` (inline + Retry, lines 134-148) / `isLoading` (skeletons, lines 149-160) / `isEmpty` (honest empty + link, lines 161-171) / populated (lines 172-180). The admin page adds `useMutation` + sonner toast (`executions/page.tsx:49-56` — toast on success only). Pages live in `app/(dashboard)/` (the existing route group).

---

### Frontend: charts — `components/dashboards/*-chart.tsx`

**Analog:** `apps/web/components/executions/trend-charts.tsx` (the recharts Card pattern)

**Copy the Card-wrapped LineChart** (`trend-charts.tsx:78-112`): `ResponsiveContainer` in an `h-64` div, `AXIS_STYLE` mono numerals (`trend-charts.tsx:29`), `stroke="var(--primary)"` for the accent series + `var(--status-neutral)` for muted (`trend-charts.tsx:104, 133`), `isAnimationActive={false}` (reduced-motion, line 107), the `role="img"` + `sr-only` accessible summary (lines 82-83), and the honest `EmptyTrends` (lines 49-62). **Recharts 3.8.1 is ALREADY installed (Phase 7) — zero new dep.**

---

### Frontend: tables — all Phase-10 tables

**Analog:** `apps/web/components/executions/runs-table.tsx` (the vendored shadcn `table` block)

**Copy the shadcn-table composition** (`runs-table.tsx:58-126`): `Table/TableHeader/TableBody/TableRow/TableHead scope="col"/TableCell` from `@/components/ui/table` (lines 16-23). Badges carry their WORD + a colored dot, never color-only (`runs-table.tsx:107-118`, WCAG 1.4.1). Reuse the `--status-*` token mapping verbatim (`runs-table.tsx:26-41`). **`@tanstack/react-table` is NOT installed — CONFIRMED** (no match in `apps/web/package.json`; used nowhere). Build every P10 table on the vendored `table` block with server-driven sort/filter via query params (the `/executions`, `/scenarios`, `/defects` precedent).

---

## Shared Patterns

### Authentication / Authorization (PLAT-04 core)
**Source:** `core/security.py:120-141` (`get_current_user`) + the NEW `require_role` factory + `routers/scenarios.py:50-55` (router-level `dependencies=[...]`)
**Apply to:** EVERY new router (dashboards, coverage, traceability, search, users). Deny-by-default 403 on role mismatch; server-side enforcement is the boundary (frontend nav-hiding is UX-only). The role is read off the `User` row each request (no stale-role window).

### Read-service query style
**Source:** `services/exec_history.py` (whole file — `select`/`scalars`/`func.date_trunc`/`func.count`, module-level `async def fn(db: AsyncSession)` returning plain dicts)
**Apply to:** `dashboards.py`, `coverage_dash.py`, `traceability.py`. No raw SQL, no ORM lazy loads, deterministic + fixture-testable.

### Graceful-degrade when a profile service is down
**Source:** `core/neo4j_driver.py` (lazy driver, boots when down) + `main.py:91-103` (`_neo4j_unavailable_handler` → clean 503) + `kg/flows.py:218-225` (swallow-and-log on the write path)
**Apply to:** the ES client (`es_client.py` mirror), the ES 503 handler (`main.py` mirror), and the on-write index swallow (`search/indexer.py`). Honest "unavailable" 503, never a crash, never an empty list pretending zero hits.

### structlog redaction (do not leak secrets into ES/logs)
**Source:** `core/logging.py:14-24` (the `redact_sensitive` processor masks password/secret/token/credential keys BEFORE the JSON renderer)
**Apply to:** any structlog→ES log path — the ES log indexing must run AFTER redaction (10-RESEARCH Security — Information Disclosure). No new logging config; the existing processor chain (`logging.py:29-39`) stays as-is.

### Migration chain + reversibility
**Source:** `alembic/versions/0009_defects.py` (header `down_revision`, `upgrade`/`downgrade`, the up/down/up gate)
**Apply to:** `0010_user_role.py` (chains `down_revision='0009'`; reversible `downgrade()` drops the column). Migrations in `apps/api/alembic/versions/`.

### Honest server-authoritative UI
**Source:** `runs-table.tsx` (word+dot badges, no fabricated status) + `trend-charts.tsx` (honest empty, no fabricated points) + `executions/page.tsx` (the loading/empty/error/populated state machine, no optimistic state)
**Apply to:** every Phase-10 surface — coverage %, pass rate, defect counts, chain segments (present vs missing), search hits/highlights, and roles render ONLY from the server payload.

---

## No Analog Found

These are NET-NEW with no exact copy-from (a shape-analog is noted; the planner uses 10-RESEARCH Code Examples for the body):

| File | Role | Data Flow | Reason (shape-analog) |
|------|------|-----------|----------------------|
| `app/services/rbac.py` | service | — | A pure static `ROLE_PERMISSIONS` dict — no in-repo constant-map analog. 10-RESEARCH D-01 defines the map (Admin=all; QA Lead=manage+all dashboards; QA Engineer=run+QA; Developer=read+Dev). |
| `app/services/coverage_dash.py` | service | transform | DASH-04 is a NEW metric — `kg/coverage.py` is only a SHAPE analog (deliberately separate; Pitfall 5). Body = 10-RESEARCH coverage-join example. |
| `app/services/traceability.py` | service | transform | A net-new cross-store assembly — `exec_history.get_run_status` is the closest SHAPE (resolve key → assemble related rows). Body = 10-RESEARCH chain example. |
| `app/services/search/{indexer,query}.py` + `app/core/es_client.py` | service/config | file-I/O / search | The ES integration is net-new (no ES code exists in-repo). `es_client.py` MIRRORS `neo4j_driver.py`; `indexer.py` reuses the `flows.py` degrade discipline; the index/search/bulk API surface comes from 10-RESEARCH (elasticsearch-py 9.4 + `async_bulk`). |

---

## Metadata

**Analog search scope:** `apps/api/app/core/`, `app/models/`, `app/routers/`, `app/services/` (kg, exec_history, codegen), `app/schemas/`, `alembic/versions/`, `apps/web/components/`, `apps/web/lib/api/`, `apps/web/app/(dashboard)/`, `infra/docker-compose.yml`.
**Files scanned:** ~25 (security, user, auth, neo4j_driver, exec_history, main, executions router, scenarios router, scenario/execution_history/defects models, kg reader/flows/coverage, config, logging, 0009 migration, codegen project, compose ES block, app-sidebar, api client, executions lib, executions page, trend-charts, runs-table).
**Key confirmations:** migrations in `apps/api/alembic/versions/` (NOT `app/alembic`); 0010 chains `down_revision='0009'`; `@tanstack/react-table` NOT in `apps/web/package.json` (tables use the vendored shadcn `table`); recharts 3.8.1 already installed; ES compose block at `docker-compose.yml:378-385` lacks the xpack-disable env (Pitfall 1); single-write-path discipline holds (reader/flows hold NO write-Cypher — traceability adds none).
**Pattern extraction date:** 2026-06-28
