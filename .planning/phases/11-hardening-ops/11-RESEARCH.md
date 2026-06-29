# Phase 11: Hardening & Ops - Research

**Researched:** 2026-06-29
**Domain:** Kubernetes manifests (Kustomize) · GitHub Actions CI/CD (GHCR) · Prometheus custom collector + instrumentator · Grafana dashboards-as-code
**Confidence:** HIGH (the four sub-domains have authoritative docs + a strong in-repo precedent for every pattern; the genuine unknowns — the sync-collect-over-async bridge and the "classification precision" data source — are resolved below with one flagged Open Question)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01 (K8s, INFRA-02):** Plain Kubernetes YAML under `infra/k8s/` as a **Kustomize base** (no Helm). CORE services always-on: Postgres / Redis / RabbitMQ / api / worker / web / **Neo4j** (Neo4j is required for explore→coverage→traceability, so it is core). Resource requests + limits matching the compose `mem_limit`s. **Elasticsearch is an OPTIONAL Kustomize overlay** (search graceful-degrades) so the SC1 e2e (explore → execute → dashboard) fits under the 3GB cap. Document realistic per-service sizing + the "ES overlay off for the e2e" note.
- **D-02 (CI/CD, INFRA-03):** Publish to **GHCR** via the built-in `GITHUB_TOKEN` (no extra registry secret). On push to master: a `test` job runs the **keyless deterministic pytest lane** (`uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional and not search"`) + frontend `tsc --noEmit` + eslint; then a `build-publish` job builds & pushes `api` and `web` to `ghcr.io/honraoclaude/...`, tagged by commit **SHA + `latest`**. SauceDemo is a **test fixture** image (NOT published).
- **D-03 (Domain metrics, INFRA-04):** **PULL-ON-SCRAPE.** A prometheus-client **custom Collector** that on each `/metrics` scrape queries the EXISTING services — healing/stats (heal success rate), defects classification accuracy (classification precision), coverage_dash (coverage %), llm_usage (LLM cost) — and emits gauges. PLUS `prometheus-fastapi-instrumentator` for HTTP metrics. **APP-LEVEL only** — NO Enterprise Neo4j endpoint. `prometheus-client` 0.25 + `prometheus-fastapi-instrumentator` 8.0 are gated new deps. Scrapes must be **cheap + failure-tolerant** (a metric source down → that gauge absent/NaN, never a 500 on /metrics — mirror the neo4j/ES degrade).
- **D-04 (Monitoring stack, INFRA-04):** Prometheus + Grafana run BOTH as a compose `monitoring` profile (OFF by default — 3GB cap) AND as K8s manifests. The Grafana **datasource + dashboards** (platform health + 4 domain metrics) are provisioned **AS CODE** — committed `grafana/provisioning/datasources/*.yml` + `dashboards/*.json` + a `prometheus.yml` scrape config. Reproducible on a fresh deploy, no manual clicking.

### Claude's Discretion (research → recommend)
- The full K8s manifest set, the Kustomize base/overlay layout, resource sizing under 3GB, the e2e validation procedure on kind/Docker Desktop K8s.
- The custom-collector implementation (sync `collect()` bridging the async read-services), gauge naming, and the standard per-component exporters (postgres/redis/rabbitmq/ES) from the CLAUDE.md exporter table.
- The GHCR build/publish workflow (buildx, GITHUB_TOKEN login, SHA+latest tags, test-gate) + image-build reproducibility.
- The Grafana provisioning (datasource + dashboards-as-code JSON) for compose + K8s; the prometheus.yml scrape targets.
- How to TEST this phase deterministically/keylessly vs Manual-Only.

### Deferred Ideas (OUT OF SCOPE)
- Production cloud K8s (EKS/GKE/AKS) + managed registries + real secrets management + ingress/TLS — single-operator local validation only.
- The Enterprise-only Neo4j native Prometheus endpoint — rejected (app-level graph metrics per CLAUDE.md).
- Autoscaling / HPA / multi-replica production tuning.
- Alerting rules / Alertmanager / on-call — dashboards only this phase.
- Write-time metric gauges — rejected (pull-on-scrape avoids hot-path coupling).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-02 | Kubernetes manifests deploy the platform, validated on Docker Desktop K8s or kind | "Architecture Patterns → K8s Kustomize Base" (manifest set, compose→K8s translation table, probe mapping, sizing); "Validation Architecture" (kustomize build + kubeconform keyless; live kind deploy + e2e Manual-Only) |
| INFRA-03 | GitHub Actions CI/CD builds, tests, and publishes platform images | "Architecture Patterns → CI/CD Workflow" (test-gate job + build-publish job, GHCR login, metadata-action SHA+latest, buildx gha cache); "Common Pitfalls" (web prod build, CI needs-no-services confirmation) |
| INFRA-04 | Grafana + Prometheus expose platform health and domain metrics (healing success rate, classification precision, coverage, LLM cost) | "Architecture Patterns → Prometheus Custom Collector" (sync-over-async bridge, gauge names/labels, /metrics mount, exporter table); "Grafana Dashboards-as-Code"; "Open Questions Q1" (classification-precision data source) |
</phase_requirements>

## Summary

Phase 11 adds **no product capability** — it deploys, builds, and observes the platform that Phases 1–10 already shipped. Every pattern it needs already exists in the repo as a precedent: compose service definitions with `mem_limit`s translate to K8s requests/limits; compose healthchecks translate to readiness/liveness probes; the four domain metrics already exist as **queryable data** (heal_audit, classifications, coverage join, llm_usage) computed by pure async service functions; and the graceful-degrade contract (lazy clients, 503-not-500 when a backing service is down) is the exact template for a failure-tolerant `/metrics`.

The three deliverables are independent and parallelizable: **(INFRA-02)** a Kustomize base under `infra/k8s/` (Deployment/StatefulSet/Service/ConfigMap/Secret/PVC per core service + an ES overlay + monitoring manifests), validated keylessly with `kustomize build | kubeconform` and live-validated by a Manual-Only kind/Docker-Desktop-K8s e2e; **(INFRA-03)** a GitHub Actions workflow that gates a GHCR build-publish job behind the keyless pytest lane + `tsc`/eslint; **(INFRA-04)** a `/metrics` endpoint backed by a prometheus-client custom Collector + the FastAPI instrumentator, plus a `monitoring` compose profile / K8s manifests with Prometheus + Grafana provisioned as code.

**The one genuine technical risk** is the custom collector: `collect()` is **synchronous and cannot be async**, but the four metric sources are async functions over async DB/Neo4j clients, and the FastAPI event loop is already running in the main thread. The recommended resolution (HIGH confidence, lowest-risk) is a **background-refreshed cached snapshot**: a lifespan-started async task periodically computes the four metrics into plain floats; `collect()` reads those cached floats synchronously and O(1). This makes scrapes cheap and trivially failure-tolerant (a stale/missing value → omit that gauge, never raise), and it sidesteps the `asyncio.run`-inside-a-running-loop deadlock entirely.

**Primary recommendation:** Build three Kustomize-base + workflow + collector slices in parallel; for INFRA-04 use the **background-refreshed snapshot** collector pattern (NOT `asyncio.run` in `collect()`); pin `prometheus-client==0.25.*` and `prometheus-fastapi-instrumentator==8.0.*`; obtain kustomize/kubeconform/actionlint/promtool as CLI tools in CI (not pip deps); and resolve the "classification precision" data-source ambiguity (Open Question Q1) before locking the gauge semantics.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Cluster deployment (manifests) | Infra / K8s (`infra/k8s/`) | — | Kustomize base translates compose; no app code change |
| Image build + publish | CI/CD (GitHub Actions) | API / Web Dockerfiles | Workflow orchestrates; Dockerfiles produce the artifacts |
| Domain-metric computation | API / Backend (existing async services) | — | Metrics are READS of shipped logic — never recomputed in Phase 11 |
| Metric exposition (`/metrics`) | API / Backend (collector + instrumentator) | — | App-level only (CLAUDE.md); FastAPI owns the endpoint |
| Infra metrics (pg/redis/rmq/es) | Infra (sidecar/standalone exporters) | — | Standard exporters scrape the datastores directly |
| Metric scrape + storage | Monitoring (Prometheus) | — | Pull model; scrape config as code |
| Dashboards / visualization | Monitoring (Grafana) | — | External to the Next.js app (no UI-SPEC); provisioned as code |

## Project Constraints (from CLAUDE.md)

These have the same authority as locked decisions — research must not contradict them.

- **New backend deps are exactly two:** `prometheus-client 0.25.x` (custom domain metrics) + `prometheus-fastapi-instrumentator 8.0.x` (HTTP `/metrics`). Both are in CLAUDE.md's locked stack. **Flag ANY other new package.**
- **Exporter table (verbatim):** `prometheuscommunity/postgres-exporter`, `oliver006/redis_exporter`, RabbitMQ **built-in `rabbitmq_prometheus` plugin** (already in `rabbitmq:4-management`, scrape **port 15692** — no external exporter), `prometheuscommunity/elasticsearch-exporter`. **Neo4j native Prometheus is Enterprise-only → emit app-level graph metrics instead** (handled by the custom collector, not a Neo4j exporter).
- **Grafana + Prometheus** are the observability stack; **Docker/Kubernetes + Docker Desktop K8s/kind** the deploy targets; **GitHub Actions** the CI; **Docker Compose profiles** (`infra`/`app`/`monitoring`) the local orchestration model.
- **3GB Windows/Docker-Desktop cap is the dominant sizing constraint.** The full stack cannot all run at once.
- **Runtime baselines:** Python **3.13.x**, Node **22 LTS**. CI must `setup-python`/`uv` and `setup-node` to these.
- **`uv` for Python**, `ruff` lint/format, `mypy`/pyright type-check, **`uv run python -m pytest`** test invocation (Windows AppControl blocks the `pytest.exe` shim locally; Linux CI is unaffected but keep `python -m pytest` for portability).
- **Async-driver stack:** asyncpg via SQLAlchemy 2.0 async, `redis.asyncio`, `neo4j.AsyncGraphDatabase`, `AsyncElasticsearch`. The collector must bridge sync↔async (see Architecture Patterns).
- **What NOT to use:** no Helm (D-01 chose Kustomize); no Enterprise Neo4j endpoint; no storing artifacts in Postgres/ES.

## Standard Stack

### Core (new this phase)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| prometheus-client | 0.25.* `[VERIFIED: PyPI 0.25.0, published 2026-04-09]` `[CITED: CLAUDE.md]` | Custom Collector for the 4 domain gauges; `/metrics` text format | The official Python Prometheus client; the only correct way to expose a custom Collector |
| prometheus-fastapi-instrumentator | 8.0.* `[VERIFIED: PyPI 8.0.2]` `[CITED: CLAUDE.md]` | HTTP request latency/status histograms + `/metrics` mount on FastAPI | The standard FastAPI instrumentation; one-line lifespan wiring; can expose the same default REGISTRY the custom Collector registers to |

### Supporting (existing — reused, NOT new deps)
| Library / image | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| SQLAlchemy async / asyncpg | existing | The collector's snapshot task reads heal_audit / classifications / coverage join / llm_usage | Every refresh tick |
| neo4j AsyncGraphDatabase | existing | coverage_dash mines flows from Neo4j (core service) | The coverage metric |
| FastAPI lifespan | existing | Start/stop the background snapshot-refresh task (the `init_redis`/`init_es` precedent) | App startup/shutdown |

### Infra exporter images (NOT Python deps — container images)
| Image | Purpose | Wiring |
|-------|---------|--------|
| `quay.io/prometheuscommunity/postgres-exporter` `[CITED: hub.docker.com/r/prometheuscommunity/postgres-exporter]` | Postgres metrics | `DATA_SOURCE_URI`/`DATA_SOURCE_USER`/`DATA_SOURCE_PASS` env; scrape :9187 |
| `oliver006/redis_exporter` `[CITED: CLAUDE.md exporter table]` | Redis metrics | `REDIS_ADDR=redis://redis:6379`; scrape :9121 |
| `quay.io/prometheuscommunity/elasticsearch-exporter` `[CITED: prometheus.io/docs/instrumenting/exporters]` | ES metrics (ONLY when the ES overlay is up) | `--es.uri=http://elasticsearch:9200`; scrape :9114 |
| RabbitMQ `rabbitmq_prometheus` plugin | RabbitMQ metrics | **Built into `rabbitmq:4-management`** — no extra container; scrape `rabbitmq:15692/metrics` `[CITED: rabbitmq.com/docs/prometheus]` |
| `prom/prometheus` | Scrape + store | `prometheus.yml` mounted (compose) / ConfigMap (K8s) |
| `grafana/grafana` | Dashboards | provisioning dir mounted (compose) / ConfigMap (K8s) |

### CLI tools (CI/dev only — NOT pip/npm deps)
| Tool | Purpose | How obtained (NOT a package install) |
|------|---------|--------------------------------------|
| `kustomize` | `kustomize build infra/k8s/...` renders manifests | Shipped inside `kubectl` (`kubectl kustomize`) OR the standalone binary; in CI use `azure/setup-kubectl` or download the release binary |
| `kubeconform` | Offline schema-validate rendered manifests (no cluster) `[CITED: github.com/yannh/kubeconform]` | Download the Go release binary in the workflow, or `yannh/kubeconform` action |
| `actionlint` | Lint the workflow YAML | Download release binary / `rhysd/actionlint` action |
| `promtool` | `promtool check config prometheus.yml` | Ships in the `prom/prometheus` image (`docker run --rm -v ... prom/prometheus promtool check config ...`) |
| `kind` | Local cluster for the Manual-Only e2e | Optional; Docker Desktop K8s is the alternative |

**Installation (the only pip change):**
```bash
# apps/api/pyproject.toml — add to [project].dependencies
prometheus-client==0.25.*
prometheus-fastapi-instrumentator==8.0.*
# then:  uv lock && uv sync
```
No new npm/frontend deps (Grafana is external; no UI-SPEC).

## Package Legitimacy Audit

slopcheck 0.6.1 ran successfully (`slopcheck install <pkgs>`); both packages `[OK]`.

| Package | Registry | Age | Releases | Source Repo | slopcheck | Disposition |
|---------|----------|-----|----------|-------------|-----------|-------------|
| prometheus-client | PyPI (0.25.0) | mature | 59 | github.com/prometheus/client_python | [OK] (note: "ends with -client, LLM-bait pattern, but established") | Approved — pin `0.25.*` |
| prometheus-fastapi-instrumentator | PyPI (latest 8.0.2) | mature | 41 | github.com/trallnag/prometheus-fastapi-instrumentator | [OK] | Approved — **pin `8.0.*`** (CLAUDE.md). NB a globally-installed 7.1.0 exists on this machine; the project must pin 8.0.* in pyproject |

**Packages removed due to [SLOP]:** none.
**Packages flagged [SUS]:** none.
**No `postinstall`/build-script risk** (Python wheels, established maintainers, real source repos). Both verified on the correct ecosystem registry (PyPI).

## Architecture Patterns

### System Architecture Diagram

```
                        ┌──────────────────────── PUSH to master ────────────────────────┐
                        │                                                                 │
                 GitHub Actions (INFRA-03)                                                 │
                 ┌──────────────┐ gate ┌────────────────────────┐ push   ┌─────────────┐  │
   git push ───► │ test job     │─────►│ build-publish job      │───────► │   GHCR      │  │
                 │ uv+pytest    │ pass │ buildx + login + meta  │ SHA+    │ api / web   │  │
                 │ tsc + eslint │      │ build api & web        │ latest  │ images      │  │
                 │ (keyless)    │      └────────────────────────┘         └──────┬──────┘  │
                 └──────────────┘                                                │ image refs
                                                                                 ▼
   ┌────────────────────────── Kubernetes (kind / Docker Desktop K8s) — INFRA-02 ──────────────┐
   │  Kustomize base (infra/k8s/base)            optional overlay: elasticsearch                │
   │  ┌─────────┐ ┌───────┐ ┌──────────┐ ┌───────┐ ┌─────┐ ┌──────┐ ┌─────┐                     │
   │  │postgres │ │ redis │ │ rabbitmq │ │ neo4j │ │ api │ │worker│ │ web │   (+ es overlay)    │
   │  │ +PVC SS │ │ Deploy│ │ Deploy   │ │+PVC SS│ │Deploy│ │Deploy│ │Deploy│                    │
   │  └────┬────┘ └───┬───┘ └────┬─────┘ └───┬───┘ └──┬──┘ └──┬───┘ └─────┘                     │
   │       │ readiness/liveness probes (from compose healthchecks)  │ /metrics                  │
   │       └──────────────── Services (ClusterIP) ──────────────────┘     │                     │
   └──────────────────────────────────────────────────────────────────────┼─────────────────────┘
                                                                            │ scrape
   ┌──────────────────── monitoring (compose profile / K8s manifests) — INFRA-04 ──────────────┐
   │  exporters: pg :9187  redis :9121  rabbitmq :15692(built-in)  es :9114(overlay only)       │
   │       │            │            │                       │                                  │
   │       └────────────┴────────────┴───────────────────────┴──────► Prometheus ──► Grafana   │
   │                                       api /metrics (4 domain gauges + HTTP)  (provisioned  │
   │                                                                              datasource +  │
   │                                                                              dashboards)   │
   └────────────────────────────────────────────────────────────────────────────────────────┘

   Domain-metric data flow (pull-on-scrape, D-03):
   [background async task every N s] reads ─► heal_audit (heal_success_rate)
                                              classifications (classification_* — see Open-Q1)
                                              coverage_dash join (coverage_percent)
                                              llm_usage (llm_cost_usd_total)
                              writes plain floats ─► in-memory snapshot
   Prometheus scrape ─► GET /metrics ─► custom Collector.collect() reads snapshot (sync, O(1)) ─► gauges
```

### Recommended Project Structure
```
infra/
├── docker-compose.yml              # add a `monitoring` profile (prometheus, grafana, exporters)
├── k8s/                            # NEW — Kustomize (D-01)
│   ├── base/
│   │   ├── kustomization.yaml      # resources: [postgres, redis, rabbitmq, neo4j, api, worker, web, ...]
│   │   ├── namespace.yaml
│   │   ├── postgres.yaml           # StatefulSet + PVC + Service + (Secret ref)
│   │   ├── redis.yaml              # Deployment + Service
│   │   ├── rabbitmq.yaml           # Deployment + Service (15692 exposed)
│   │   ├── neo4j.yaml              # StatefulSet + PVC + Service (core, D-01)
│   │   ├── api.yaml                # Deployment + Service (image: ghcr.io/.../api) + probes + /metrics
│   │   ├── worker.yaml             # Deployment (same image, worker_main command)
│   │   ├── web.yaml                # Deployment + Service (image: ghcr.io/.../web)
│   │   ├── configmap.yaml          # non-secret env (URLs, hosts)
│   │   └── secret.example.yaml     # JWT_SECRET / TARGET_CREDENTIAL_KEY / NEO4J_AUTH (example, gitignore real)
│   ├── overlays/
│   │   └── elasticsearch/          # OPTIONAL ES overlay (D-01) — search degrades when absent
│   │       ├── kustomization.yaml  # bases: [../../base] + es resources
│   │       └── elasticsearch.yaml
│   └── monitoring/                 # Prometheus + Grafana + exporters as manifests (D-04)
│       ├── kustomization.yaml
│       ├── prometheus.yaml         # Deployment + Service + ConfigMap(prometheus.yml)
│       ├── grafana.yaml            # Deployment + Service + ConfigMap(provisioning + dashboards)
│       └── exporters.yaml          # pg / redis exporter Deployments + Services
├── monitoring/                     # NEW — shared as-code config (mounted by compose AND K8s ConfigMaps)
│   ├── prometheus.yml              # scrape_configs: api /metrics + exporters
│   └── grafana/
│       └── provisioning/
│           ├── datasources/prometheus.yml
│           └── dashboards/
│               ├── provider.yml    # tells Grafana to load *.json from this dir
│               ├── platform-health.json
│               └── domain-metrics.json   # the 4 domain panels
apps/api/app/
├── core/
│   └── metrics.py                  # NEW — the custom Collector + the snapshot refresher
├── routers/
│   └── metrics.py                  # NEW — (or mount via instrumentator.expose(app))
.github/workflows/
└── platform-ci.yml                 # NEW — separate from run-suite.yml (D-02)
```

### Pattern 1: Prometheus custom Collector with a background-refreshed snapshot (sync-over-async bridge) — THE CRUX
**What:** `collect()` is synchronous and **cannot be async** — the prometheus-client REGISTRY iterates it synchronously, and making it truly async requires rewriting the registry + `generate_latest` (see Sources, GH #587 — an anti-pattern here). Meanwhile the four metric sources are async over async DB/Neo4j, and the FastAPI event loop already runs in the main thread, so calling `asyncio.run(...)` inside `collect()` raises `RuntimeError: asyncio.run() cannot be called from a running event loop`, and `run_coroutine_threadsafe` adds latency + failure surface to every scrape.
**Recommended (HIGH confidence):** decouple computation from exposition with a **background-refreshed cached snapshot**:
1. In the FastAPI lifespan (the `init_redis`/`init_es` precedent), start an `asyncio.create_task(_refresh_loop())`.
2. `_refresh_loop()` sleeps N seconds (e.g. 15–30s, well under any scrape interval), then computes the four metrics by reusing the existing async service functions over a fresh `SessionLocal()` + `get_neo4j()`, writing plain floats into a module-level `_snapshot` dict. **Each source is wrapped independently in try/except** — a failure sets that key to `None` (NOT zero) and logs, exactly mirroring the graceful-degrade contract.
3. The custom `Collector.collect()` reads `_snapshot` synchronously and O(1): for each metric, if the value is `None` it **omits that gauge entirely** (Prometheus treats absent as "no data"/NaN — the honest signal), else `yield GaugeMetricFamily(name, help, value=...)`.
**Why this and not the alternatives:** scrapes become cheap and cannot fail (no DB I/O on the scrape path); failure-tolerance is structural (a down Neo4j → coverage gauge simply absent, `/metrics` still 200); it reuses shipped logic without duplicating it; and it never touches the running event loop from a sync context.
**Example:**
```python
# apps/api/app/core/metrics.py
# Source: https://prometheus.github.io/client_python/collector/custom/ (custom Collector pattern)
import asyncio
import structlog
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector, REGISTRY

from app.db.session import SessionLocal
from app.core.neo4j_driver import get_neo4j
from app.services.healing.stats import per_element_heal_stats
from app.services import coverage_dash
# ... classification + llm_usage source imports (see Open-Q1 for the precision source)

log = structlog.get_logger()

_snapshot: dict[str, float | None] = {
    "heal_success_rate": None,
    "classification_precision": None,   # SEE Open Question Q1 — semantics to confirm
    "coverage_percent": None,
    "llm_cost_usd_total": None,
}
_refresh_task: asyncio.Task | None = None
_REFRESH_SECONDS = 30


async def _refresh_once() -> None:
    # Each source independently guarded — one failure never blanks the others (graceful degrade).
    async with SessionLocal() as db:
        try:
            rows = await per_element_heal_stats(db)
            # aggregate per-element rates into a platform rate (sum healed / sum attempts)
            attempts = sum(r["attempts"] for r in rows)
            healed = sum(r["heal_success_rate"] * r["attempts"] for r in rows)
            _snapshot["heal_success_rate"] = (healed / attempts) if attempts else None
        except Exception as exc:                       # noqa: BLE001 — never propagate to /metrics
            log.warning("metric_refresh_failed", metric="heal_success_rate", error=str(exc))
            _snapshot["heal_success_rate"] = None
        try:
            cov = await coverage_dash.coverage(db, driver=get_neo4j())
            _snapshot["coverage_percent"] = float(cov["coverage_percent"])
        except Exception as exc:                       # noqa: BLE001
            log.warning("metric_refresh_failed", metric="coverage_percent", error=str(exc))
            _snapshot["coverage_percent"] = None
        # ... classification_precision + llm_cost_usd_total similarly guarded ...


async def _refresh_loop() -> None:
    while True:
        await _refresh_once()
        await asyncio.sleep(_REFRESH_SECONDS)


class DomainMetricsCollector(Collector):
    def collect(self):                                  # SYNC — reads the cached snapshot, O(1)
        defs = {
            "qa_platform_heal_success_rate": "Self-healing success rate (0..1)",
            "qa_platform_classification_precision": "Defect classification precision (0..1)",
            "qa_platform_coverage_percent": "Lifecycle coverage percent (0..100)",
            "qa_platform_llm_cost_usd_total": "Total LLM spend in USD",
        }
        for gauge, key in zip(defs, _snapshot):
            value = _snapshot[key]
            if value is None:                           # honest absence — never a fake 0
                continue
            yield GaugeMetricFamily(gauge, defs[gauge], value=value)


def start_metrics(app) -> None:
    """Call from lifespan startup: register the collector + start the refresher."""
    global _refresh_task
    REGISTRY.register(DomainMetricsCollector())
    _refresh_task = asyncio.create_task(_refresh_loop())


async def stop_metrics() -> None:
    if _refresh_task is not None:
        _refresh_task.cancel()
```

### Pattern 2: Mount /metrics + HTTP instrumentation on FastAPI
**What:** add HTTP request metrics and expose the `/metrics` endpoint over the same default REGISTRY the custom Collector registers to.
**Example:**
```python
# in apps/api/app/main.py
# Source: https://github.com/trallnag/prometheus-fastapi-instrumentator
from prometheus_fastapi_instrumentator import Instrumentator
from app.core.metrics import start_metrics, stop_metrics

# inside lifespan startup (after init_* calls):
start_metrics(app)                                  # register collector + start refresher
# instrument + expose /metrics (default REGISTRY includes the custom Collector)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
# inside lifespan shutdown:
await stop_metrics()
```
**/metrics auth:** keep `/metrics` **unauthenticated but safe** for local single-operator validation — it emits only aggregate numeric gauges + HTTP histograms (no secrets, no PII, no prompts). This matches the existing unauthenticated `/health`. If a scrape-token gate is later wanted, add a header check in a thin router wrapping `instrumentator.expose` — but defer (Deferred: production secrets/ingress). Document the choice explicitly in the plan.

### Pattern 3: Compose→K8s translation (the manifest set)
**What:** each compose service becomes a K8s workload. The mapping is mechanical.

| Compose construct | K8s equivalent |
|-------------------|----------------|
| `image:` / `build:` | `image: ghcr.io/honraoclaude/<api|web>:<tag>` (built images); exporters use upstream images |
| `mem_limit: 512m` | `resources.limits.memory: 512Mi` + a `requests.memory` (~50–70% of limit) |
| `healthcheck:` (CMD) | `readinessProbe` + `livenessProbe` (exec or httpGet) translating the same command |
| `environment:` (non-secret) | `ConfigMap` + `envFrom`/`env` |
| `environment:` (JWT_SECRET, TARGET_CREDENTIAL_KEY, NEO4J_AUTH, provider keys) | `Secret` + `secretKeyRef` |
| named volume `pgdata:` | `PersistentVolumeClaim` + `StatefulSet.volumeClaimTemplates` |
| `depends_on: condition: service_healthy` | readiness probes + app-level lazy/retry (already built — api boots without neo4j/es) |
| `ports:` (host:container) | `Service` (ClusterIP) + a documented `kubectl port-forward` for the e2e |
| compose profile `graph`/`queue`/`search` | Neo4j+RabbitMQ are CORE in K8s (D-01); ES is an **overlay** |

**Stateful vs stateless:** Postgres + Neo4j → **StatefulSet + PVC** (durable state). Redis, RabbitMQ, api, worker, web, exporters, Prometheus, Grafana → **Deployment** (Redis/RabbitMQ are ephemeral here; Prometheus/Grafana use an emptyDir or a small PVC for local validation). Probe translation examples:
```yaml
# api — translate the compose python urllib /health check
readinessProbe:
  httpGet: { path: /health, port: 8000 }
  initialDelaySeconds: 20
  periodSeconds: 10
livenessProbe:
  httpGet: { path: /health, port: 8000 }
  periodSeconds: 10
# postgres — translate pg_isready
readinessProbe:
  exec: { command: ["pg_isready", "-U", "$(POSTGRES_USER)", "-d", "$(POSTGRES_DB)"] }
```

### Pattern 4: CI/CD — test-gate then build-publish (two jobs)
**What:** a `test` job runs the keyless lane + frontend checks; a `build-publish` job `needs: test` and publishes to GHCR. **The keyless lane needs NO backing services** (it excludes `graph`/`search`/`functional`/`e2e`/`live_llm`); confirm whether the remaining `not`-marked tests touch Postgres — if any `integration`-marked test needs Postgres, add a `services: postgres` container; otherwise CI needs none.
**Example:**
```yaml
# .github/workflows/platform-ci.yml
# Source: docker/login-action, docker/metadata-action, docker/build-push-action docs
name: platform-ci
on:
  push:
    branches: [master]
permissions:
  contents: read
  packages: write            # REQUIRED for GHCR push (default token is read-only on packages)
jobs:
  test:
    runs-on: ubuntu-latest
    # services: { postgres: ... }   # ADD ONLY IF an integration-marked test needs Postgres (confirm)
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v6          # uv for the api
      - run: uv sync --frozen
        working-directory: apps/api
      - run: uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional and not search"
        working-directory: apps/api
      - uses: actions/setup-node@v5
        with: { node-version: '22' }
      - run: npm ci
        working-directory: apps/web
      - run: npx tsc --noEmit
        working-directory: apps/web
      - run: npx eslint .
        working-directory: apps/web
  build-publish:
    needs: test
    runs-on: ubuntu-latest
    permissions: { contents: read, packages: write }
    strategy:
      matrix:
        include:
          - { name: api, context: apps/api }
          - { name: web, context: apps/web }
    steps:
      - uses: actions/checkout@v5
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/honraoclaude/${{ matrix.name }}
          tags: |
            type=sha
            type=raw,value=latest
      - uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

### Pattern 5: Grafana dashboards-as-code (compose AND K8s)
**What:** Grafana v5+ reads `/etc/grafana/provisioning/{datasources,dashboards}` at boot. Commit a Prometheus datasource yml + a dashboards-provider yml + dashboard JSON; mount them (compose) or ConfigMap them (K8s). No manual clicking.
**Layout + datasource:**
```yaml
# infra/monitoring/grafana/provisioning/datasources/prometheus.yml
# Source: https://keepgrowing.in/tools/grafana-provisioning-how-to-configure-data-sources-and-dashboards/
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090     # in-cluster/compose service name
    isDefault: true
---
# infra/monitoring/grafana/provisioning/dashboards/provider.yml
apiVersion: 1
providers:
  - name: 'qa-platform'
    folder: ''
    type: file
    options: { path: /etc/grafana/provisioning/dashboards }
```
The dashboard JSON panels query the gauge names (`qa_platform_heal_success_rate`, `qa_platform_classification_precision`, `qa_platform_coverage_percent`, `qa_platform_llm_cost_usd_total`) plus a platform-health panel from the instrumentator's `http_request_duration_*` / `http_requests_total` series and `up{job=...}`.
**prometheus.yml scrape config:**
```yaml
# infra/monitoring/prometheus.yml
global: { scrape_interval: 30s }
scrape_configs:
  - job_name: api
    metrics_path: /metrics
    static_configs: [{ targets: ['api:8000'] }]
  - job_name: postgres
    static_configs: [{ targets: ['postgres-exporter:9187'] }]
  - job_name: redis
    static_configs: [{ targets: ['redis-exporter:9121'] }]
  - job_name: rabbitmq
    static_configs: [{ targets: ['rabbitmq:15692'] }]   # built-in plugin, no separate exporter
  - job_name: elasticsearch                              # ONLY meaningful when the ES overlay is up
    static_configs: [{ targets: ['elasticsearch-exporter:9114'] }]
```

### Anti-Patterns to Avoid
- **`asyncio.run()` inside `collect()`** — deadlocks under the running FastAPI loop (`RuntimeError`). Use the background snapshot (Pattern 1).
- **Recomputing the 4 metrics** — they already exist as service functions; the collector READS them, never reimplements them (the coverage_dash/heal-stats discipline).
- **A fake `0` for a down source** — emit *absence* (omit the gauge), never zero (zero is a meaningful value that would lie). Mirrors the 503-not-fake-empty contract (T-10-20).
- **`deploy.resources.limits` in compose** — the repo standard is service-level `mem_limit` (compose comment, Pitfall 3). In K8s use `resources.limits.memory`.
- **Helm** — D-01 chose raw-YAML Kustomize; do not introduce charts.
- **A Neo4j Prometheus exporter / Enterprise endpoint** — CLAUDE.md forbids it; graph metrics come from the app collector.
- **Publishing the saucedemo image** — it is a test fixture (D-02); build it where tests need it, never push to GHCR.
- **Running the whole stack at once under K8s** — ES overlay OFF + monitoring separate for the e2e (3GB cap).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Prometheus text exposition | A custom `/metrics` text serializer | `prometheus-client` + `GaugeMetricFamily` | Format edge cases (escaping, HELP/TYPE lines, NaN) are easy to get wrong |
| HTTP request metrics | Hand-rolled latency middleware | `prometheus-fastapi-instrumentator` | Standard histograms/labels, one-line mount |
| Postgres/Redis/ES metrics | Custom DB-stat scrapers | the official exporters (CLAUDE.md table) | Maintained, comprehensive, correct |
| RabbitMQ metrics | An external rabbitmq exporter | the **built-in** `rabbitmq_prometheus` plugin (:15692) | Already in `rabbitmq:4-management` — zero extra container/memory |
| Manifest templating | Bash `sed` over YAML / Helm | Kustomize base + overlays (D-01) | Native `kubectl kustomize`; overlays handle the ES on/off cleanly |
| Manifest validation | Apply-to-a-cluster to find errors | `kustomize build \| kubeconform` | Offline, fast, keyless, no cluster needed |
| Image build/push in CI | `docker build` + manual `docker push` + manual tags | `docker/{login,metadata,build-push}-action` | GITHUB_TOKEN login, SHA+latest tag generation, gha layer cache |
| Grafana setup | Clicking dashboards in the UI | provisioning yml + dashboard JSON (D-04) | Reproducible on fresh deploy; version-controlled |

**Key insight:** every piece of this phase is "wire well-known tools together correctly," not "invent." The only bespoke code is the ~60-line custom Collector + snapshot refresher, and even that is the documented prometheus-client pattern adapted to the repo's async/graceful-degrade conventions.

## Runtime State Inventory

> This is a deploy/build/observe phase, not a rename/refactor. No string-rename or data-migration risk. Included for completeness.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no schema change, no rename. The collector READS existing tables (heal_audit, classifications, defects, llm_usage). | None |
| Live service config | New committed-as-code config: `prometheus.yml`, Grafana provisioning, K8s manifests — all in git, none in a UI/DB. | None (the as-code requirement is satisfied by construction) |
| OS-registered state | None — no Task Scheduler / pm2 / systemd registration. CI runs on GitHub-hosted runners. | None |
| Secrets/env vars | K8s Secrets re-use the SAME env var NAMES the app already reads (`JWT_SECRET`, `TARGET_CREDENTIAL_KEY`, `NEO4J_AUTH`, provider keys) — code rename: none. New: GHCR uses the built-in `GITHUB_TOKEN` (no new secret). Optional later: a scrape token (deferred). | Create K8s Secret manifests (example, gitignored real values); no code change |
| Build artifacts | The `api`/`web` images CI publishes to GHCR are the new artifacts. `uv.lock` re-locks after adding the two prometheus deps; the api image must rebuild to include them. | `uv lock && uv sync`; CI rebuilds the image |

**Verified:** no runtime cached/registered state carries an old identity — nothing to migrate.

## Common Pitfalls

### Pitfall 1: `collect()` cannot be async / `asyncio.run` deadlocks
**What goes wrong:** writing `async def collect()` (silently never iterated correctly) or `asyncio.run(coro)` inside a sync `collect()` under the running FastAPI loop → `RuntimeError: asyncio.run() cannot be called from a running event loop`, or a hang.
**Why:** prometheus-client's REGISTRY is synchronous; the app's event loop owns the main thread.
**How to avoid:** the background-refreshed snapshot (Pattern 1) — `collect()` reads cached floats only.
**Warning signs:** `/metrics` hangs or 500s; tests of the collector deadlock.

### Pitfall 2: a down metric source 500s /metrics
**What goes wrong:** Neo4j is off (coverage source) and the scrape path raises → Prometheus marks the target down, losing ALL metrics including healthy ones.
**Why:** coupling computation to the scrape path.
**How to avoid:** independent per-source try/except in the refresher; `collect()` omits a `None` gauge. `/metrics` is always 200. This is the neo4j/ES 503-degrade contract applied to metrics.
**Warning signs:** `up{job=api}` flaps when an optional service is down.

### Pitfall 3: the web Dockerfile is DEV-only (`npm run dev`)
**What goes wrong:** publishing the current `apps/web/Dockerfile` ships a Turbopack **dev** server to GHCR/K8s — not a production build, memory-hungry (1536m), and the wrong artifact for a "deploy like a product" phase.
**Why:** the existing image was scoped to the Phase-1 "stack is up" promise, not production serving.
**How to avoid:** the plan must decide — either (a) add a **production multi-stage build** (`next build` → `next start`, lower memory) for the K8s/CI image, or (b) explicitly accept the dev image for local-only validation and document it. **Flag this for the planner** (the AGENTS.md note warns this Next.js differs from training data — read `node_modules/next/dist/docs/` before changing the build). The api Dockerfile similarly runs `--reload` (dev) — the K8s command should drop `--reload`/`--reload-dir`.
**Warning signs:** large web image, high memory in K8s, hot-reload watchers running in prod.

### Pitfall 4: 3GB cap — the K8s full stack won't fit at once
**What goes wrong:** deploying base + ES overlay + monitoring simultaneously on Docker Desktop K8s/kind under the 3GB cap → OOM/evictions.
**Why:** the cumulative `mem_limit`s exceed 3GB (Postgres 512 + Neo4j 1g + web 1536 + ... + ES 1536 + Prometheus + Grafana).
**How to avoid:** sequence the e2e — **ES overlay OFF** (search degrades, already built), **monitoring as a SEPARATE step** from the explore→execute→dashboard e2e. Document the sizing math (below). The live full-stack-at-once is Manual-Only and may need the web image trimmed (Pitfall 3) or `web` scaled to 0 during the explore phase (the `graph_mode` precedent that stops web before neo4j).
**Warning signs:** pods Pending/OOMKilled; node memory pressure.

**Sizing math (core set, ES off, monitoring separate) — fits ≈ same envelope as the validated compose graph_mode (~2.9GB):**
| Service | limit |
|---------|-------|
| postgres | 512Mi |
| redis | 256Mi |
| rabbitmq | 512Mi |
| neo4j | 1Gi (heap 512 + pagecache 256) |
| api | 1Gi |
| worker | 768Mi |
| web | 1536Mi (dev) — **trim or scale-to-0 during explore** to fit |
*The Phase-3 precedent: postgres+redis+api+neo4j+saucedemo ≈ 2.9GB fit by stopping web. The same lever applies in K8s — scale `web` to 0 during the explore phase of the e2e, scale to 1 for the dashboard step.*

### Pitfall 5: `classification precision` has no runtime ground-truth source (Open-Q1)
**What goes wrong:** assuming `classifications` rows carry a "correct?" label and computing precision from them — they don't. Precision is measured **offline** by the QUAL-03 harness against a hand-labeled set; the live table has only the predicted class + confidence (no ground truth).
**Why:** at runtime there is no oracle for whether a classification was right.
**How to avoid:** resolve Open Question Q1 before locking the gauge. Candidate runtime proxies: (a) the **human-feedback precision** from `defects.status` — applied vs rejected of human-reviewed defects (a real, queryable precision-of-acted-defects); (b) the **measured QUAL-03 accuracy** surfaced as a static/last-measured gauge; (c) a confidence-distribution gauge. **Recommend (a)** as the honest runtime metric, with the gauge named/documented to say exactly what it measures.
**Warning signs:** a precision gauge that always reads 1.0 or is computed from predictions alone.

### Pitfall 6: in-cluster hostnames + RabbitMQ AMQP vs metrics ports
**What goes wrong:** copying compose `localhost`/host-port URLs into K8s, or scraping RabbitMQ on 5672 (AMQP) instead of 15692 (metrics).
**Why:** K8s service DNS differs from host ports; the prometheus plugin serves on 15692, not the AMQP port.
**How to avoid:** use service names (`postgres`, `redis`, `neo4j`, `rabbitmq`, `api`) — the compose internal hostnames already match (`bolt://neo4j:7687`, `amqp://...@rabbitmq:5672`). Scrape RabbitMQ at `rabbitmq:15692/metrics`.
**Warning signs:** connection-refused in pods; empty RabbitMQ metrics.

### Pitfall 7: pinning `prometheus-fastapi-instrumentator` — global 7.1.0 vs project 8.0.x
**What goes wrong:** a machine-global 7.1.0 is installed; tests/imports might silently use it instead of the locked 8.0.x.
**How to avoid:** pin `prometheus-fastapi-instrumentator==8.0.*` in `apps/api/pyproject.toml` and run inside `uv` (the project venv), never global Python. `uv sync` resolves the pin.

## Code Examples

The verified patterns are inline above (Patterns 1–5). Sources:
- Custom Collector: `https://prometheus.github.io/client_python/collector/custom/`
- Instrumentator: `https://github.com/trallnag/prometheus-fastapi-instrumentator`
- GHCR build/publish: `docker/login-action`, `docker/metadata-action`, `docker/build-push-action` READMEs
- Grafana provisioning: `https://keepgrowing.in/tools/grafana-provisioning-how-to-configure-data-sources-and-dashboards/`
- kubeconform: `https://github.com/yannh/kubeconform`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `kubeval` for manifest validation | `kubeconform` (faster, maintained, supports CRDs, offline) | kubeval deprecated ~2022 | Use kubeconform for the keyless validation gate |
| Manual `docker push` + hand-written tags | `docker/metadata-action` + `build-push-action` with `type=sha`/`type=raw` | stable since v4/v5 | Deterministic SHA+latest tags, gha layer cache |
| `actions/setup-python` + pip | `astral-sh/setup-uv` (matches the repo's uv tooling) | uv mainstream 2024–25 | CI parity with local `uv` workflow |
| Grafana manual datasource/dashboard clicks | provisioning yml + dashboard JSON (v5+) | Grafana 5.0+ | Reproducible, GitOps-friendly (D-04 requirement) |
| Async-collector registry rewrite (GH #587) | background-refreshed snapshot + sync `collect()` | n/a | Avoids rewriting prometheus-client internals |

**Deprecated/outdated:** kubeval (→ kubeconform); the dev-only web image as a publishable artifact (→ production multi-stage build, Pitfall 3).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `classification precision` is best surfaced at runtime as human-feedback precision over `defects.status` (applied vs rejected), since the `classifications` table has no ground-truth label | Open Q1 / Pitfall 5 | The gauge could measure the wrong thing; resolve before locking gauge semantics |
| A2 | The keyless pytest lane (`not graph/search/functional/e2e/live_llm`) needs NO backing services in CI (no Postgres) | CI/CD Pattern 4 | If an `integration`-marked test needs Postgres, add a `services: postgres` container — confirm by inspecting `tests/integration` markers |
| A3 | A 30s refresh interval (< scrape interval) is acceptable freshness for these slow-moving operational gauges | Pattern 1 | If near-real-time is required, lower the interval (still cheap) — minor |
| A4 | `/metrics` may be unauthenticated for local single-operator validation (no secrets/PII in aggregate gauges) | Pattern 2 | If a scrape token is required, add a header gate on `expose` — small, deferrable |
| A5 | The dev-only web Dockerfile should be replaced with a production build for the K8s/CI image | Pitfall 3 | If kept dev-only, document it; memory/footprint implications under the 3GB cap |
| A6 | GHCR namespace is `ghcr.io/honraoclaude/<api|web>` per D-02 | CI/CD | Wrong org/name → push 403; verify the actual GitHub owner |
| A7 | Action major versions (checkout@v5, build-push-action@v6, login-action@v4, metadata-action@v5, setup-uv@v6, setup-node@v5) are current as of June 2026 | CI/CD Pattern 4 | Pin to whatever is current at plan time; majors drift — verify before committing |

## Open Questions

1. **What does `classification precision` mean at runtime, and what is its data source?** (HIGH priority — blocks gauge semantics)
   - What we know: the `classifications` table stores predicted class + 0-100 confidence, NO ground-truth label. Precision is measured offline by the QUAL-03 harness (hand-labeled set, accuracy 10/10 in 09-02). The `defects.status` (draft/applied/rejected) DOES record human judgment on filed defects.
   - What's unclear: whether the operator wants (a) live human-feedback precision over `defects.status` (applied/(applied+rejected)), (b) the last-measured QUAL-03 accuracy as a static gauge, or (c) a confidence-distribution proxy.
   - Recommendation: surface **(a)** as `qa_platform_classification_precision` (honest, queryable, moves with operator feedback) and document the definition in the gauge HELP; the planner/discuss-phase should confirm with the user.

2. **Does the keyless CI lane require Postgres?**
   - What we know: the lane excludes graph/search/functional/e2e/live_llm. `integration`-marked tests "need a real Postgres."
   - What's unclear: whether any `integration` test runs in the keyless lane (it isn't excluded by the marker set).
   - Recommendation: inspect `apps/api/tests/integration` markers at plan time; if present in the lane, add a `services: postgres` container to the CI `test` job (a known, small pattern).

3. **web image: production build or accept dev-only?** (see Pitfall 3 / A5)
   - Recommendation: production multi-stage build for the publishable image; if deferred, document the dev-image limitation explicitly.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Desktop + K8s OR kind | Live INFRA-02 e2e | Manual-Only (operator's machine) | — | The keyless `kustomize build \| kubeconform` validation needs NO cluster |
| `kustomize` (or `kubectl kustomize`) | Render manifests (keyless + live) | obtain in CI/dev (binary) | latest | — |
| `kubeconform` | Keyless manifest schema validation | obtain in CI/dev (binary) | latest | — |
| `actionlint` | Keyless workflow lint | obtain in CI/dev (binary) | latest | — |
| `promtool` | Keyless `prometheus.yml` check | inside `prom/prometheus` image | — | — |
| GitHub Actions (GHCR) | INFRA-03 publish | yes (push to master) | — | — |
| Provider API key | The LIVE e2e's autonomous explore step needs a key (project-wide note) | NO (placeholder) | — | The deterministic explore path runs keyless, but the live autonomous demo is Manual-Only |
| 3GB Docker Desktop memory | Live full-stack | yes (capped) | 3GB | ES overlay off + monitoring separate + web scaled-to-0 during explore |

**Missing with no fallback:** the LIVE kind/Docker-Desktop-K8s deploy + e2e + live Grafana dashboards (need a running cluster + populated data + a provider key for the autonomous step) → **Manual-Only**.
**Missing with fallback:** none for the keyless gates — every deterministic artifact (manifests, workflow, collector/`/metrics`, prometheus.yml, dashboard JSON) is validatable without a cluster or keys.

## Validation Architecture

nyquist_validation is **enabled** (`config.json: workflow.nyquist_validation: true`).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.* + pytest-asyncio 1.4.* (`asyncio_mode = "auto"`) |
| Config file | `apps/api/pyproject.toml` (`[tool.pytest.ini_options]`, markers, `pythonpath`) |
| Quick run command | `uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional and not search"` (from `apps/api`) |
| Full suite command | `uv run python -m pytest` (from `apps/api`) |
| Frontend checks | `npx tsc --noEmit` + `npx eslint .` (from `apps/web`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-02 | Kustomize base renders + passes schema validation | keyless shell | `kustomize build infra/k8s/base \| kubeconform -strict -summary` | ❌ Wave 0 (script/CI step) |
| INFRA-02 | ES overlay renders | keyless shell | `kustomize build infra/k8s/overlays/elasticsearch \| kubeconform -strict` | ❌ Wave 0 |
| INFRA-02 | monitoring manifests render | keyless shell | `kustomize build infra/k8s/monitoring \| kubeconform -strict` | ❌ Wave 0 |
| INFRA-02 | LIVE deploy + explore→execute→dashboard e2e on kind/Docker-Desktop-K8s | **Manual-Only** | documented `kubectl apply -k` + port-forward + run | n/a (needs cluster + data + key) |
| INFRA-03 | workflow YAML is valid | keyless shell | `actionlint .github/workflows/platform-ci.yml` | ❌ Wave 0 |
| INFRA-03 | keyless lane is green (the gate it enforces) | unit | `uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional and not search"` | ✅ exists |
| INFRA-03 | LIVE build+push to GHCR | **Manual-Only** | push to master / observe Actions run | n/a (needs the push) |
| INFRA-04 | `/metrics` emits the 4 domain gauges against seeded/fixture data | integration (in-process) | `pytest tests/integration/test_metrics_endpoint.py` (seed rows → assert gauge names present + values) | ❌ Wave 0 |
| INFRA-04 | a down source → gauge absent, `/metrics` still 200 (degrade) | unit | `pytest tests/unit/test_metrics_collector.py::test_degrade` (snapshot=None → no gauge, no raise) | ❌ Wave 0 |
| INFRA-04 | `prometheus.yml` is valid | keyless shell | `docker run --rm -v $PWD/infra/monitoring:/cfg prom/prometheus promtool check config /cfg/prometheus.yml` | ❌ Wave 0 |
| INFRA-04 | dashboard JSON is valid + references the gauge names | unit | `pytest tests/unit/test_dashboards_json.py` (json.load each; assert the 4 gauge names appear) | ❌ Wave 0 |
| INFRA-04 | LIVE Grafana renders the dashboards on populated data | **Manual-Only** | bring up monitoring + open Grafana | n/a (needs running stack + data) |

### Sampling Rate
- **Per task commit:** the quick keyless lane + the relevant new keyless gate (kubeconform / actionlint / promtool / json test).
- **Per wave merge:** full `uv run python -m pytest` + all keyless infra gates.
- **Phase gate:** all keyless gates green before `/gsd:verify-work`; the Manual-Only live deploy/e2e/dashboards are checked off in 11-VALIDATION as Manual-Only.

### Wave 0 Gaps
- [ ] `apps/api/tests/unit/test_metrics_collector.py` — snapshot→gauge mapping + degrade (None → absent, no raise) — INFRA-04
- [ ] `apps/api/tests/integration/test_metrics_endpoint.py` — seed rows, GET /metrics, assert the 4 gauge names + values — INFRA-04
- [ ] `apps/api/tests/unit/test_dashboards_json.py` — dashboard JSON valid + references the gauge names — INFRA-04
- [ ] A keyless infra-validation script/CI steps: `kustomize build | kubeconform`, `actionlint`, `promtool check config` — INFRA-02/03/04 (CLI tools, not pytest)
- [ ] CI: `astral-sh/setup-uv` + `actions/setup-node@22` installed in the workflow
- [ ] (confirm Q2) whether the CI `test` job needs a `services: postgres` container

*The keyless lane infrastructure already exists; the gaps above are NEW tests/gates for the Phase-11 artifacts.*

## Security Domain

`security_enforcement` is not disabled in config → included.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | partial | Existing JWT/argon2 unchanged; Phase 11 adds no auth surface. `/metrics` is unauthenticated-but-safe (A4) — aggregate numerics only |
| V3 Session Management | no | No session change |
| V4 Access Control | partial | `/metrics` exposes no per-user data; scrape-token gating deferred |
| V5 Input Validation | minimal | No new user input; the collector reads internal data only. prometheus-client owns exposition format |
| V6 Cryptography | no | No new crypto. Secrets (JWT_SECRET, TARGET_CREDENTIAL_KEY, NEO4J_AUTH, provider keys) move into K8s Secrets re-using existing names — never literals in manifests |
| V14 Config / Deployment | **yes** | K8s Secrets (not ConfigMaps) for sensitive env; `secret.example.yaml` committed, real values gitignored; GHCR via scoped `GITHUB_TOKEN` (least privilege: `packages: write` only); CI token never echoed (the run-suite.yml precedent) |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secret leakage in manifests | Information Disclosure | K8s Secret manifests with placeholder/example values; real values gitignored; never inline secrets in Deployments |
| `/metrics` exposing sensitive data | Information Disclosure | Emit only aggregate numeric gauges + HTTP histograms — no prompts/credentials/PII (PLAT-07 discipline: the llm_usage ledger already excludes prompt/response text) |
| GHCR token over-privilege | Elevation of Privilege | `permissions: { contents: read, packages: write }` — minimal; the built-in token, no PAT |
| CI secret echo | Information Disclosure | Never print tokens/headers in workflow logs (the run-suite.yml T-07-07 precedent) |
| Image supply chain | Tampering | SHA-tagged images (immutable ref) + reproducible `uv sync --frozen` / `npm ci` builds + gha cache (not a trust boundary) |

## Sources

### Primary (HIGH confidence)
- `https://prometheus.github.io/client_python/collector/custom/` — custom Collector `collect()` + `GaugeMetricFamily.add_metric` + REGISTRY.register; collect() is sync, fresh per scrape
- `apps/api/app/main.py`, `core/{redis_client,neo4j_driver,es_client}.py`, `db/session.py`, `core/config.py` — lifespan pattern, lazy clients, graceful-degrade (503-not-500), async session/driver — the collector's bridge template
- `apps/api/app/services/healing/stats.py`, `services/coverage_dash.py`, `models/llm_usage.py`, `models/defects.py`, `services/defects/classifier.py` — the 4 domain-metric data sources + the precision-source gap
- `infra/docker-compose.yml` — service set, `mem_limit`s, healthchecks, profiles, in-cluster hostnames (the K8s translation source)
- `.github/workflows/run-suite.yml` — Actions syntax + scoped-token discipline precedent
- `CLAUDE.md` — locked stack, exporter table, Neo4j-Enterprise caveat, 3GB cap, runtime baselines
- PyPI JSON API (queried 2026-06-29): prometheus-client 0.25.0 (2026-04-09), prometheus-fastapi-instrumentator 8.0.2

### Secondary (MEDIUM confidence — verified against official sources)
- `https://github.com/yannh/kubeconform` — offline, cluster-less, fast schema validation; `kustomize build | kubeconform`
- docker `login-action`/`metadata-action`/`build-push-action` READMEs — GHCR login via GITHUB_TOKEN, `packages: write`, `type=sha`/`type=raw` tags, `cache-from/to: type=gha`
- `https://www.rabbitmq.com/docs/prometheus` — built-in `rabbitmq_prometheus` plugin on :15692
- `https://keepgrowing.in/tools/grafana-provisioning-how-to-configure-data-sources-and-dashboards/` — Grafana v5+ provisioning layout (datasources/ + dashboards/ + provider yml)
- `hub.docker.com/r/prometheuscommunity/postgres-exporter`, `prometheus.io/docs/instrumenting/exporters/` — exporter image names + env

### Tertiary (LOW confidence — flagged for validation)
- GH issue prometheus/client_python#587 — confirms async collectors require registry rewrites (cited as an anti-pattern to AVOID, not to follow)
- Action major version currency (A7) — verify pins at plan time

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — both new deps version-verified on PyPI, slopcheck [OK], real source repos; exporter images cited
- Architecture (K8s/CI/Grafana): HIGH — mechanical compose→K8s translation + documented action/provisioning patterns + strong in-repo precedent
- Collector bridge: HIGH — the sync-over-async risk is real and the background-snapshot resolution is sound and matches the repo's lifespan/degrade conventions
- Pitfalls: HIGH — derived from the actual codebase (dev-only web image, 3GB math, precision-source gap, AMQP-vs-metrics port)
- Open Q1 (precision source): MEDIUM — a genuine semantic decision the user/discuss-phase must confirm

**Research date:** 2026-06-29
**Valid until:** ~2026-07-29 for the stable bits (K8s/Grafana/exporter patterns); ~2026-07-13 for the fast-moving bits (GitHub Action major versions — re-verify at plan time)
