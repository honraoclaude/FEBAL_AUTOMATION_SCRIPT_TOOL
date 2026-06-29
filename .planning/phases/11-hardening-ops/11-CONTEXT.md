# Phase 11: Hardening & Ops - Context

**Gathered:** 2026-06-29
**Status:** Ready for planning (needs --research-phase — the K8s manifest set + resource sizing under the 3GB cap, the prometheus-client custom-collector + instrumentator wiring, the GHCR build/publish workflow, and the Grafana dashboards-as-code provisioning have no canonical reference)

<domain>
## Phase Boundary

The FINAL phase: the platform ships and operates like a product. Kubernetes manifests deploy the full stack on Docker Desktop K8s / kind with realistic resource limits, and an end-to-end run (explore → execute → dashboard) succeeds on that deployment. GitHub Actions CI/CD builds, tests, and publishes the platform images on push. Grafana-on-Prometheus dashboards show platform health PLUS the four domain metrics — healing success rate, classification precision, coverage, LLM cost — via APP-LEVEL exporters (no Enterprise-only Neo4j Prometheus endpoint). Delivers INFRA-02/03/04. UI hint: NO — observability is Grafana (external), not the Next.js app; no UI-SPEC.

**In scope:** raw-YAML/Kustomize K8s manifests for the platform (core services always-on, Elasticsearch as an optional overlay) validated on Docker Desktop K8s/kind + an e2e run (INFRA-02); a GitHub Actions CI/CD workflow that runs the keyless deterministic suite + tsc/eslint then builds & publishes the api + web images to GHCR on push to master (INFRA-03); a /metrics endpoint exposing the 4 domain metrics via a pull-on-scrape prometheus-client custom collector + prometheus-fastapi-instrumentator HTTP metrics, a compose `monitoring` profile + K8s manifests for Prometheus + Grafana, and dashboards-as-code (INFRA-04).
**Out of scope (no later phase — this is the last):** any NEW platform capability (Phases 1-10 own the product; this phase only deploys/builds/observes it); the Enterprise-only Neo4j native Prometheus endpoint (app-level metrics instead); production cloud K8s / managed registries / secrets-management beyond what kind+GHCR need (local validation only — this is a single-operator dev platform); the Phase-7 `run-suite.yml` suite-trigger (distinct from the platform CI/CD here).

</domain>

<decisions>
## Implementation Decisions

### K8s manifests: tooling + memory (INFRA-02)
- **D-01:** Plain Kubernetes YAML under `infra/k8s/` as a KUSTOMIZE base (no Helm — a single operator validating on kind/Docker Desktop K8s does not need templating). CORE services (Postgres / Redis / RabbitMQ / api / worker / web / **Neo4j** — Neo4j is required for explore→coverage→traceability, so it is in the core set) deploy with resource requests + limits matching the compose `mem_limit`s. **Elasticsearch is an OPTIONAL Kustomize overlay** (search graceful-degrades — already built) so the SC1 e2e (explore → execute → dashboard) fits under the 3GB cap. Document the realistic per-service sizing + the "ES overlay off for the e2e" note. (Research: the exact manifest set — Deployments/StatefulSets/Services/ConfigMaps/Secrets/PVCs — image refs to the GHCR images, init/healthcheck → readiness/liveness probes, and the e2e validation steps on kind/Docker Desktop K8s.)

### CI/CD: registry + test scope (INFRA-03)
- **D-02:** Publish to GitHub Container Registry (GHCR — free, native to Actions, uses the built-in GITHUB_TOKEN, no extra registry secret). On push to master: a `test` job runs the KEYLESS deterministic pytest lane (`uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional and not search"`) + frontend `tsc --noEmit` + eslint; then a `build-publish` job builds & pushes the `api` and `web` images to `ghcr.io/honraoclaude/...`, tagged by commit SHA + `latest`. SauceDemo is a TEST FIXTURE image (built where tests need it, NOT published as a platform image). (Research: the workflow YAML — matrix/jobs, uv + node setup, docker buildx + GHCR login via GITHUB_TOKEN, caching, the test-before-publish gate; what to do about the Windows-AppControl pytest-shim on the Linux CI runner — `python -m pytest` works everywhere so keep it.)

### Domain-metrics exposure (INFRA-04)
- **D-03:** PULL-ON-SCRAPE. A prometheus-client custom Collector that, on each `/metrics` scrape, queries the EXISTING services — healing/stats (heal success rate), defects classification accuracy (classification precision), coverage_dash (coverage %), llm_usage (LLM cost) — and emits gauges. Always current, no double-write, no metric-write coupling in the hot paths, reuses shipped logic. PLUS prometheus-fastapi-instrumentator for HTTP latency/status metrics on `/metrics`. APP-LEVEL only — NO Enterprise Neo4j endpoint. prometheus-client 0.25 + prometheus-fastapi-instrumentator 8.0 are gated new deps. Scrapes must be cheap + failure-tolerant (a metric source down → that gauge absent/NaN, never a 500 on /metrics). (Research: the Collector implementation [sync collect() over async services — run the read in a loop/thread or precompute]; the gauge names/labels; making /metrics unauthenticated-but-safe or scrape-token-gated; the standard exporters for pg/redis/rabbitmq/ES from the CLAUDE.md table.)

### Monitoring stack + dashboards-as-code (INFRA-04)
- **D-04:** Prometheus + Grafana run BOTH as a compose `monitoring` profile (OFF by default — 3GB cap) AND as K8s manifests (so the K8s deployment has observability too). The Grafana DATASOURCE + the DASHBOARDS (platform health + the 4 domain metrics) are provisioned AS CODE — committed `grafana/provisioning/datasources/*.yml` + `dashboards/*.json` + a `prometheus.yml` scrape config (api `/metrics` + the pg/redis/rabbitmq exporters). Reproducible on a fresh deploy, no manual Grafana clicking. (Research: the prometheus scrape config + the exporter sidecars/services; the Grafana provisioning layout for compose AND K8s [ConfigMap-mounted]; the 4 domain-metric panels + a platform-health panel.)

### Claude's Discretion / for research (--research-phase)
- The full K8s manifest set + the Kustomize base/overlay layout + resource sizing under 3GB + the e2e validation procedure on kind/Docker Desktop K8s.
- The custom-collector implementation (sync collect() bridging the async read-services), gauge naming, and the standard per-component exporters (postgres/redis/rabbitmq/ES) from the CLAUDE.md exporter table.
- The GHCR build/publish workflow (buildx, GITHUB_TOKEN login, SHA+latest tags, test-gate) + image-build reproducibility.
- The Grafana provisioning (datasource + dashboards-as-code JSON) for compose + K8s; the prometheus.yml scrape targets.
- How to TEST this phase deterministically/keylessly: manifest validity (kubeconform/kustomize build), the /metrics endpoint emitting the 4 gauges (against fixture/seeded data, no live cluster), the CI workflow lint/shape; the LIVE kind deploy + e2e + the live Grafana dashboards are Manual-Only (need a running cluster + a populated dataset).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — INFRA-02, INFRA-03, INFRA-04 (INFRA-01 done in Phase 1).
- `.planning/ROADMAP.md` (Phase 11 section) — the 3 success criteria.

### Locked stack & carried conventions
- `CLAUDE.md` — prometheus-client 0.25.x (custom domain metrics), prometheus-fastapi-instrumentator 8.0.x (HTTP /metrics), Grafana + Prometheus, the EXPORTER TABLE (postgres-exporter, redis_exporter, rabbitmq built-in prometheus plugin :15692, elasticsearch-exporter; **Neo4j native Prometheus is Enterprise-only → emit app-level graph metrics instead**), Docker/Kubernetes + Docker Desktop K8s/kind, GitHub Actions, Docker Compose profiles (infra/app/monitoring). The 3GB Windows/Docker-Desktop cap (the dominant sizing constraint).

### Reusable seams (read the summaries + code)
- `infra/docker-compose.yml` (the full service set + mem_limits + the profile pattern [graph/queue/search] — the K8s manifests translate these; the new `monitoring` profile) + `.planning/phases/01-foundation-dev-environment/01-*-SUMMARY.md`.
- `apps/api/Dockerfile` + `apps/web/Dockerfile` (the images CI builds/publishes + K8s deploys) + `infra/targets/saucedemo/Dockerfile` (test-fixture image).
- `apps/api/app/main.py` (the FastAPI app + lifespan — where /metrics + the instrumentator mount; the neo4j/ES graceful-degrade handlers as the scrape-tolerance precedent).
- The metric SOURCES (already computed as data): `apps/api/app/services/healing/stats.py` (heal success rate), `apps/api/app/services/defects/` + the Phase-9 classification accuracy (precision), `apps/api/app/services/coverage_dash.py` (coverage %), `apps/api/app/models/llm_usage.py` + the Phase-2 cost ledger (LLM cost) — the custom collector queries these.
- `.github/workflows/run-suite.yml` (the Phase-7 suite trigger — the Actions-syntax precedent; INFRA-03 is a SEPARATE platform build/publish workflow).
- The keyless deterministic test lane (`uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional and not search"`) — what CI runs.

### Known issues / project-wide
- 3GB Windows/Docker-Desktop cap: the FULL stack (Postgres+Neo4j+ES+RabbitMQ+Redis+api+worker+web+Prometheus+Grafana) cannot all run at once — K8s core set excludes ES (optional overlay) + monitoring is a separate profile; the live e2e + live Grafana are Manual-Only.
- Windows AppControl blocks the `pytest.exe` shim locally (`uv run python -m pytest`); the Linux CI runner is unaffected but keep `python -m pytest` for portability.
- No NEW provider-key dependence here — manifests/CI/metrics are deterministic; only the LIVE kind-deploy e2e + live dashboards (needing a running cluster + populated data, some of which needs keys upstream) are Manual-Only.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- infra/docker-compose.yml (service set + mem_limits + profiles) → the K8s manifest source + the new monitoring profile.
- apps/api/Dockerfile + apps/web/Dockerfile → CI build/publish + K8s images.
- apps/api/app/main.py (lifespan + degrade handlers) → /metrics + instrumentator mount + scrape tolerance.
- healing/stats.py + defects classification + coverage_dash.py + llm_usage.py → the 4 domain-metric sources the custom collector queries.
- .github/workflows/run-suite.yml → Actions-syntax precedent (separate platform CI/CD workflow here).
- The keyless deterministic pytest lane → the CI test job.

### Established Patterns
- Compose profiles to keep heavy services off (the K8s analog: optional overlays + a monitoring profile); per-service mem_limits → K8s requests/limits; graceful-degrade when a service is down (→ /metrics scrape tolerance); gated new deps behind checkpoint:human-verify (aio-pika/recharts/atlassian-python-api/elasticsearch precedent → prometheus-client + instrumentator); `uv run python -m pytest` test invocation; deterministic/keyless tests + a clear Manual-Only split (live cluster/dashboards).
- Carry forward: app-level metrics over Enterprise endpoints; pull-on-scrape (no hot-path metric coupling); dashboards/provisioning AS CODE (reproducible); honest degrade (a down metric source → absent gauge, never a 500).

### Integration Points
- New infra/k8s/ Kustomize base + ES overlay + monitoring manifests; a new platform CI/CD workflow publishing api+web to GHCR; prometheus-client + instrumentator deps + a /metrics endpoint + the custom collector in apps/api; a compose monitoring profile + prometheus.yml + grafana provisioning (datasource + dashboards-as-code) + the per-component exporters.

</code_context>

<specifics>
## Specific Ideas

- The 4 domain metrics already EXIST as data (heal stats, classification accuracy, coverage, LLM cost ledger) — Phase 11 EXPOSES them via a pull-on-scrape collector, never recomputes or double-writes.
- The 3GB cap shapes everything: K8s core set without ES (optional overlay), monitoring as a separate profile, live e2e + dashboards Manual-Only — the manifest/collector/CI shape is deterministically testable without a live cluster.
- App-level metrics only (no Enterprise Neo4j endpoint) — a deliberate CLAUDE.md decision; graph metrics come from the app, not the DB.
- Everything-as-code: Kustomize manifests, the CI workflow, the prometheus scrape config, and the Grafana datasource + dashboards are all committed + reproducible.
- This is the LAST phase — it adds NO product capability, only deploy/build/observe; after it, all 11 phases + every REQUIREMENT are complete.

</specifics>

<deferred>
## Deferred Ideas

- Production cloud K8s (EKS/GKE/AKS) + managed registries + real secrets management + ingress/TLS → out of scope (single-operator local validation on kind/Docker Desktop K8s).
- The Enterprise-only Neo4j native Prometheus endpoint → rejected (app-level graph metrics per CLAUDE.md).
- Autoscaling / HPA / multi-replica production tuning → out of scope (the workers are stateless + replica-ready by design, but production scaling isn't validated here).
- Alerting rules / Alertmanager / on-call → out of scope (dashboards only this phase).
- Write-time metric gauges → rejected (pull-on-scrape avoids hot-path coupling).

None of these block Phase 11 — discussion stayed within the deploy/build/observe scope.

</deferred>

---

*Phase: 11-hardening-ops*
*Context gathered: 2026-06-29*
