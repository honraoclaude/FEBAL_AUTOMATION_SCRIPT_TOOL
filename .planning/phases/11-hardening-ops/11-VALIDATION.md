---
phase: 11
slug: hardening-ops
status: draft
nyquist_compliant: false
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
| **Infra-as-code validation** | `kustomize build infra/k8s/base | kubeconform -strict -summary` (+ the ES + monitoring overlays); `actionlint .github/workflows/*.yml`; `promtool check config infra/monitoring/prometheus.yml`; Grafana dashboard JSON valid + references the gauge names |
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

> Populated by the planner. Each task maps to INFRA-02/03/04, a test type (unit deterministic /
> infra-as-code CLI validation / live-cluster-manual), a threat ref, and a keyless command. The
> /metrics endpoint + the 4 gauges + scrape-tolerance, the manifest validity (kustomize+kubeconform),
> the CI workflow shape (actionlint), and the prometheus/Grafana config validity are ALL deterministic
> WITHOUT a live cluster; the live kind deploy + the e2e run + the live Grafana dashboards are Manual-Only.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | INFRA-02/03/04 | — | populated by planner | — | — | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] prometheus-client 0.25.x + prometheus-fastapi-instrumentator 8.0.x added to apps/api/pyproject.toml + `uv sync` (the expected new BACKEND deps; gated checkpoint:human-verify; both in CLAUDE.md)
- [ ] kubeconform + actionlint + promtool available as CLI validators (dev/CI tools, NOT pip deps — document how they're obtained; gate any test that needs them to skip cleanly if absent locally)
- [ ] A background-refreshed metrics-snapshot seam (lifespan task) + seeded/fixture data (heal stats / classification defects.status / coverage / llm_usage) so the 4 gauges are unit-testable WITHOUT a live cluster
- [ ] Production multi-stage Dockerfile stages/targets for api (no --reload) + web (next build/start) — buildable in CI
- [ ] infra/k8s/ Kustomize base + ES overlay + monitoring manifests scaffold; infra/monitoring/ (prometheus.yml + grafana provisioning) scaffold
- [ ] Existing functional infra (the keyless pytest lane, the graceful-degrade handlers as the scrape-tolerance precedent, the compose profile pattern) carries forward

*Existing infrastructure (the keyless deterministic lane, the neo4j/ES degrade handlers, the metric-source services, the compose service set + mem_limits, the run-suite.yml Actions precedent) covers most of the phase; the prometheus deps + the custom collector + the K8s/CI/monitoring scaffolds are the new Wave-0 pieces.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live K8s deploy + explore→execute→dashboard e2e | INFRA-02 | Needs a running kind / Docker Desktop K8s cluster + a populated dataset (some upstream steps need provider keys) | `kind create cluster` (or enable Docker Desktop K8s); `kubectl apply -k infra/k8s/base`; run explore→execute→open a dashboard; confirm the core path succeeds under realistic limits (ES overlay off) |
| Live CI/CD build+publish to GHCR | INFRA-03 | Runs on the GitHub Actions runner on push | Push to master; confirm the test job gates, then the api+web images publish to ghcr.io tagged SHA+latest |
| Live Grafana dashboards over real data | INFRA-04 | Needs Prometheus scraping a running platform with real heal/classification/coverage/cost data | `docker compose --profile monitoring up -d`; open Grafana; confirm the 4 domain panels + platform-health render from live scrapes |
| 3GB memory fit on the K8s deploy | (infra) | host Vmmem observation | `kubectl top pods` / `docker stats` during the e2e — confirm the core set (ES off, monitoring separate) stays under the cap |

*Deterministic logic (the /metrics endpoint + 4 gauges + scrape-tolerance, manifest validity via kustomize+kubeconform, the CI workflow via actionlint, prometheus/Grafana config validity) is automated WITHOUT a live cluster.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (prometheus deps, CLI validators, snapshot seam + fixtures, prod Dockerfiles, k8s/monitoring scaffolds)
- [ ] No watch-mode flags
- [ ] Feedback latency < 3 min
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
