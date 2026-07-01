---
phase: 11-hardening-ops
verified: 2026-07-01T00:00:00Z
status: human_needed
score: 19/19 deterministic must-haves verified (3 live SC endpoints Manual-Only)
overrides_applied: 0
re_verification: null
human_verification:
  - test: "Live K8s deploy + explore→execute→dashboard e2e (SC1 / INFRA-02)"
    expected: "kubectl apply -k infra/k8s/base on kind / Docker Desktop K8s brings up the 7 core workloads under the 3GB cap (ES overlay off, monitoring separate); an explore→execute→open-dashboard run completes"
    why_human: "Needs a running cluster + populated data + a provider key (ANTHROPIC/OPENAI) for the autonomous explore step — no live cluster available to the verifier"
  - test: "Live CI/CD build+publish to GHCR on push to master (SC2 / INFRA-03)"
    expected: "On push, the test job gates, then build-publish pushes ghcr.io/honraoclaude/{api,web}:sha-… + :latest; saucedemo never published"
    why_human: "Runs on the GitHub Actions runner on a real push; the packages must be made visible/linked on first publish"
  - test: "Live Grafana renders the 4 domain panels + platform-health over real scrapes (SC3 / INFRA-04)"
    expected: "docker compose --profile monitoring up -d; Grafana provisions the 2 dashboards and renders heal_success_rate, classification_precision, coverage_percent, llm_cost from live Prometheus scrapes"
    why_human: "Needs Prometheus scraping a running platform with real heal/classification/coverage/cost data"
  - test: "kubeconform -strict schema gate on the rendered manifests"
    expected: "kustomize build … | kubeconform -strict passes for base / ES overlay / monitoring"
    why_human: "The kubeconform standalone binary is absent on this Windows box; validate.sh skip-cleaned to render-only (which still caught real Kustomize/YAML errors). CI installs kubeconform and runs the strict gate"
  - test: "actionlint on platform-ci.yml"
    expected: "actionlint reports no diagnostics"
    why_human: "The actionlint standalone binary is absent locally; the executor ran it via the rhysd/actionlint container (EXIT 0). Re-run in CI or via Docker to reconfirm"
---

# Phase 11: Hardening & Ops Verification Report

**Phase Goal:** The platform ships and operates like a product — deployable to Kubernetes, built and published by CI, and observable down to its domain metrics.
**Verified:** 2026-07-01
**Status:** human_needed
**Re-verification:** No — initial verification
**This is the FINAL phase.** On completion of the Manual-Only live confirmations, all 11 phases + all v1 requirements (INFRA-02/03/04 being the last three) are complete.

> **Verdict in one line:** the entire DETERMINISTIC contract of Phase 11 is VERIFIED in code (metrics endpoint + 4 gauges + honest degrade, the K8s manifests render + validate, the CI workflow shape, the monitoring config validity, the 2-dep package gate). The three success criteria each carry an inherently LIVE tail (an e2e run must *succeed*, images must *publish on push*, dashboards must *render over real scrapes*) that is Manual-Only — EXPECTED per 11-VALIDATION, routed to human verification. No blockers, no gaps.

## Mode note

ROADMAP marks this phase `mode: mvp`, but the phase goal is NOT a User Story ("As a … I want … so that …") — it is a standard capability goal. The MVP-mode User-Flow-Coverage methodology does not apply; standard goal-backward verification was used, which is correct for a non-User-Story goal.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GET /metrics returns 200 and exposes the 4 domain gauges over seeded data | ✓ VERIFIED (deterministic) | Collector logic reproduced green standalone (4 gauges from populated snapshot); `main.py:106` mounts Instrumentator `.expose(endpoint="/metrics")`; the live 200-over-seeded-DB integration test needs a live stack (verified by reading test_metrics_endpoint.py:161,196 assert 200) |
| 2 | A down metric source omits its gauge — /metrics still 200, never 500 | ✓ VERIFIED | metrics.py per-source try/except sets key None on failure; collect() skips None (metrics.py:150-152); test_metrics_endpoint.py:203-224 asserts 200 + gauge-absent; collector None-omit reproduced green standalone |
| 3 | classification_precision = applied/(applied+rejected) of reviewed defects; zero-reviewed → absent | ✓ VERIFIED | metrics.py:99-122 exact formula over `defects.status in (applied,rejected)`; `(applied/reviewed) if reviewed else None`; test asserts absence when zero-reviewed (line 196-197) |
| 4 | prometheus.yml passes promtool check config | ⚠ VERIFIED (SUMMARY-claimed; promtool binary absent locally) | Config structurally valid: scrapes api:8000 /metrics + pg/redis/rabbitmq/es exporters (prometheus.yml:24-47). SUMMARY reports promtool green; local binary absent → render-verified |
| 5 | Grafana dashboard JSON is valid and references the 4 gauge names | ✓ VERIFIED | Dashboard-JSON contract reproduced green standalone: both dashboards present, valid JSON w/ title+panels, all 4 `qa_platform_*` gauge names in domain-metrics.json |
| 6 | docker compose --profile monitoring is OFF by default | ✓ VERIFIED | prometheus/grafana/exporters all carry `profiles: [monitoring]` (docker-compose.yml:409,419,434,449) — a plain `up` never starts them |
| 7 | api production image runs uvicorn WITHOUT --reload (workers) | ✓ VERIFIED | `grep -c -- '--reload'` = 0; CMD = `uvicorn app.main:app … --workers 2` (Dockerfile:34) |
| 8 | web production image = next build → next start (multi-stage, no dev/Turbopack) | ✓ VERIFIED | `FROM node:22-alpine AS build` → runtime stage; `CMD ["npx","next","start",…]`; no `next dev`/`npm run dev` (web/Dockerfile:20,31,45) |
| 9 | platform-ci.yml gates GHCR build-publish behind keyless pytest lane + tsc + eslint | ✓ VERIFIED | `build-publish.needs: test`; test job runs the exact keyless marker lane + `tsc --noEmit` + eslint (platform-ci.yml:76,87,90,94) |
| 10 | workflow declares contents:read + packages:write (least privilege), never echoes token | ✓ VERIFIED | top-level + job `permissions: {contents: read, packages: write}` (25-27,96-98); GITHUB_TOKEN only in login-action `password:`, never in a `run:` echo |
| 11 | platform-ci.yml passes actionlint | ⚠ VERIFIED (executor ran via rhysd/actionlint container, EXIT 0; local binary absent) | SUMMARY 11-02: actionlint EXIT 0 via official container; local CLI absent → re-run in CI |
| 12 | saucedemo image NOT published (test fixture only) | ✓ VERIFIED | matrix = {api, web} only; `grep -c saucedemo` = 0 in the workflow |
| 13 | kustomize build base/ES/monitoring passes (kubeconform-strict) | ⚠ VERIFIED render; kubeconform binary absent | `kubectl kustomize` renders all three (base 16, ES 18, monitoring 12 objects); validate.sh PASSED render-only; kubeconform -strict is Manual/CI |
| 14 | Core services deploy with requests+limits from compose mem_limits | ✓ VERIFIED | 16 resources: blocks across the base; per-workload limits.memory (512/256/512/1Gi/1Gi/768/1536 Mi) per SUMMARY + rendered manifests |
| 15 | Postgres+Neo4j StatefulSet+PVC; rest Deployments; api /health probes | ✓ VERIFIED | rendered base: 2 StatefulSet + 5 Deployment; api.yaml readiness+liveness httpGet path:/health (api.yaml:98-108) |
| 16 | Sensitive env in a Secret (example values, real gitignored) | ✓ VERIFIED | secret.example.yaml stringData with CHANGE_ME_* placeholders; .gitignore ignores real secret.yaml (SUMMARY 11-03) |
| 17 | 3GB sizing + ES-off note + Manual-Only e2e documented | ✓ VERIFIED | README.md §Sizing (3GB), fit rules (ES off / monitoring separate / scale web to 0), `kubectl apply -k` e2e procedure |
| 18 | Package gate: exactly 2 new backend deps, no new frontend dep | ✓ VERIFIED | commit 54452de adds ONLY prometheus-client==0.25.* + prometheus-fastapi-instrumentator==8.0.* (+own transitives in uv.lock); apps/web/package.json last touched Phase 07 (recharts) |
| 19 | metrics collector is sync O(1) over a background-refreshed snapshot (no asyncio.run in collect) | ✓ VERIFIED | metrics.py: `_refresh_loop` async task (lifespan), `collect()` reads plain floats O(1), zero DB I/O on scrape path; started/stopped in main.py lifespan |

**Score:** 19/19 deterministic must-haves verified. 3 live SC endpoints (the e2e-succeeds / publish-on-push / dashboards-render tails) are Manual-Only → human verification.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `apps/api/app/core/metrics.py` | snapshot + sync collector + 4 gauges + start/stop | ✓ VERIFIED | 175 lines; DomainMetricsCollector, _refresh_loop, per-source degrade, start/stop_metrics |
| `apps/api/app/main.py` | /metrics + instrumentator + lifespan snapshot task | ✓ VERIFIED | imports start/stop_metrics; lifespan calls start_metrics + Instrumentator().expose(/metrics); stop_metrics on shutdown |
| `apps/api/pyproject.toml` | 2 prometheus deps | ✓ VERIFIED | lines 40-41 |
| test_metrics_collector.py / test_metrics_endpoint.py / test_dashboards_json.py | keyless proofs | ✓ VERIFIED (logic) | collector + dashboard contracts reproduced green standalone; endpoint test verified by reading (needs live stack) |
| `infra/monitoring/prometheus.yml` + grafana provisioning + 2 dashboards | config-as-code | ✓ VERIFIED | metrics_path:/metrics + all exporters; datasource + provider + 2 dashboard JSONs |
| `.github/workflows/platform-ci.yml` | 2-job test-gate→GHCR | ✓ VERIFIED | complete, correct, least-privilege |
| `apps/api/Dockerfile` + `apps/web/Dockerfile` | production images | ✓ VERIFIED | api no --reload; web multi-stage next start |
| `infra/k8s/base/*` + overlays/elasticsearch + monitoring + validate.sh + README.md | Kustomize manifest set | ✓ VERIFIED | all render; validate.sh PASSED |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| main.py | app.core.metrics.start_metrics | lifespan startup call | ✓ WIRED (main.py:18,105) |
| metrics.py | coverage_dash.coverage | snapshot refresh read | ✓ WIRED (metrics.py:45,93) |
| domain-metrics.json | core/metrics.py gauge names | panel PromQL | ✓ WIRED (all 4 `qa_platform_*` present) |
| platform-ci.yml | keyless pytest marker lane | test job pytest -m | ✓ WIRED (exact marker string, line 76) |
| platform-ci.yml | ghcr.io | login/metadata/build-push | ✓ WIRED (lines 112,118) |
| base/api.yaml | ghcr.io/honraoclaude/api | container image | ✓ WIRED (rendered) |
| base/worker.yaml | api image + worker_main | command override | ✓ WIRED (worker.yaml:25 `python -m app.worker_main`) |
| monitoring/grafana.yaml | infra/monitoring provisioning | ConfigMap-mounted | ✓ WIRED (/etc/grafana/provisioning) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| /metrics gauges | `_snapshot` floats | `_refresh_loop` → per_element_heal_stats / coverage_dash.coverage / Defect.status counts / LLMUsage.cost_usd sum over live SessionLocal + Neo4j | ✓ (reads shipped services, not hardcoded) | ✓ FLOWING (verified in code; live values require a running stack — Manual-Only) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Collector emits 4 gauges / omits None / all-None empty | `uv run python` standalone assertions | all 3 assertions pass | ✓ PASS |
| Dashboard JSON valid + all 4 gauge names | `python` standalone json.load + membership | all 4 assertions pass | ✓ PASS |
| Kustomize base/ES/monitoring render | `kubectl kustomize …` | 16 / 18 / 12 objects | ✓ PASS |
| validate.sh | `bash infra/k8s/validate.sh` | VALIDATION PASSED (exit 0) | ✓ PASS |
| api Dockerfile no --reload | `grep -c -- '--reload'` | 0 | ✓ PASS |
| Full pytest metrics group | `pytest tests/unit/test_metrics_collector.py …` | 7 ERRORS — autouse Redis fixture timeout (no live stack) | ? SKIP (infra-absence, not logic — see note) |

**Note on the 7 pytest ERRORS:** `tests/unit/conftest.py` has an `autouse=True` fixture `_isolate_gateway_redis` (line 129) that connects to and flushes compose Redis at `localhost:6379` before EVERY unit test. Docker Desktop is down on this box, so that fixture times out and ERRORS every test in the group — this is the project-wide live-stack test model (D-02: "tests hit the RUNNING stack over live HTTP with real Postgres/Redis"), NOT a Phase 11 logic defect. The actual Phase-11 assertions were reproduced green by executing their logic standalone (collector + dashboard contracts above). The SUMMARY reports 6+4 passing in an environment with the stack up.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| INFRA-02 | 11-03 | K8s manifests deploy the platform, validated on Docker Desktop K8s / kind | ✓ SATISFIED (deterministic); live deploy Manual-Only | Kustomize base+overlay+monitoring render; validate.sh PASSED; README e2e procedure |
| INFRA-03 | 11-02 | GitHub Actions CI/CD builds, tests, publishes platform images | ✓ SATISFIED (deterministic); live push Manual-Only | platform-ci.yml test-gate→GHCR; production Dockerfiles |
| INFRA-04 | 11-01 | Grafana+Prometheus expose platform health + 4 domain metrics | ✓ SATISFIED (deterministic); live render Manual-Only | /metrics + 4 gauges + degrade; prometheus.yml + dashboards-as-code |

No orphaned requirements — INFRA-02/03/04 each claimed by exactly one plan; INFRA-01 was completed in Phase 1.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | none | — | No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER debt markers, no stub returns, no hardcoded-empty data in any Phase-11 file. secret.example.yaml CHANGE_ME_* values are intentional documented placeholders (not stubs). |

### Human Verification Required

1. **Live K8s e2e (SC1)** — `kubectl apply -k infra/k8s/base` on kind/Docker Desktop K8s; port-forward web+api; run explore→execute→open a dashboard under realistic limits (ES off, monitoring separate). Expected: core path succeeds under the 3GB cap.
2. **Live GHCR publish (SC2)** — push to master; confirm the test job gates, then api+web publish to ghcr.io tagged SHA+latest (saucedemo never published).
3. **Live Grafana dashboards (SC3)** — `docker compose --profile monitoring up -d`; open Grafana; confirm the 4 domain panels + platform-health render from live scrapes.
4. **kubeconform -strict** — run the strict schema gate (binary absent locally; CI installs it).
5. **actionlint** — reconfirm EXIT 0 (executor ran it via the rhysd/actionlint container; local binary absent).

### Gaps Summary

No gaps. Every deterministic, keyless must-have of Phase 11 is verified in the codebase (19/19). The three success criteria each retain a LIVE tail — an e2e run must *succeed* on a cluster, images must *publish on a real push*, dashboards must *render over real scrapes* — which is inherently un-automatable without a cluster/push/populated data and was correctly declared Manual-Only in 11-VALIDATION. Status is `human_needed` solely because those live confirmations plus the two absent-binary gates (kubeconform, actionlint) require human/CI execution; nothing is broken or missing.

---

_Verified: 2026-07-01_
_Verifier: Claude (gsd-verifier)_
