# Phase 11: Hardening & Ops - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-29
**Phase:** 11-hardening-ops
**Areas discussed:** K8s manifests (tooling + memory), CI/CD (registry + test scope), Domain-metrics exposure, Monitoring stack + dashboards

---

## K8s manifests: tooling + memory (INFRA-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Raw YAML/Kustomize, core always-on, ES optional overlay | Kustomize base under infra/k8s/; core (pg/redis/rabbit/api/worker/web/neo4j) with limits ~ compose mem_limits; ES optional overlay (search degrades) so the e2e fits under 3GB | ✓ |
| Helm chart | Templated chart with values; heavier authoring + a Helm dep for one operator | |
| Everything always-on, tuned limits | All services incl. ES + Neo4j; likely OOMs the e2e on 3GB | |

**User's choice:** Raw YAML/Kustomize, core always-on, ES optional overlay
**Notes:** Neo4j is core (explore→coverage needs it); ES is the optional overlay (search graceful-degrades, already built); the e2e explore→execute→dashboard fits under the cap.

---

## CI/CD: registry + test scope (INFRA-03)

| Option | Description | Selected |
|--------|-------------|----------|
| GHCR + deterministic suite + build/publish api & web | GHCR via GITHUB_TOKEN; push→master runs keyless pytest + tsc/eslint then builds/pushes api+web (SHA+latest); saucedemo = test fixture, not published | ✓ |
| Docker Hub | Needs Docker Hub secrets; not native to Actions | |
| Lint/build only (no tests) | Drops the 'tests' half of INFRA-03; lets regressions publish | |

**User's choice:** GHCR + deterministic suite + build/publish api & web
**Notes:** Native to Actions (built-in token), test-before-publish gate, SauceDemo stays a test fixture.

---

## Domain-metrics exposure (INFRA-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Pull-on-scrape custom collector + instrumentator | prometheus_client Collector queries the existing services on /metrics scrape (heal/classification/coverage/LLM-cost) → gauges; + instrumentator HTTP metrics; app-level only | ✓ |
| Write-time gauges | Update gauges in the hot paths; cheaper scrapes but metric-write coupling + drift risk | |

**User's choice:** Pull-on-scrape custom collector + instrumentator
**Notes:** Always current, no double-write, reuses shipped logic; scrapes cheap + failure-tolerant; no Enterprise Neo4j endpoint.

---

## Monitoring stack + dashboards-as-code (INFRA-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Compose 'monitoring' profile + K8s manifests, dashboards-as-code | Prometheus+Grafana in a compose monitoring profile (off by default) AND K8s manifests; datasource + dashboards provisioned as committed JSON/YAML | ✓ |
| Compose only | No K8s monitoring; the K8s deploy has no observability | |
| Manual Grafana dashboards | Hand-built; not reproducible/committed | |

**User's choice:** Compose 'monitoring' profile + K8s manifests, dashboards-as-code
**Notes:** Reproducible on a fresh deploy; both compose + K8s have observability; prometheus.yml + grafana provisioning committed.

---

## Claude's Discretion

- The full K8s manifest set + Kustomize base/overlay layout + 3GB resource sizing + the kind/Docker-Desktop-K8s e2e validation procedure.
- The custom-collector implementation (sync collect() bridging async read-services), gauge naming, the standard pg/redis/rabbitmq/ES exporters.
- The GHCR build/publish workflow (buildx, GITHUB_TOKEN, SHA+latest, test-gate).
- The Grafana provisioning (datasource + dashboards-as-code) for compose + K8s + the prometheus.yml scrape targets.
- The deterministic/keyless test approach (manifest validity via kustomize build/kubeconform; /metrics emitting the 4 gauges on fixtures; CI shape) vs the Manual-Only live kind deploy + e2e + live dashboards.

## Deferred Ideas

- Production cloud K8s + managed registries + secrets/ingress/TLS → out of scope (local validation).
- Enterprise Neo4j native Prometheus endpoint → rejected (app-level metrics).
- Autoscaling/HPA/multi-replica production tuning → out of scope.
- Alerting/Alertmanager/on-call → out of scope (dashboards only).
- Write-time metric gauges → rejected (pull-on-scrape).
