---
phase: 11
slug: hardening-ops
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-29
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (pytest-asyncio 1.4) for the /metrics endpoint + collector unit tests; CLI validators for infra-as-code (kustomize build + kubeconform for manifests, actionlint for the workflow, promtool + JSON validation for prometheus.yml/Grafana). Invoke pytest as `uv run python -m pytest` (Windows AppControl blocks the `pytest.exe` shim — os error 4551; Linux CI unaffected). |
| **Config file** | apps/api/pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd apps/api && uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional and not search" -q` (the /metrics endpoint emits the 4 domain gauges from a background-refreshed snapshot over seeded data + the instrumentator HTTP metrics + scrape-tolerance when a source is down — keyless, no live cluster) |
| **Infra-as-code validation** | `kustomize build infra/k8s/base \| kubeconform -strict -summary` (+ the ES + monitoring overlays via `infra/k8s/validate.sh`); `actionlint .github/workflows/platform-ci.yml`; `docker run --rm -v $PWD/infra/monitoring:/cfg prom/prometheus promtool check config /cfg/prometheus.yml`; Grafana dashboard JSON valid + references the gauge names (`tests/unit/test_dashboards_json.py`) |
| **Full suite command** | `cd apps/api && uv run python -m pytest -m "not live_llm" -q` (unchanged — Phase 11 adds no graph/search/functional product tests; the metrics tests are in the keyless lane) |
| **Estimated runtime** | ~2-3 min (metrics unit tests + the CLI validators are fast; no heavy product tests added) |

---

## Sampling Rate

- **After every task commit:** the relevant validator — `uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional and not search" -q` for the collector/endpoint; `kustomize build … | kubeconform` for manifests; `actionlint` for the workflow; `promtool`/JSON for monitoring
- **After every plan wave:** the keyless metrics lane + all infra-as-code validators green
- **Before `/gsd:verify-work`:** /metrics emits the 4 gauges + degrades honestly; manifests kubeconform-valid; the workflow actionlint-clean; prometheus.yml promtool-valid + the Grafana dashboards JSON-valid referencing the gauge names; the LIVE kind deploy + the explore→execute→dashboard e2e + the live Grafana dashboards demonstrated (Manual-Only)
- **Max feedback latency:** ~3 min

---

## Per-Task Verification Map

> Each task maps to INFRA-02/03/04, a test type (unit deterministic / infra-as-code CLI validation /
> live-cluster-manual), a threat ref, and a keyless command. The /metrics endpoint + the 4 gauges +
> scrape-tolerance, the manifest validity (kustomize+kubeconform), the CI workflow shape (actionlint),
> and the prometheus/Grafana config validity are ALL deterministic WITHOUT a live cluster; the live
> kind deploy + the e2e run + the live Grafana dashboards are Manual-Only.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| P1-T1 | 11-01 | 1 | INFRA-04 | T-11-SC | Gated deps via blocking-human checkpoint; slopcheck [OK] | checkpoint + import | `cd apps/api && uv run python -c "import prometheus_client, prometheus_fastapi_instrumentator"` | ❌ W0 | ⬜ pending |
| P1-T2 | 11-01 | 1 | INFRA-04 | T-11-01/02/03 | /metrics aggregate-numeric-only; O(1) cached scrape; down source → absent gauge, never 500 | unit + integration | `cd apps/api && uv run python -m pytest tests/unit/test_metrics_collector.py tests/integration/test_metrics_endpoint.py -q` | ❌ W0 | ⬜ pending |
| P1-T3 | 11-01 | 1 | INFRA-04 | T-11-04 | Config-as-code, JSON/promtool-validated before deploy; monitoring OFF by default | unit + infra-CLI | `cd apps/api && uv run python -m pytest tests/unit/test_dashboards_json.py -q` + `docker run --rm -v $PWD/infra/monitoring:/cfg prom/prometheus promtool check config /cfg/prometheus.yml` | ❌ W0 | ⬜ pending |
| P2-T1 | 11-02 | 2 | INFRA-03 | T-11-08 | Prod images (no dev hot-reload watchers); no secrets baked in | infra-CLI (grep) | `grep -v '^#' apps/api/Dockerfile \| grep -c -- '--reload'` is 0; `grep 'AS build' apps/web/Dockerfile` | ❌ W0 | ⬜ pending |
| P2-T2 | 11-02 | 2 | INFRA-03 | T-11-05/06/07/09 | Least-privilege GHCR token; never-echo; SHA-immutable; test-gate; saucedemo not published | infra-CLI (actionlint) | `actionlint .github/workflows/platform-ci.yml` | ❌ W0 | ⬜ pending |
| P3-T1 | 11-03 | 3 | INFRA-02 | T-11-10/11/14 | Secrets in Secret (example values); requests+limits; GHCR images | infra-CLI (kubeconform) | `kustomize build infra/k8s/base \| kubeconform -strict` + ES overlay | ❌ W0 | ⬜ pending |
| P3-T2 | 11-03 | 3 | INFRA-02 | T-11-11/12/13 | kubeconform gate; documented 3GB fit; ClusterIP-scoped /metrics | infra-CLI (kubeconform + script) | `kustomize build infra/k8s/monitoring \| kubeconform -strict` + `bash infra/k8s/validate.sh` | ❌ W0 | ⬜ pending |
| MANUAL-1 | 11-03 | 3 | INFRA-02 | T-11-11 | Live deploy + explore→execute→dashboard e2e under realistic limits | live-cluster-manual | `kubectl apply -k infra/k8s/base` + port-forward + run (Manual-Only) | n/a | ⬜ manual |
| MANUAL-2 | 11-02 | 2 | INFRA-03 | T-11-05/07 | Live build+push to GHCR on push to master | live-CI-manual | push to master; observe Actions (Manual-Only) | n/a | ⬜ manual |
| MANUAL-3 | 11-01/03 | 1/3 | INFRA-04 | T-11-01 | Live Grafana renders the 4 domain panels + platform-health over real scrapes | live-cluster-manual | `docker compose --profile monitoring up -d`; open Grafana (Manual-Only) | n/a | ⬜ manual |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] prometheus-client 0.25.x + prometheus-fastapi-instrumentator 8.0.x added to apps/api/pyproject.toml + `uv sync` (the expected new BACKEND deps; gated checkpoint:human-verify; both in CLAUDE.md) — **11-01 Task 1**
- [ ] kubeconform + actionlint + promtool available as CLI validators (dev/CI tools, NOT pip deps — `infra/k8s/validate.sh` skip-cleans when absent locally; CI obtains them via release binaries / docker run)
- [ ] A background-refreshed metrics-snapshot seam (lifespan task) + seeded/fixture data (heal stats / classification defects.status / coverage / llm_usage) so the 4 gauges are unit-testable WITHOUT a live cluster — **11-01 Task 2 (tests/unit/test_metrics_collector.py + tests/integration/test_metrics_endpoint.py)**
- [ ] tests/unit/test_dashboards_json.py — dashboard JSON valid + references the gauge names — **11-01 Task 3**
- [ ] Production multi-stage Dockerfile stages/targets for api (no --reload) + web (next build/start) — buildable in CI — **11-02 Task 1**
- [ ] infra/k8s/ Kustomize base + ES overlay + monitoring manifests scaffold; infra/monitoring/ (prometheus.yml + grafana provisioning) scaffold — **11-01 Task 3 (monitoring config) + 11-03 (manifests)**
- [ ] Existing functional infra (the keyless pytest lane, the graceful-degrade handlers as the scrape-tolerance precedent, the compose profile pattern) carries forward

*Existing infrastructure (the keyless deterministic lane, the neo4j/ES degrade handlers, the metric-source services, the compose service set + mem_limits, the run-suite.yml Actions precedent) covers most of the phase; the prometheus deps + the custom collector + the K8s/CI/monitoring scaffolds are the new Wave-0 pieces.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live K8s deploy + explore→execute→dashboard e2e | INFRA-02 | Needs a running kind / Docker Desktop K8s cluster + a populated dataset (some upstream steps need provider keys) | `kind create cluster` (or enable Docker Desktop K8s); `kubectl apply -k infra/k8s/base`; port-forward web+api; run explore→execute→open a dashboard; confirm the core path succeeds under realistic limits (ES overlay off) |
| Live CI/CD build+publish to GHCR | INFRA-03 | Runs on the GitHub Actions runner on push | Push to master; confirm the test job gates, then the api+web images publish to ghcr.io tagged SHA+latest |
| Live Grafana dashboards over real data | INFRA-04 | Needs Prometheus scraping a running platform with real heal/classification/coverage/cost data | `docker compose --profile monitoring up -d`; open Grafana; confirm the 4 domain panels + platform-health render from live scrapes |
| 3GB memory fit on the K8s deploy | (infra) | host Vmmem observation | `kubectl top pods` / `docker stats` during the e2e — confirm the core set (ES off, monitoring separate) stays under the cap |

*Deterministic logic (the /metrics endpoint + 4 gauges + scrape-tolerance, manifest validity via kustomize+kubeconform, the CI workflow via actionlint, prometheus/Grafana config validity) is automated WITHOUT a live cluster.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (prometheus deps, CLI validators, snapshot seam + fixtures, prod Dockerfiles, k8s/monitoring scaffolds)
- [x] No watch-mode flags
- [x] Feedback latency < 3 min
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planner-signed (2026-06-29) — Wave 0 completion (the gated deps + the snapshot seam + the test scaffolds + the manifest/CI/monitoring scaffolds) is satisfied within 11-01 Task 1-3, 11-02 Task 1, and 11-03 during execution.
