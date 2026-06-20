# Phase 7: Execution Engine & Workers - Pattern Map

**Mapped:** 2026-06-20
**Files analyzed:** 28 (new + modified)
**Analogs found:** 24 / 28 (4 are NET-NEW mechanisms with no close analog)

> **Phase posture (carry from RESEARCH "Key insight"):** Phase 7 is overwhelmingly an ASSEMBLY/UPGRADE phase. The only genuinely NEW code is the aio-pika consumer/producer topology, the worker container entrypoint, the GH Actions trigger workflow, and the pure flaky classifier. Almost everything else is DIRECT-REUSE or UPGRADE-IN-PLACE of a battle-tested seam. Each file below is tagged:
> - **DIRECT-REUSE** — wrap/call the analog verbatim; copy its discipline 1:1.
> - **UPGRADE-IN-PLACE** — edit an existing file, following its own internal pattern.
> - **NET-NEW** — no close analog; build from the cited shape + RESEARCH patterns (flag for the planner).

---

## File Classification

### Backend (Python)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/services/worker/consumer.py` | worker entrypoint loop | pub-sub (AMQP consume) | *(none — aio-pika topology)* | NET-NEW |
| `app/worker_main.py` | worker container entrypoint | event-driven | `app/main.py` lifespan (init_redis/init_neo4j) | role-match |
| `app/services/worker/job.py` | service (per-flow job runner) | request-response (subprocess) | `app/services/stability.py` `_run_spec_once` | exact |
| `app/services/worker/classifier.py` | utility (pure rule) | transform | `app/services/kg/risk.py` (pure, table-testable) | exact |
| `app/services/worker/progress.py` | service (publish) | pub-sub | `app/services/explorer/progress.py` | exact |
| `app/services/exec_service.py` | service (tier resolve + enqueue + kill) | CRUD + pub-sub (AMQP produce) | `app/services/run_service.py` + producer is NET-NEW | role-match (producer NET-NEW) |
| `app/services/exec_history.py` | service (history queries) | CRUD | `app/services/run_service.py` | role-match |
| `app/routers/execute.py` (extend) OR new `app/routers/executions_v2.py` | router | request-response + streaming (SSE) | `app/routers/explore.py` (SSE + stop + screenshot guard) | exact |
| `app/models/execution_history.py` | model | CRUD | `app/models/run.py` + `app/models/scenario.py` | exact |
| `alembic/versions/0007_execution_history.py` | migration | — | `alembic/versions/0006_scenarios.py` | exact |
| `app/schemas/execution.py` | schema | — | `app/schemas/run.py` | exact |
| `app/templates/conftest.py.j2` (extend) | config (codegen template) | file-I/O | itself (extend) + `stability._BASE_URL_ENV` | UPGRADE-IN-PLACE |
| `app/services/codegen/project.py` (extend) | service (codegen) | file-I/O | itself (extend — marker registration) | UPGRADE-IN-PLACE |

### Frontend (Next.js / TypeScript)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/(dashboard)/executions/page.tsx` | page (launcher + history) | request-response (TanStack Query) | `app/(dashboard)/scenarios/page.tsx` | exact |
| `app/(dashboard)/executions/[runId]/page.tsx` | page (live view + terminal detail) | streaming (SSE) | `app/(dashboard)/explore/[runId]/page.tsx` | exact |
| `lib/api/executions.ts` | api client (zod) | request-response + streaming | `lib/api/explore.ts` + `lib/api/scenarios.ts` | exact |
| `components/executions/counter-tile.tsx` *(or reuse explore's)* | component | — | `components/explore/counter-tile.tsx` | exact (reusable as-is) |
| `components/executions/status-pill.tsx` | component | — | `components/explore/status-pill.tsx` | exact |
| `components/executions/verdict-badge.tsx` | component | — | `components/scenarios/status-badge.tsx` + `components/explore/status-pill.tsx` DOT map | role-match |
| `components/executions/runs-table.tsx` | component | — | `app/(dashboard)/scenarios/page.tsx` Table block | exact |
| `components/executions/trend-charts.tsx` | component (Recharts) | — | *(none — Recharts not yet installed)* | NET-NEW (gated dep) |
| `components/executions/terminal-banner.tsx` | component | — | `components/explore/terminal-banner.tsx` | exact |
| `components/app-sidebar.tsx` (modify) | component (nav) | — | itself (append `NAV_ITEMS`) | UPGRADE-IN-PLACE |

### Infra / CI

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `infra/docker-compose.yml` (modify) | config | — | itself (the `api` + `rabbitmq` blocks) | UPGRADE-IN-PLACE |
| `.github/workflows/run-suite.yml` | config (CI) | request-response | *(none — no `.github/workflows/` exists)* | NET-NEW |

---

## Pattern Assignments

### `app/services/worker/job.py` (service, request-response) — DIRECT-REUSE

**Analog:** `app/services/stability.py` `_run_spec_once` (the per-run subprocess primitive) + `app/services/execution.py` `run_execution` (the fresh-session-finish shape).

**Subprocess discipline to copy VERBATIM** (`stability.py` lines 58-96): argv LIST, no shell, `cwd=_run_cwd()` imported from `execution.py`, combined stdout/stderr, `_OUTPUT_TAIL_CHARS` cap, `FileNotFoundError` → honest failure (never crash). The Phase-7 worker EXTENDS this argv with the pytest-playwright capture flags (D-04) and the per-attempt retry loop (D-05).

```python
# stability.py:58-96 — the exact subprocess shape to reuse. base_url override via env
# (TARGET_BASE_URL) is the SAME mechanism the determinism harness needs.
env = os.environ.copy()
if base_url is not None:
    env[_BASE_URL_ENV] = base_url   # _BASE_URL_ENV = "TARGET_BASE_URL"
proc = await asyncio.create_subprocess_exec(
    "uv", "run", "pytest", spec_path, "-q",
    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    cwd=_run_cwd(), env=env,
)
out, _ = await proc.communicate()
exit_code = proc.returncode
output = (out.decode(errors="replace") if out else "")[-_OUTPUT_TAIL_CHARS:]
```

**Phase-7 EXTENSION** (per RESEARCH Pattern 4 — capture flags appended to the SAME argv list, no shell):
```python
argv = [
    "uv", "run", "pytest", spec_path, "-q",
    "--screenshot=on",            # ALWAYS (D-04)
    "--tracing=on",               # ALWAYS — trace carries console+network (D-04)
    "--video=retain-on-failure",  # video ON FAILURE ONLY (D-04)
    "--output", str(run_artifacts_dir),   # under workspaces/<run_id>/ (run_id-derived)
]
```

**Fresh-session-finish to copy** (`execution.py` lines 85-92 — Pitfall 2): the worker opens its OWN `SessionLocal` after the retry loop, never a request session.
```python
async with SessionLocal() as db:                       # FRESH session (Pitfall 2)
    await exec_history.record_result(db, run_id, flow_id, verdict, artifact_paths=...)
```

**Kill-check seam** (mirrors `explore.py` `explore_stop` flag + the explorer loop-top check): read `get_redis().get(f"run:{run_id}:kill")` BEFORE pulling/running each attempt; on set, publish an `aborted` event and return (D-07). See `progress.py` analog below for the publish.

---

### `app/services/worker/classifier.py` (utility, transform) — DIRECT-REUSE (shape)

**Analog:** `app/services/kg/risk.py` — a PURE, stdlib-only, table-testable module (no I/O, no graph driver, no LLM). Copy its discipline exactly: the SC3 NO-LLM gate and the unit test will assert this module imports nothing from the DB/graph/LLM path.

**Pattern to copy** (`risk.py` lines 41-58 — pure function over a plain dict, deterministic, table-testable):
```python
# risk.py is the canonical "pure deterministic verdict" shape. classify_retry mirrors it:
# inputs are plain values (the per-attempt exit codes), output is a plain dict, NO I/O.
def classify_retry(attempt_exit_codes: list[int]) -> dict:
    passed = any(code == 0 for code in attempt_exit_codes)
    retried = len(attempt_exit_codes) > 1
    if passed:
        verdict = "flaky" if retried else "passed"      # passed-on-retry => flaky (D-05)
    else:
        verdict = "product_failure"                     # all attempts failed => product
    return {"verdict": verdict, "attempts": len(attempt_exit_codes),
            "passed": passed, "exit_codes": attempt_exit_codes}
```
RESEARCH §"Code Examples" has the full reference body. Verdict vocabulary: `passed | flaky | product_failure | aborted` (matches the per-test verdict tokens in 07-UI-SPEC).

---

### `app/services/worker/progress.py` (service, pub-sub) — DIRECT-REUSE

**Analog:** `app/services/explorer/progress.py` — the publish half of the Redis pub/sub → SSE seam.

**Pattern to copy** (`explorer/progress.py` lines 21, 68-75): reuse the SAME lifespan `get_redis()` client — NEVER a second client (PITFALLS note). Publish `model_dump_json()` text to a run-scoped channel; a publish to a zero-subscriber channel is a no-op.
```python
from app.core.redis_client import get_redis      # the ONE shared client (redis_client.py:41)

async def publish_test_event(run_id: str, flow_id: str, *, status: str, attempt: int,
                             duration_s: float = 0.0) -> None:
    event = {...}                                  # absolute per-test values (see SSE schema)
    await get_redis().publish(f"exec:{run_id}", json.dumps(event))   # run-scoped channel
```
**Channel naming carry-over:** explorer uses `explore:{run_id}`; the kill flag in `explore.py` uses `explore:cancel:{run_id}`. Phase-7 uses `exec:{run_id}` (progress) and `run:{run_id}:kill` (kill flag, per CONTEXT D-07). Define the per-test event as a `shared/events` model (mirrors `ExploreProgressEvent`) so the zod schema in `lib/api/executions.ts` mirrors it 1:1.

---

### `app/routers/execute.py` (extend) — router, request-response + streaming — DIRECT-REUSE

**Analog:** `app/routers/explore.py` — the canonical SSE + stop-flag + path-guarded-artifact router. This is the EXACT template for the execution router's `events` (SSE), `kill` (flag), and `artifacts` (containment-guarded FileResponse) endpoints.

**Router auth gate** (`explore.py` lines 35-40 — router-level `Depends(get_current_user)`; EventSource can't set headers, so the httpOnly cookie is the only auth):
```python
router = APIRouter(prefix="/api", tags=["execute"],
                   dependencies=[Depends(get_current_user)])   # every route auth-gated
```

**SSE endpoint to copy** (`explore.py` lines 90-122 — snapshot-first reconnect, forward loop, `finally` unsubscribe):
```python
@router.get("/executions/{run_id}/events")
async def execution_events(run_id, request, db=Depends(get_db)) -> EventSourceResponse:
    snapshot = await _snapshot_event(db, run_id)   # terminal state on (re)connect, no replay
    async def event_generator():
        pubsub = get_redis().pubsub()
        await pubsub.subscribe(f"exec:{run_id}")
        try:
            if snapshot is not None:
                yield {"event": "snapshot", "data": snapshot}
            async for message in pubsub.listen():
                if await request.is_disconnected(): break
                if message is None or message.get("type") != "message": continue
                yield {"event": "test", "data": message["data"]}
        finally:
            await pubsub.unsubscribe(f"exec:{run_id}"); await pubsub.aclose()
    return EventSourceResponse(event_generator())
```

**Artifact path-traversal guard to copy VERBATIM** (`explore.py` lines 125-144 — the screenshot route; RESEARCH Security Domain mandates reuse for artifact serving):
```python
# Reject anything that is not a bare filename BEFORE touching the filesystem.
if not name or "/" in name or "\\" in name or os.sep in name or ".." in name:
    raise HTTPException(status_code=400, detail="invalid artifact name")
base = run_dir(run_id).resolve()
target = (base / name).resolve()
if target != base and base not in target.parents:    # containment guard
    raise HTTPException(status_code=400, detail="invalid artifact path")
```

**Kill endpoint** (`explore.py` lines 147-156 — the cooperative stop flag; Phase-7 ADDS the aio-pika `queue.purge()` per RESEARCH Pattern 3):
```python
@router.post("/executions/{run_id}/kill")
async def kill_run(run_id: str) -> dict:
    await get_redis().set(f"run:{run_id}:kill", "1")    # worker checks between tests (D-07)
    # NET-NEW: also purge the queue of this run's pending jobs (aio-pika — RESEARCH Pattern 3)
    return {"stopping": True}
```

**POST start endpoint** (`execute.py` lines 34-55 — 202 + run_id, create row, enqueue): the Phase-7 `POST /executions {tier}` replaces the BackgroundTask `bg.add_task(run_execution, ...)` with an aio-pika enqueue (NET-NEW producer), but keeps the 202-shape and the `run_service.create_*` row creation.

---

### `app/models/execution_history.py` (model, CRUD) — DIRECT-REUSE

**Analog:** `app/models/run.py` (the `run_id`-keyed status row, indexed) + `app/models/scenario.py` (the `String(64)`/`String(255)` + `JSON` + `server_default` + timestamp columns).

**Column conventions to copy** (`run.py` lines 26-58 + `scenario.py` lines 28-53): `Mapped[...] = mapped_column(...)`, `run_id: String(64) index=True`, `flow_id: String(255) index=True`, `status: String(16) server_default=...`, `exit_code: Integer nullable`, `JSON` for structured sidecars (here `exit_codes`), `created_at` with `server_default=func.now()`.
```python
class TestRun(Base):                       # one row per tier run (RESEARCH data model)
    __tablename__ = "test_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tier: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default="queued")
    total: Mapped[int] = mapped_column(Integer, server_default="0")
    # ... passed / failed / flaky / started_at / finished_at(nullable) / created_at
# TestResult (run_id, flow_id indexed; verdict; attempts; exit_codes JSON; duration_ms),
# TestArtifact (run_id, flow_id indexed; kind; path String(1024)) — PATHS only, no binaries.
```
**Registration carry-over:** add the new models to `main.py`'s `# noqa: F401` import block (lines 19-21) for Base.metadata/Alembic discovery, exactly like `Scenario` was added.

---

### `alembic/versions/0007_execution_history.py` (migration) — DIRECT-REUSE

**Analog:** `alembic/versions/0006_scenarios.py` — the migration-chain shape.

> **CRITICAL path note (per the prior fix in commit 1166eae):** migrations live in `apps/api/alembic/versions/`, **NOT** `apps/api/app/alembic/`. The compose bind-mount is `../apps/api/alembic:/app/alembic` (docker-compose.yml line 88).

**Pattern to copy** (`0006_scenarios.py` lines 18-50 — the `revision`/`down_revision` chain, `op.create_table` with the same column types, `op.create_index(op.f(...))`, the APP-TABLES-ONLY caveat, the `downgrade()` mirror):
```python
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'   # chains AFTER 0006
# APP TABLES ONLY — LangGraph checkpoint tables are AsyncPostgresSaver.setup()-owned (0005/0006 caveat carries).
def upgrade() -> None:
    op.create_table('test_runs', ...)          # mirror the scenario column style exactly
    op.create_table('test_results', ...)
    op.create_table('test_artifacts', ...)
    op.create_index(op.f('ix_test_results_run_id'), 'test_results', ['run_id'], unique=False)
    # ... index run_id + flow_id on results/artifacts, run_id UNIQUE on test_runs
```
The self-migrating api entrypoint applies it on next boot (no rebuild — alembic dir is bind-mounted).

---

### `app/schemas/execution.py` (schema) — DIRECT-REUSE

**Analog:** `app/schemas/run.py` — request body (`Field(min_length=1)`) + ORM-readable responses (`ConfigDict(from_attributes=True)`) + the small poll shape (`RunStatus`).

**Pattern to copy** (`run.py` lines 29-69):
```python
class ExecuteTierRequest(BaseModel):           # mirror ExecuteRequest
    tier: str = Field(...)                      # validate against an allow-list (V5; RESEARCH Security)
class TestRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)   # built straight from the ORM row
    # run_id, tier, status, total, passed, failed, flaky, started_at, finished_at ...
```

---

### `app/services/exec_service.py` (service) — role-match (producer half NET-NEW)

**Analog:** `app/services/run_service.py` (status machine + `create_run` + `VALID` guard + `list_*`) for the row-management half; `app/services/scenarios.py` `_flow_risk_index` + `app/services/kg/risk.py` for the risk-based tier resolution.

**Row/status pattern to copy** (`run_service.py` lines 24-64): the `VALID` set guard (`_validate_status`), `create_run` with a fresh `uuid.uuid4().hex` run_id, `set_status` guarded transitions, `list_runs`.

**Risk-based tier resolution to copy** (`scenarios.py` lines 66-83 `_flow_risk_index` — the timeout-bounded graph read that degrades gracefully when neo4j is down): risk-based reads `kg/flows` + `kg/risk.risk_score` BEFORE the run phase (D-03b sequencing), then materializes the top-N spec list. Reuse the `asyncio.wait_for(..., timeout=_RISK_TIMEOUT_S)` graceful-degrade shape.

**Tier→selector map** (RESEARCH Pattern 5 — a plain dict, no analog needed):
```python
TIER_SELECTOR = {"smoke": ["-m","smoke"], "sanity": ["-m","sanity"],
                 "regression": ["-m","regression"], "full": []}   # risk-based: explicit spec paths
```

**The enqueue half is NET-NEW** — see "Shared Patterns → AMQP producer" below.

---

### `app/services/exec_history.py` (service, CRUD) — role-match

**Analog:** `app/services/run_service.py` `list_*` + `app/routers/scenarios.py` query helpers. The trend/duration/flaky SQL is spelled out in RESEARCH §"Execution-History Data Model" (pass-rate trend, durations, flaky leaderboard, failure-history-for-risk). Use SQLAlchemy 2.0 `select(...)` + `db.scalars(...)` exactly as `run_service.list_runs` (lines 133-138).

---

### `app/templates/conftest.py.j2` (extend) — UPGRADE-IN-PLACE

**Analog:** itself. The generated conftest ALREADY reads `TARGET_BASE_URL` (lines 22-31) — the env-repointable base URL gives Docker/CI parity for free (D-08) and is the SAME override the determinism harness uses. Phase-7 EXTENSIONS:
1. Register the pytest-bdd tier markers (`smoke`/`sanity`/`regression`) so `-m smoke` selects (RESEARCH Pitfall 3 — unregistered markers warn/select-nothing). Either here or in the generated project's `pyproject.toml [tool.pytest.ini_options] markers` (mirror the api's own marker block, pyproject.toml lines 56-61).
2. OPTIONAL plain-text console/network log hooks (`page.on("console", ...)`) if `--tracing=on` is deemed insufficient (RESEARCH Pattern 4 / A3) — extend the existing fixture, do not add a new template.

> This template is rendered through `_render_checked_py` (`codegen/project.py` line 234) which ast-parses every `.py` — keep the Jinja output valid Python.

---

### `app/services/codegen/project.py` (extend) — UPGRADE-IN-PLACE

**Analog:** itself. If marker registration goes in a generated `pyproject.toml`/`pytest.ini` rather than conftest, add a rendered file to the `files` dict (lines 233-247) exactly like `conftest.py`/`fixtures` are added, render it through `_render_checked_py` if it's `.py` (or write directly for a `.toml`/`.ini`), and it lands under `workspaces/<run_id>/<target>/` via the existing write loop (lines 249-255). No structural change — one more entry in the in-memory `files` map.

---

### `app/worker_main.py` (worker container entrypoint) — role-match

**Analog:** `app/main.py` lifespan (lines 60-77) — the startup/shutdown resource-management shape. The worker is the SAME uv project + image (RESEARCH Open Question 1: reuse the api image with a different `command:`), so it shares `get_redis()`, `SessionLocal`, all models/services. The entrypoint:
- calls `init_redis()` (worker publishes progress + reads the kill flag via the SAME client) — copy `main.py` line 63;
- does NOT need neo4j (D-03b — off during runs) or the checkpointer;
- runs the aio-pika consumer loop (NET-NEW — `consumer.py`) until shutdown.

> **SC3 invariant:** worker code MUST NOT import `init_chat_model`/the LLM gateway. A unit grep gate asserts this (RESEARCH EXEC-03 test map). Do not import anything from `app/services/explorer` (LLM path) or the gateway into the worker package.

---

### Frontend: `app/(dashboard)/executions/[runId]/page.tsx` (live view + terminal) — DIRECT-REUSE

**Analog:** `app/(dashboard)/explore/[runId]/page.tsx` — the EXACT live-view template (the 07-UI-SPEC says "mirrors the Phase-4 Live Exploration View verbatim").

**Patterns to copy** (explore `[runId]/page.tsx`):
- Mount-time `GET /api/executions/{runId}` once to resolve 404 / already-terminal — NO parallel polling during a live run (lines 114-135).
- `new EventSource('/api/executions/${runId}/events')` over the same-origin proxy (cookie auth; lines 165-198); `step`/`snapshot` listeners; `onerror` → `reconnecting`/`stream-lost` by `readyState`; close on terminal.
- Absolute-value counters from the latest event (`latest?.X ?? 0`, lines 242-251).
- Feed cap + auto-scroll-only-at-bottom + "Jump to latest" (lines 200-222, 361-370) — retarget the feed to the per-test list (`role="log" aria-live="polite"`).
- The destructive Kill button + confirmation `Dialog` (lines 282-289, 405-432) — copy the focus-trapped dialog; D-07 ADDS the amber "Stopping…" draining state (07-UI-SPEC) which has no Phase-4 analog but reuses the StatusPill amber token.
- The `connecting | running | reconnecting | terminal | stream-lost | not-found` state machine (lines 52-59) — extend with `stopping` (draining).

> 07-UI-SPEC: the SAME route renders the terminal run-detail layout once terminal (no separate route) — the explore page already does this freeze (`conn === "terminal"`).

---

### Frontend: `app/(dashboard)/executions/page.tsx` (launcher + history) — DIRECT-REUSE

**Analog:** `app/(dashboard)/scenarios/page.tsx` — the list-page template (TanStack Query, the Table block, the filter-segment pattern reusable as the tier picker's segmented-control option, loading/empty/error states, inline errors never toasts).

**Patterns to copy** (scenarios `page.tsx`):
- `useQuery({ queryKey: [...], queryFn: () => listX(...), retry: false })` (lines 61-65).
- The `Table`/`TableHeader`/`TableRow`/`TableCell` block + `LoadingRows` skeleton + accent drill-in `<Link>` per row (lines 138-193) — retarget to the runs-history columns (Tier · Started · Duration · Results · Status), a running row drilling into the live view.
- The accent-underlined segmented `<nav>` (lines 82-104) — the documented tier-picker fallback (or a styled-native `<select>`, 07-UI-SPEC; no new shadcn block).
- The centered empty-state card with an accent action link (lines 110-136) — "No runs yet" / "Trends appear after your first run."

> The launcher's `POST /api/executions {tier}` mutation + `POST .../kill` mirror the scenarios mutations (`api.post` + query invalidation, NO optimistic updates — server-authoritative; `lib/api/scenarios.ts` lines 75-91).

---

### Frontend: `lib/api/executions.ts` (zod client) — DIRECT-REUSE

**Analog:** `lib/api/explore.ts` (the SSE event zod schema + start/stop POSTs + the auth-gated artifact-URL builder) + `lib/api/scenarios.ts` (the list/detail fetchers + mutation discipline).

**Patterns to copy:**
- The per-test SSE event `z.object({...})` schema mirroring the backend `shared/events` model 1:1 (`explore.ts` lines 23-35) — the page parses every frame through it.
- `screenshotUrl(runId, name)` → the artifact-URL builder `artifactUrl(runId, flowId, kind)` (`explore.ts` lines 56-59) — run-relative basename, never a raw path.
- The `api.get`/`api.post` fetchers with `schema.parse(...)` at the boundary (`scenarios.ts` lines 64-91).
- `startRun(tier)` / `killRun(runId)` mirror `startExplore`/`stopExplore` (`explore.ts` lines 39-54).

---

### Frontend: reusable components — DIRECT-REUSE

- `components/explore/counter-tile.tsx` — **reuse as-is** for the live counters strip (Passed/Failed/Flaky/Total/Elapsed). The `mono` prop already handles the mono numerals. Either import directly or copy into `components/executions/`.
- `components/explore/status-pill.tsx` — copy + extend the `PillState`/`DOT` map for the run-status pill (add `stopping` → `--status-quarantine` amber, per 07-UI-SPEC). The `--status-*` token map is already exactly the Phase-7 run-status mapping.
- `components/explore/terminal-banner.tsx` — copy for the passed/failed/killed terminal banners.
- `components/scenarios/status-badge.tsx` — analog for the per-test verdict badge (word + color, never color-only — WCAG 1.4.1; the 07-UI-SPEC verdict→token map matches the StatusPill `DOT` shape).

---

### Frontend: `components/app-sidebar.tsx` (modify) — UPGRADE-IN-PLACE

**Analog:** itself. Append ONE entry to `NAV_ITEMS` (lines 35-47) following the documented flat-list `{icon, label, href}` contract:
```ts
{ icon: PlayCircle, label: "Executions", href: "/executions" },   // AFTER Scenarios
```
`PlayCircle` from `lucide-react` (add to the import block, lines 6-13). Active via the existing `pathname.startsWith(item.href)` (line 79). The file's own comment already anticipates "Executions" (lines 30-32).

---

### Infra: `infra/docker-compose.yml` (modify) — UPGRADE-IN-PLACE

**Analog:** itself — the `api` service block (lines 44-109) for the worker service body (it reuses the api image + the SAME env + the SAME volume mounts: `app`, `shared`, `workspaces`, `alembic`), the `rabbitmq` block (lines 207-210) for the `profiles: [queue]` + `mem_limit` pattern, and the `saucedemo-bug` block (lines 160-175) for the profile-gated-dormant-service shape.

**Pattern to copy:**
```yaml
  worker:
    build: ../apps/api          # SAME image as api (reuse — RESEARCH Open Q1)
    profiles: [queue]           # joins rabbitmq's profile (line 209) — OFF by default
    mem_limit: 768m             # ~512-768m incl. 2 Chromium contexts (RESEARCH memory math)
    command: ["python", "-m", "app.worker_main"]   # different entrypoint, same image
    environment:                # copy the api env block (lines 47-83) + add:
      AMQP_URL: amqp://...@rabbitmq:5672/          # NET-NEW (Runtime State Inventory)
      WORKSPACES_DIR: /app/workspaces
      EXECUTION_CWD: /app
    volumes:                    # SAME mounts as api (lines 84-96) — shared workspaces tree
      - ../apps/api/app:/app/app
      - ../shared:/app/shared
      - ../workspaces:/app/workspaces
    depends_on:
      rabbitmq: { condition: service_healthy }     # ADD a healthcheck to rabbitmq (it has none yet)
```
> The existing `rabbitmq` block (lines 207-210) has NO healthcheck/ports — add a `rabbitmq-diagnostics ping` healthcheck (the `rabbitmq:4-management` image supports it) for the worker's `depends_on: condition: service_healthy`, mirroring every other service block.

---

## Shared Patterns

### Authentication (router-level cookie gate)
**Source:** `app/routers/explore.py` lines 35-40, `app/routers/scenarios.py` lines 50-55, `app/routers/executions.py` lines 20-24.
**Apply to:** ALL execution routes (start, status, events SSE, kill, artifacts). EventSource can't set headers — the httpOnly `access_token` cookie over the same-origin proxy is the only auth.
```python
router = APIRouter(prefix="/api", tags=["..."],
                   dependencies=[Depends(get_current_user)])
```

### Subprocess discipline (the run primitive)
**Source:** `app/services/execution.py` lines 35-92, `app/services/stability.py` lines 58-96.
**Apply to:** `worker/job.py`. argv LIST, no `shell=True`, `spec_path` run_id-derived (never client input — T-03-15), `cwd=_run_cwd()`, output tail-cap, `FileNotFoundError` → honest failure. NEVER in-process pytest (Pitfall 3 — sync-Playwright-in-asyncio deadlock).

### Fresh session per background unit (Pitfall 2)
**Source:** `app/services/execution.py` lines 85-92.
**Apply to:** every worker job + the consumer — open a fresh `async with SessionLocal() as db:`, never a request session.

### Single Redis client (no second client)
**Source:** `app/core/redis_client.py` (`get_redis()`), `app/services/explorer/progress.py` line 21, `app/routers/explore.py` line 27.
**Apply to:** `worker/progress.py` (publish), the kill-flag read in `worker/job.py`, the SSE subscribe in the router. Always `get_redis()` — never construct a new client.

### Redis pub/sub → SSE live seam (absolute counters, snapshot-on-reconnect)
**Source:** publish `app/services/explorer/progress.py` lines 68-75; SSE re-emit `app/routers/explore.py` lines 90-122; frontend `app/(dashboard)/explore/[runId]/page.tsx`.
**Apply to:** the entire live execution view. Run-scoped channel `exec:{run_id}`; absolute values; snapshot-first reconnect; `finally` unsubscribe.

### Artifact / screenshot path-traversal containment
**Source:** `app/routers/explore.py` lines 125-144.
**Apply to:** the execution artifact-serving route (screenshot/trace/video/logs). Reject `..`/separators before touching the FS; resolve inside `run_dir(run_id)`. RESEARCH Security Domain mandates this reuse.

### Graceful cooperative kill (Redis flag)
**Source:** `app/routers/explore.py` lines 147-156 (set flag) + the explorer loop-top check.
**Apply to:** `kill_run` (set `run:{run_id}:kill`) + the worker's between-tests check (D-07). NET-NEW addition: `queue.purge()` on the aio-pika queue (RESEARCH Pattern 3). No SIGKILL.

### Pure, table-testable verdict modules (SC3 NO-LLM)
**Source:** `app/services/kg/risk.py` (stdlib-only, no DB/graph/LLM imports, swappable frozen weights).
**Apply to:** `worker/classifier.py` (the flaky rule) and the risk-based ranking weights (frozen dataclass like `RiskWeights`, RESEARCH A1 weights `[ASSUMED]`).

### ORM model + migration column conventions
**Source:** `app/models/run.py`, `app/models/scenario.py`, `alembic/versions/0006_scenarios.py`.
**Apply to:** the 3 history tables + migration 0007. `Mapped[...] = mapped_column(...)`, indexed `run_id`/`flow_id`, `String(16)` status with `server_default`, `JSON` sidecars, `func.now()` timestamps, `op.create_index(op.f(...))`. Register new models in `main.py`'s `# noqa: F401` block.

### Frontend boundary discipline (zod + server-authoritative)
**Source:** `lib/api/explore.ts`, `lib/api/scenarios.ts`.
**Apply to:** `lib/api/executions.ts` + both pages. zod-parse every payload/event at the boundary; NO optimistic updates; status/verdict render strictly from the server (the Phase-6 honesty rule — green/amber/red only when the server reports it); inline errors, never toasts (success toasts only).

---

## No Analog Found (NET-NEW — flag for the planner)

These have NO close analog in the codebase and must be built from the cited RESEARCH shapes. They are the genuine new surface of Phase 7.

| File | Role | Data Flow | Why no analog / build-from |
|------|------|-----------|----------------------------|
| `app/services/worker/consumer.py` | worker AMQP consume loop | pub-sub (AMQP) | No aio-pika usage anywhere in the repo (aio-pika is the one new dep). Build from RESEARCH Pattern 1: `connect_robust` + `channel.set_qos(prefetch_count=2)` + `queue.iterator()` + `message.process(requeue=...)`. Memory: prefetch=2 hard ceiling (3GB cap). |
| AMQP producer (in `app/services/exec_service.py`) | enqueue jobs | pub-sub (AMQP) | No AMQP publish anywhere. Build from RESEARCH Pattern 2: `connect_robust` + `Message(..., delivery_mode=PERSISTENT)` + `default_exchange.publish` on a `durable=True` queue, publisher confirms. The row-management half (around it) reuses `run_service`. |
| `components/executions/trend-charts.tsx` | Recharts trend cards | — | Recharts is NOT in `apps/web/package.json` (verified, 07-UI-SPEC). It is the ONE stack-sanctioned frontend add (analogue of backend's `aio-pika`) — gate the `pnpm add recharts@3.8.*` behind the standard verification step. Honest fallback: token-styled native SVG/HTML sparkline over `--status-*` tokens (no new dep). |
| `.github/workflows/run-suite.yml` | CI trigger | request-response | NO `.github/workflows/` directory exists — net-new CI surface. Build from RESEARCH §"GitHub Actions trigger": `workflow_dispatch` → `curl POST /api/execute` (scoped `CI_TOKEN` secret) → poll `GET /api/executions/{run_id}` → map `passed`/`failed` to exit 0/1 (→ GitHub check conclusion). Reachability assumption (A5): self-hosted runner or tunnel — host port 8001 is local. |

> **Gated new dependencies (2, both pre-sanctioned by CLAUDE.md):** `aio-pika==9.6.*` (backend, the one expected runtime dep) and `recharts@3.8.*` (frontend, the one sanctioned chart dep). Both behind a `checkpoint:human-verify` per project policy. NO other new package (e.g. `pytest-rerunfailures`) — the worker-side retry loop avoids it (D-05, RESEARCH).

---

## Metadata

**Analog search scope:** `apps/api/app/services/` (execution, stability, explorer/progress, codegen/project, run_service, scenarios, kg/risk), `apps/api/app/routers/` (explore, execute, executions, scenarios), `apps/api/app/models/`, `apps/api/alembic/versions/`, `apps/api/app/schemas/`, `apps/api/app/templates/`, `apps/api/app/core/` (redis_client, workspaces, main lifespan), `apps/web/app/(dashboard)/` (explore, scenarios), `apps/web/lib/api/`, `apps/web/components/` (explore, scenarios, app-sidebar), `infra/docker-compose.yml`, `.github/` (absent).
**Files scanned:** ~30 source files read; ~6 directory listings.
**Pattern extraction date:** 2026-06-20
