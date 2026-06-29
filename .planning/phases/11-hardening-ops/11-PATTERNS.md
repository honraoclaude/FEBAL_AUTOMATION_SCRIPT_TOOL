# Phase 11: Hardening & Ops - Pattern Map

**Mapped:** 2026-06-29
**Files analyzed:** 24 new/modified
**Analogs found:** 16 with a concrete in-repo analog / 24 (8 are NET-NEW config with no code analog — compose/CLI patterns only)

> Phase 11 adds **no product capability** — it deploys/builds/observes the platform. The bulk is
> infra-as-code (K8s manifests, a CI workflow, Prometheus/Grafana config) plus ONE bespoke ~60-line
> custom collector. Most files are NET-NEW YAML/JSON whose SOURCE is `infra/docker-compose.yml`
> (service block → manifest shape) or a CLI-tool convention, not a Python analog. The one piece of
> real code (the collector + `/metrics`) has strong analogs in the lifespan + graceful-degrade +
> read-service style the repo already ships.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `apps/api/app/core/metrics.py` | service (collector + snapshot refresher) | event-driven (lifespan task) + pull-on-scrape | `apps/api/app/services/dashboards.py` + `core/es_client.py` lifespan | role-match (NET-NEW pattern, strong analogs) |
| `apps/api/app/main.py` (MODIFY) | config (app wiring) | request-response | itself (existing lifespan + 503 degrade handlers) | exact (extend in place) |
| `apps/api/pyproject.toml` (MODIFY) | config | — | itself (the existing pinned `dependencies` list) | exact |
| `apps/api/app/core/config.py` (MODIFY, optional) | config | — | itself (the `ci_token: str \| None = None` optional-secret pattern) | exact |
| `apps/api/Dockerfile` (MODIFY) | config (image build) | — | itself + `infra/targets/saucedemo/Dockerfile` (multi-stage) | exact / role-match |
| `apps/web/Dockerfile` (MODIFY → prod multi-stage) | config (image build) | — | `infra/targets/saucedemo/Dockerfile` (multi-stage `AS build` → runtime) | role-match |
| `.github/workflows/platform-ci.yml` | config (CI/CD) | batch (jobs) | `.github/workflows/run-suite.yml` | role-match (syntax/token precedent; different job shape) |
| `infra/docker-compose.yml` (MODIFY: `monitoring` profile) | config | — | itself (the `profiles: [graph/queue/search]` blocks) | exact |
| `infra/k8s/base/kustomization.yaml` | config (K8s) | — | — (Kustomize layout) | NO ANALOG (CLI convention) |
| `infra/k8s/base/namespace.yaml` | config (K8s) | — | — | NO ANALOG |
| `infra/k8s/base/postgres.yaml` (StatefulSet+PVC+Service) | config (K8s) | CRUD (stateful) | compose `postgres` block (lines 16-31) | role-match (compose→manifest translation) |
| `infra/k8s/base/redis.yaml` (Deployment+Service) | config (K8s) | request-response | compose `redis` block (lines 33-42) | role-match |
| `infra/k8s/base/rabbitmq.yaml` (Deployment+Service, :15692) | config (K8s) | pub-sub | compose `rabbitmq` block (lines 331-345) | role-match |
| `infra/k8s/base/neo4j.yaml` (StatefulSet+PVC+Service) | config (K8s) | CRUD (stateful) | compose `neo4j` block (lines 305-329) | role-match |
| `infra/k8s/base/api.yaml` (Deployment+Service+probes) | config (K8s) | request-response | compose `api` block (lines 44-119) | role-match |
| `infra/k8s/base/worker.yaml` (Deployment) | config (K8s) | event-driven (consumer) | compose `worker` block (lines 352-382) | role-match |
| `infra/k8s/base/web.yaml` (Deployment+Service) | config (K8s) | request-response | compose `web` block (lines 121-141) | role-match |
| `infra/k8s/base/configmap.yaml` + `secret.example.yaml` | config (K8s) | — | compose `environment:` blocks (non-secret vs `${JWT_SECRET}`/`${NEO4J_AUTH}`) | role-match |
| `infra/k8s/overlays/elasticsearch/*` | config (K8s overlay) | search | compose `elasticsearch` block (lines 384-398) | role-match |
| `infra/k8s/monitoring/{prometheus,grafana,exporters}.yaml` | config (K8s) | — | — (exporter images + Prom/Grafana) | NO ANALOG (CLI/image convention) |
| `infra/monitoring/prometheus.yml` | config (scrape) | — | — (Prometheus config) | NO ANALOG |
| `infra/monitoring/grafana/provisioning/{datasources,dashboards}/*` | config (dashboards-as-code) | — | — (Grafana provisioning) | NO ANALOG |
| `apps/api/tests/unit/test_metrics_collector.py` | test | — | existing unit tests under `apps/api/tests/unit` (collector snapshot→gauge + degrade) | role-match |
| `apps/api/tests/integration/test_metrics_endpoint.py` + `tests/unit/test_dashboards_json.py` | test | — | existing `tests/integration` (seed rows → assert) | role-match |

## Pattern Assignments

### `apps/api/app/core/metrics.py` (service: custom Collector + snapshot refresher) — THE ONE BESPOKE FILE

**Status:** NET-NEW pattern (no exact analog), assembled from THREE existing in-repo patterns + the
documented prometheus-client custom-Collector shape (RESEARCH Pattern 1, lines 219-305). Do NOT use
`asyncio.run()` inside `collect()` — use the background-refreshed snapshot.

**Analog 1 — lifespan-managed module-global + lazy/graceful client** (`apps/api/app/core/es_client.py`, full file; identical shape in `neo4j_driver.py`, `redis_client.py`):
```python
_es: AsyncElasticsearch | None = None

def init_es() -> AsyncElasticsearch:          # called from main.py lifespan startup (idempotent)
    global _es
    if _es is None:
        _es = AsyncElasticsearch(settings.elasticsearch_url)
    return _es

async def close_es() -> None:                  # called from lifespan shutdown (idempotent)
    global _es
    if _es is not None:
        await _es.close()
        _es = None
```
Copy this module-global + `init_*`/`close_*`/`get_*` triad shape for `_snapshot` + `_refresh_task`
+ `start_metrics()`/`stop_metrics()`. The `_refresh_task = asyncio.create_task(...)` started in
`start_metrics` mirrors how `init_redis`/`init_neo4j`/`init_es` are started in the lifespan.

**Analog 2 — the 4 metric SOURCES the refresh loop reuses (NEVER recompute; READ these):**

| Gauge | Source function | File:line | Returns |
|-------|-----------------|-----------|---------|
| `qa_platform_heal_success_rate` | `per_element_heal_stats(db)` | `app/services/healing/stats.py:34` | list of `{element_key, attempts, heal_success_rate, false_heal_rate}` — aggregate to platform rate: `sum(healed) / sum(attempts)` (RESEARCH lines 256-261; guard attempts==0 → `None`) |
| `qa_platform_coverage_percent` | `coverage_dash.coverage(db, driver=get_neo4j())` | `app/services/coverage_dash.py:54` | dict with `coverage_percent` (0..100, 1dp) |
| `qa_platform_classification_precision` | NET-NEW small query over `Defect.status` (see D-05 below) | model `app/models/defects.py:53` (`Defect.status` draft/applied/rejected) | applied / (applied+rejected) of REVIEWED rows; zero reviewed → `None` |
| `qa_platform_llm_cost_usd_total` | NET-NEW small `func.sum(LLMUsage.cost_usd)` query | model `app/models/llm_usage.py:19` (`cost_usd Numeric(12,6)`) | total USD spend; cast `Numeric → float` |

**Analog 3 — the EXACT SQLAlchemy `func`-aggregate idioms** for the two NET-NEW small queries
(`app/services/dashboards.py`, `executive()` lines 38-62 — the closest precedent for both):

The D-05 precision numerator/denominator is the `Defect.status`-filtered `func.count` already shipped:
```python
# dashboards.py:50-52 — copy this status-filtered count shape for applied + (applied+rejected)
open_defects = int(
    await db.scalar(select(func.count(Defect.id)).where(Defect.status != "rejected")) or 0
)
# Phase-11 precision: applied = count(status=='applied'); reviewed = count(status IN ('applied','rejected'))
# precision = applied / reviewed  (reviewed == 0 → None, honest absence — D-05)
```
The LLM-cost sum reuses the `func.sum(...)` + `int(... or 0)` null-guard idiom (same file,
`_root_cause_groups`/`failure_rate` style; `func.sum` over a numeric column appears at
`app/services/exec_service.py:120`). Cast the `Numeric` result to `float` for the gauge.

**Core pattern — background snapshot + sync collect (RESEARCH Pattern 1, the verified shape to copy):**
```python
# Each source independently try/excepted → one failure sets that key None (never blanks others,
# never raises into /metrics). This IS the graceful-degrade contract (main.py 503 handlers) applied
# to metrics. collect() is SYNC, reads the cached floats O(1), and OMITS a None gauge (honest
# absence, never a fake 0).
_snapshot: dict[str, float | None] = {...}            # heal/precision/coverage/cost → None
async def _refresh_once() -> None: ...                 # per-source try/except, write floats/None
async def _refresh_loop() -> None: ...                 # while True: await _refresh_once(); sleep(30)
class DomainMetricsCollector(Collector):
    def collect(self):
        for gauge_name, key in ...:
            if _snapshot[key] is None: continue        # omit — Prometheus reads absent as "no data"
            yield GaugeMetricFamily(gauge_name, help, value=_snapshot[key])
```
Full reference implementation is in 11-RESEARCH.md lines 226-305 (verbatim, repo-conventions-adapted).

**Error-handling pattern to mirror** (`apps/api/app/core/es_client.py` docstring lines 11-20 + the
`main.py` 503 handlers lines 109-137): lazy clients boot even when a backing service is down; a down
source NEVER 500s the consumer. For `/metrics` this means: a down Neo4j → coverage gauge simply
absent, `/metrics` still 200. Use `structlog.get_logger()` + `log.warning("metric_refresh_failed", metric=..., error=str(exc))` (the `main.py` `log.warning("neo4j_unavailable", ...)` style, line 117).

---

### `apps/api/app/main.py` (MODIFY — wire `/metrics` + instrumentator into the existing lifespan)

**Analog:** the file ITSELF (extend in place — exact match).

**Lifespan startup/shutdown pattern** (lines 80-104) — add the two calls alongside the existing `init_*`:
```python
# startup (after init_es() / await ensure_indices(...), before/after seed_admin):
start_metrics(app)                                  # register DomainMetricsCollector + start refresher
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
# shutdown (alongside close_neo4j/close_es/close_redis):
await stop_metrics()
```
Imports go with the existing `from app.core.* import ...` block (lines 13-20). The instrumentator
import mirrors how other optional integrations are imported at top of file.

**`/metrics` auth precedent — unauthenticated-but-safe** (the existing `/health` router,
`apps/api/app/routers/health.py:19` — `@router.get("/health")` with NO auth dependency, mounted at
root NOT under `/api`, line 140-141 in main.py). `/metrics` follows the SAME no-auth, root-mounted
convention; it emits only aggregate numerics (RESEARCH Pattern 2 lines 307-323; A4). Document the choice.

---

### `apps/api/pyproject.toml` (MODIFY — the 2 gated new deps)

**Analog:** the existing `[project].dependencies` pinned list (lines 7-40).

**CONFIRMED NOT yet present:** `prometheus-client` and `prometheus-fastapi-instrumentator` are
absent from the current `dependencies` (verified — the list ends at `elasticsearch[async]==9.4.*`,
line 39). Both are CLAUDE.md-locked + slopcheck `[OK]` (RESEARCH lines 119-130). Add EXACTLY these two,
matching the existing `==X.Y.*` pin style (these are GATED — checkpoint:human-verify, the
aio-pika/atlassian-python-api/elasticsearch precedent):
```toml
"prometheus-client==0.25.*",
"prometheus-fastapi-instrumentator==8.0.*",
```
Then `uv lock && uv sync`. NB a machine-global `prometheus-fastapi-instrumentator` 7.1.0 exists —
the pin + running inside `uv` (project venv) is what enforces 8.0.* (RESEARCH Pitfall 7).

---

### `apps/api/app/core/config.py` (MODIFY — optional, only if a scrape token is wanted)

**Analog:** the `ci_token: str | None = None  # env CI_TOKEN` optional-scoped-secret pattern
(`config.py:139`; same shape as `anthropic_api_key`, `jira_api_token`). A4 defers the scrape token —
if added later, copy this `str | None = None  # env METRICS_SCRAPE_TOKEN` line VERBATIM. Default to
NOT adding it this phase.

---

### `apps/api/Dockerfile` (MODIFY — drop dev `--reload` for the published/K8s image, D-06)

**Analog:** the file ITSELF (lines 1-27). The image is already a clean uv multi-stage-ish build
(manifests-first layer cache, `uv sync --frozen --no-dev`, `playwright install`). The ONLY production
change is the CMD: drop `--reload --reload-dir app` and use uvicorn workers.
```dockerfile
# CURRENT (dev, line 27):
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app"]
# PRODUCTION target (drop --reload; add --workers — CLAUDE.md "run with --workers in containers"):
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2"]
```
The worker K8s Deployment reuses this SAME image with the compose worker command
(`["python","-m","app.worker_main"]`, compose line 356) — no second build (compose worker comment,
lines 347-356).

---

### `apps/web/Dockerfile` (MODIFY → production multi-stage, D-06 / RESEARCH Pitfall 3)

**Analog:** `infra/targets/saucedemo/Dockerfile` (lines 22-31) — the repo's canonical multi-stage
`FROM ... AS build` → slim runtime pattern:
```dockerfile
FROM node:16-bullseye AS build      # build stage: clone/install/build
...
RUN npm ci && npm run build
FROM nginx:alpine                    # runtime stage: copy only built artifacts
COPY --from=build /src/build /usr/share/nginx/html
```
Current web Dockerfile (lines 1-16) is DEV-only (`CMD ["npm","run","dev"]`, Turbopack, 1536m). The
production image must follow the saucedemo two-stage shape adapted to Next 16:
`FROM node:22-alpine AS build` → `npm ci && npm run build` → runtime stage running `next start` (NOT
`npm run dev`). **Flag for planner:** the AGENTS.md note warns this Next.js build differs from
training data — read `node_modules/next/dist/...` before changing the build (RESEARCH Pitfall 3).
Keep the existing dev Dockerfile for local compose; add a prod stage/target (or a separate prod file).

---

### `.github/workflows/platform-ci.yml` (NET-NEW — separate from run-suite.yml, D-02)

**Analog:** `.github/workflows/run-suite.yml` (full file) — the Actions-SYNTAX + scoped-token
discipline precedent. This is a DIFFERENT workflow (test-gate + build-publish, not the suite trigger).

**Reuse from run-suite.yml:**
- `name:` / `on:` / `jobs:` / `runs-on: ubuntu-latest` / `steps:` skeleton (lines 23-39).
- The `permissions`/`env` scoping + NEVER-echo-the-token discipline (header comment lines 17-21,
  `env: CI_TOKEN: ${{ secrets.CI_TOKEN }}` line 38). Phase 11 uses `permissions: { contents: read,
  packages: write }` (least-privilege, the built-in `GITHUB_TOKEN` — no PAT, RESEARCH Security V14).

**NET-NEW (not in run-suite.yml) — the two-job test-gate→build-publish shape** (RESEARCH Pattern 4,
lines 355-419, verbatim to copy):
- `test` job: `astral-sh/setup-uv@v6` + `uv sync --frozen` + the KEYLESS lane
  `uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional and not search"`
  (the EXACT marker set from pyproject.toml lines 59-66) + `actions/setup-node@v5` (node 22) +
  `npx tsc --noEmit` + `npx eslint .`.
- `build-publish` job: `needs: test`, matrix `{api: apps/api, web: apps/web}`, `docker/login-action@v4`
  (registry ghcr.io, `${{ secrets.GITHUB_TOKEN }}`), `docker/metadata-action@v5` (`type=sha` +
  `type=raw,value=latest`), `docker/build-push-action@v6` (`cache-from/to: type=gha`).
- **Confirm (Open-Q2):** whether the keyless lane needs `services: postgres`. Inspect
  `apps/api/tests/integration` markers — the `integration` marker ("needs a real Postgres",
  pyproject.toml line 61) is NOT in the excluded set, so any `integration`-marked test runs in the
  keyless lane → add a `services: postgres` container IF present.
- **NEVER publish the saucedemo image** (it is a test fixture — D-02; only `api` + `web` go to GHCR).
- Verify action major-version pins at plan time (RESEARCH A7).

---

### `infra/k8s/base/*.yaml` (NET-NEW manifests — SOURCE is the compose service blocks)

**Analog:** `infra/docker-compose.yml` per-service block → one K8s workload. The translation is
MECHANICAL (RESEARCH Pattern 3, lines 325-353). Per-service source line ranges:

| Manifest | Compose source (file:line) | K8s shape | Key carry-overs |
|----------|----------------------------|-----------|-----------------|
| `postgres.yaml` | lines 16-31 | StatefulSet + PVC + Service | `mem_limit:512m`→`limits.memory:512Mi`; `pg_isready` healthcheck→exec readinessProbe; `pgdata` volume→`volumeClaimTemplates` |
| `redis.yaml` | lines 33-42 | Deployment + Service | `256m`→`256Mi`; `redis-cli ping`→exec probe |
| `rabbitmq.yaml` | lines 331-345 | Deployment + Service | `512m`→`512Mi`; `rabbitmq-diagnostics -q ping`→exec probe; EXPOSE 15692 (metrics, Pitfall 6) |
| `neo4j.yaml` | lines 305-329 | StatefulSet + PVC + Service | `1g`→`1Gi`; the `NEO4J_server_memory_*` env (double-underscore caveat, lines 313-319); wget :7474 probe; CORE (D-01, not the compose `graph` profile) |
| `api.yaml` | lines 44-119 | Deployment + Service + probes | `1g`→`1Gi`; the python-urllib `/health` healthcheck (line 113)→`httpGet: {path:/health, port:8000}` readiness+liveness; image `ghcr.io/honraoclaude/api:<tag>`; env split ConfigMap vs Secret |
| `worker.yaml` | lines 352-382 | Deployment | SAME image as api + `command:["python","-m","app.worker_main"]` (line 356); `768m`→`768Mi`; `EXEC_PREFETCH_COUNT:2` (line 374); no Service (consumer) |
| `web.yaml` | lines 121-141 | Deployment + Service | the prod image (`next start`, D-06); node `fetch` healthcheck (line 135)→httpGet probe; scale-to-0 lever during explore (Pitfall 4) |
| `configmap.yaml` | non-secret `environment:` keys (URLs/hosts, e.g. lines 48-49, 66-67, 75-76, 86, 92) | ConfigMap + `envFrom`/`env` | in-cluster hostnames (`postgres`/`redis`/`neo4j`/`rabbitmq`/`elasticsearch`) already match compose service names (Pitfall 6) |
| `secret.example.yaml` | the `${JWT_SECRET}`/`${TARGET_CREDENTIAL_KEY}`/`${NEO4J_AUTH}`/provider-key env (lines 50-51, 67-68, 311) | Secret + `secretKeyRef` | SAME env var NAMES the app already reads (config.py); placeholder/example values, real gitignored (Security V14) |

**Probe-translation excerpts** (RESEARCH lines 341-353): api `httpGet /health:8000`; postgres
`exec pg_isready -U $(POSTGRES_USER) -d $(POSTGRES_DB)`. `depends_on: condition: service_healthy`
(compose lines 107-111) → readiness probes + the already-built app-level lazy/graceful boot (api boots
without neo4j/es). Stateful (Postgres, Neo4j) → StatefulSet+PVC; everything else → Deployment.

---

### `infra/k8s/overlays/elasticsearch/*` (NET-NEW overlay — SOURCE compose `elasticsearch`)

**Analog:** compose `elasticsearch` block (lines 384-398). Kustomize overlay layout is NET-NEW (no
in-repo Kustomize precedent), but the ES Deployment content translates the compose block:
`1536m`→`1536Mi`, `ES_JAVA_OPTS`, `discovery.type:single-node`, the `xpack.security.*:false` env
(lines 392-396). This overlay is OFF for the SC1 e2e (3GB cap, D-01) — the conceptual analog is the
compose `search` profile keeping ES off by default (line 386).

---

### `infra/docker-compose.yml` (MODIFY — add a `monitoring` profile)

**Analog:** the existing `profiles: [graph]` / `[queue]` / `[search]` blocks (lines 307, 333, 386) —
copy that `profiles: [<name>]` "OFF by default" mechanism for a new `profiles: [monitoring]` group
holding prometheus, grafana, postgres-exporter, redis-exporter, elasticsearch-exporter. The
`mem_limit` + `healthcheck` + `ports` + `environment` shape per service mirrors every existing block.
RabbitMQ needs NO exporter (built-in plugin on :15692, the existing rabbitmq image, line 332).

---

### Monitoring config (NET-NEW — no code analog; CLI/image conventions)

- `infra/monitoring/prometheus.yml` — scrape_configs for `api:8000/metrics` + the exporters +
  `rabbitmq:15692` (RESEARCH lines 444-460). In-cluster hostnames = compose service names (Pitfall 6).
- `infra/monitoring/grafana/provisioning/datasources/prometheus.yml` + `dashboards/provider.yml` +
  `dashboards/{platform-health,domain-metrics}.json` (RESEARCH Pattern 5, lines 421-460). The 4 panels
  query the gauge names defined in `core/metrics.py`
  (`qa_platform_heal_success_rate`/`_classification_precision`/`_coverage_percent`/`_llm_cost_usd_total`);
  platform-health queries the instrumentator's `http_request_duration_*`/`http_requests_total` + `up{}`.
- `infra/k8s/monitoring/{prometheus,grafana,exporters}.yaml` — the SAME prometheus.yml/provisioning
  mounted via ConfigMap instead of a compose bind. No in-repo analog (standard Prom/Grafana K8s shape).

---

### Tests (NET-NEW — analogs are the existing unit/integration test dirs)

- `apps/api/tests/unit/test_metrics_collector.py` — assert `_snapshot`→gauge mapping and the DEGRADE
  case (`_snapshot[key]=None` → that `GaugeMetricFamily` is NOT yielded, no raise). Analog: existing
  `apps/api/tests/unit` tests (pytest, `asyncio_mode=auto`).
- `apps/api/tests/integration/test_metrics_endpoint.py` — seed `heal_audit`/`classifications`/
  `defects`/`llm_usage` rows, GET `/metrics`, assert the 4 gauge names + values present. Analog:
  existing `apps/api/tests/integration` (the `integration` marker, real Postgres).
- `apps/api/tests/unit/test_dashboards_json.py` — `json.load` each dashboard JSON; assert the 4 gauge
  names appear. Pure-keyless unit test.

## Shared Patterns

### Graceful degrade → metric scrape tolerance (the most important carried pattern)
**Source:** `apps/api/app/main.py:109-137` (the `ServiceUnavailable`/`ESConnectionError` 503 handlers)
+ `apps/api/app/core/es_client.py:11-20` (lazy-client-boots-when-down docstring contract).
**Apply to:** `core/metrics.py` `_refresh_once()` (per-source try/except → `None`, never raise) and
`collect()` (omit a `None` gauge). A down source → that gauge absent + `/metrics` still 200. A fake
`0` is FORBIDDEN (RESEARCH anti-patterns line 465; the T-10-20 "never a fake empty" contract).
```python
# the exact log shape to mirror (main.py:117)
log.warning("metric_refresh_failed", metric="coverage_percent", error=str(exc))
```

### Lifespan-managed module-global (init/close + create_task)
**Source:** `apps/api/app/core/{es_client,neo4j_driver,redis_client}.py` (the `_x=None` global +
`init_*`/`close_*`/`get_*` triad) + `apps/api/app/main.py:80-104` (lifespan calls them).
**Apply to:** `core/metrics.py` `_snapshot`/`_refresh_task` + `start_metrics`/`stop_metrics`, wired
into the existing lifespan (start after `init_es`, stop alongside `close_*`).

### Read-service SQLAlchemy aggregation (NEVER recompute the metric)
**Source:** `apps/api/app/services/dashboards.py:38-73` + `healing/stats.py:34` +
`coverage_dash.py:54` — module-level `async def fn(db: AsyncSession)` returning plain dicts/floats,
SQLAlchemy 2.0 `select`/`func.count`/`func.sum`, no raw SQL, no LLM, no broker.
**Apply to:** the collector's refresh loop reuses these functions as-is; the two NET-NEW small queries
(precision over `Defect.status`, sum over `LLMUsage.cost_usd`) copy the `func.count(...).where(status...)`
(dashboards.py:50-52) + `int(... or 0)`/`float(...)` null-guard idiom.

### Optional secret in Settings
**Source:** `apps/api/app/core/config.py:139` (`ci_token: str | None = None  # env CI_TOKEN`; same as
`anthropic_api_key`, `jira_api_token`).
**Apply to:** any optional metrics scrape token (deferred, A4) — copy the line verbatim. K8s Secrets
reuse the SAME env var names the app already reads — no code rename.

### Scoped, never-echoed CI token + least-privilege permissions
**Source:** `.github/workflows/run-suite.yml:17-21,36-38` (the header discipline + `env:` scoping).
**Apply to:** `platform-ci.yml` — `permissions: { contents: read, packages: write }`, the built-in
`GITHUB_TOKEN`, never print the token/Authorization header (Security V14, T-07-07 precedent).

### Multi-stage Docker build (build stage → slim runtime)
**Source:** `infra/targets/saucedemo/Dockerfile:22-31` (`FROM ... AS build` → `COPY --from=build`).
**Apply to:** `apps/web/Dockerfile` production target (`next build` → `next start` runtime stage).
The api Dockerfile already layer-caches via uv; its only prod change is dropping `--reload`.

### Compose `profiles:` OFF-by-default → K8s overlay / separate manifest group
**Source:** `infra/docker-compose.yml` `profiles: [graph/queue/search]` (lines 307, 333, 386).
**Apply to:** the new compose `profiles: [monitoring]` block; the ES Kustomize overlay; the separate
`infra/k8s/monitoring/` manifest group (the K8s analog of an OFF-by-default profile — 3GB cap, D-01/D-04).

## No Analog Found

True NET-NEW config with no in-repo code/compose analog (planner uses RESEARCH.md patterns + CLI docs):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `infra/k8s/base/kustomization.yaml` + `namespace.yaml` | config (K8s) | — | No prior Kustomize/K8s manifests in the repo (Kustomize layout is a CLI convention) |
| `infra/k8s/monitoring/{prometheus,grafana,exporters}.yaml` | config (K8s) | — | First Prometheus/Grafana/exporter manifests; standard image shapes |
| `infra/monitoring/prometheus.yml` | config (scrape) | — | First Prometheus config; promtool-validated, not code |
| `infra/monitoring/grafana/provisioning/{datasources,dashboards}/*` | config (dashboards-as-code) | — | First Grafana provisioning + dashboard JSON; Grafana v5+ convention |

> Note: the K8s WORKLOAD manifests (postgres/redis/rabbitmq/neo4j/api/worker/web/es) DO have a strong
> analog — the compose service blocks — even though K8s YAML itself is new to the repo. Only the
> Kustomize wiring + the monitoring stack are truly analog-free.

## Metadata

**Analog search scope:** `infra/` (docker-compose, targets, monitoring), `apps/api/app/` (main,
core/{es_client,neo4j_driver,redis_client,config}, services/{dashboards,healing/stats,coverage_dash,
defects}, models/{llm_usage,defects}, routers/health), `apps/api/{Dockerfile,pyproject.toml}`,
`apps/web/Dockerfile`, `.github/workflows/`.
**Files scanned:** 14 read in full/targeted + 2 glob/grep sweeps over `services/` and `defects/`.
**prometheus deps confirmed absent from `apps/api/pyproject.toml`:** YES (list ends `elasticsearch[async]==9.4.*`).
**Pattern extraction date:** 2026-06-29
