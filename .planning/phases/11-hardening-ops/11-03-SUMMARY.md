---
phase: 11-hardening-ops
plan: 03
subsystem: infra-k8s
tags: [kubernetes, kustomize, manifests, deployment, monitoring, prometheus, grafana, exporters, sizing, INFRA-02]
requirements-completed: [INFRA-02]
dependency-graph:
  requires: ["11-01 (prometheus.yml + Grafana provisioning ConfigMap-mounted)", "11-02 (GHCR api/web production images referenced by the manifests)"]
  provides: ["Kustomize base (7 core workloads)", "ES overlay", "monitoring manifest group", "validate.sh keyless render+kubeconform gate", "K8s README with 3GB sizing + Manual-Only e2e"]
  affects: ["deployment/ops — the platform now deploys on Docker Desktop K8s / kind"]
tech-stack:
  added: []
  patterns: ["mechanical compose->K8s translation (RESEARCH Pattern 3)", "in-tree configMapGenerator dashboards (load-restrictor-safe)", "keyless kustomize-build|kubeconform validation gate", "separate off-by-default monitoring manifest group (D-04 analog of the compose profile)"]
key-files:
  created: ["infra/k8s/base/*.yaml (11)", "infra/k8s/overlays/elasticsearch/*.yaml (2)", "infra/k8s/monitoring/*.yaml (4)", "infra/k8s/monitoring/dashboards/*.json (2)", "infra/k8s/validate.sh", "infra/k8s/README.md"]
  modified: [".gitignore"]
decisions: ["dashboard JSONs mirrored INTO infra/k8s/monitoring/dashboards so bare `kubectl apply -k` works with no --load-restrictor flag; validate.sh drift-checks against the Plan-01 canonical source", "validate.sh uses K8S_GROUPS not GROUPS (GROUPS is a bash built-in array — the user's GIDs — silently overrides an assignment)"]
metrics:
  duration: ~30min
  tasks: 2
  files: 22
completed: 2026-07-01
---

# Phase 11 Plan 03: Kubernetes Manifests — Kustomize base + ES overlay + monitoring + validate.sh + sizing README Summary

**A Kustomize manifest set that deploys the platform on Docker Desktop K8s / kind: a `base` of the 7 core workloads (Postgres+Neo4j as StatefulSet+PVC, Redis/RabbitMQ/api/worker/web as Deployments, the GHCR prod images from Plan 02, api /health probes, sensitive env in a Secret with placeholder values), an optional Elasticsearch overlay, and a SEPARATE off-by-default monitoring group (Prometheus+Grafana+postgres/redis exporters, ConfigMap-mounting the Plan-01 dashboards-as-code). A keyless `validate.sh` renders all three groups and runs kubeconform -strict (skip-cleaning when the CLIs are absent), and `README.md` documents the 3GB sizing math + the ES-off/monitoring-separate/scale-web-to-0 fit rules + the Manual-Only `kubectl apply -k` explore→execute→dashboard e2e. INFRA-02.**

## Performance
- **Completed:** 2026-07-01
- **Tasks:** 2
- **Files:** 22 (21 created, 1 modified)
- **Note:** Resumed a session-limited prior executor — Task 1's manifests were written + staged but uncommitted; this session committed them, then executed Task 2.

## Accomplishments

- **Task 1 — Kustomize base + ES overlay (`a78a9f0`):** committed the prior executor's staged, orchestrator-validated manifests. `infra/k8s/base`: `namespace.yaml` (qa-platform), `configmap.yaml` (non-secret in-cluster URLs/hosts/flags — the compose service names ARE the in-cluster Service DNS, so `bolt://neo4j:7687` / `redis://redis:6379/0` / `amqp://…@rabbitmq:5672/` carry over verbatim per RESEARCH Pitfall 6), `secret.example.yaml` (a Secret with PLACEHOLDER values — T-11-10), and the 7 workloads. Postgres + Neo4j → StatefulSet + volumeClaimTemplates + Service; Redis/RabbitMQ/api/worker/web → Deployment (worker no Service — it is a consumer). Each workload carries `resources.limits.memory` from the compose `mem_limit` (512/256/512/1Gi/1Gi/768/1536 Mi) + requests at ~50-70%. api uses the GHCR image `ghcr.io/honraoclaude/api:latest` with httpGet `/health` readiness+liveness; worker reuses that image with `command: ["python","-m","app.worker_main"]`; web uses `ghcr.io/honraoclaude/web:latest`. Neo4j carries the double-underscore `NEO4J_server_memory_heap_max__size` env; rabbitmq exposes 15692 (metrics) + 5672. ES overlay: `resources: [../../base]` + `elasticsearch.yaml` (Deployment+Service, 1536Mi, discovery.type single-node, xpack.security off) — OFF for the SC1 e2e (D-01). `.gitignore` ignores real `secret.yaml` / `secret.*.local.yaml` (only `secret.example.yaml` is committed).

- **Task 2 — monitoring manifests + validate.sh + README (`31c5080`):** `infra/k8s/monitoring` is a SEPARATE off-by-default group (the K8s analog of the compose `monitoring` profile — D-04), kept apart from the base so it is not deployed during the 3GB-constrained e2e. `prometheus.yaml`: Deployment + Service (9090) + a ConfigMap holding the SAME scrape config as the Plan-01 `infra/monitoring/prometheus.yml` (targets api:8000/metrics, postgres-exporter:9187, redis-exporter:9121, rabbitmq:15692, elasticsearch-exporter:9114) mounted at `/etc/prometheus/prometheus.yml`. `grafana.yaml`: Deployment + Service (3000) + datasource/provider ConfigMaps + a `configMapGenerator` for the 2 dashboards, all mounted under `/etc/grafana/provisioning` — provisions with no manual clicking (D-04); the Grafana admin password comes from the Secret (`ADMIN_PASSWORD`). `exporters.yaml`: postgres-exporter (quay.io/prometheuscommunity/postgres-exporter, creds from the Secret/ConfigMap, :9187) + redis-exporter (oliver006/redis_exporter, REDIS_ADDR redis://redis:6379, :9121) — NO Neo4j exporter (Enterprise-only, CLAUDE.md — graph metrics via the app collector) and NO RabbitMQ exporter (built-in plugin). `validate.sh`: renders base + ES overlay + monitoring (prefers standalone `kustomize`, falls back to `kubectl kustomize`), diffs the dashboard mirrors against the Plan-01 source, and runs `kubeconform -strict` when present — skip-cleans (exit 0) with a clear message when the CLIs are absent (this Windows box lacks them; CI installs them). `README.md`: the per-service sizing table + the "core set ≈ the validated compose graph_mode ~2.9GB" note + the ES-off / monitoring-separate / scale-web-to-0-during-explore fit rules + Secret handling + the Manual-Only `kubectl apply -k` explore→execute→dashboard e2e procedure.

## Verification Results
- Keyless render (kubectl bundles kustomize v5 — standalone kustomize/kubeconform absent on this box): `kubectl kustomize infra/k8s/base` = **16 objects**, `…/overlays/elasticsearch` = **18**, `…/monitoring` = **12** (4 ConfigMap + 4 Deployment + 4 Service). The monitoring `grafana-dashboards` ConfigMap renders with no hash suffix (matches the volume ref).
- `bash infra/k8s/validate.sh` → **VALIDATION PASSED** (exit 0): renderer=`kubectl kustomize`, render-only note for the absent kubeconform, dashboard mirrors in sync, all three groups OK (16/18/12).
- Plan Task-2 grep gates: `grep -q '3GB' infra/k8s/README.md` ✓, `grep -q 'kubectl apply -k' infra/k8s/README.md` ✓.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] Dashboard configMapGenerator sources moved in-tree (Kustomize load-restrictor)**
- **Found during:** Task 2
- **Issue:** The plan implied the Grafana dashboards ConfigMap should mount the Plan-01 `infra/monitoring/grafana/provisioning/dashboards/*.json`. Kustomize's default load restrictor FORBIDS `configMapGenerator` file sources outside the kustomization root, so `kubectl kustomize infra/k8s/monitoring` errored ("file … is not in or below …/monitoring"). Requiring `--load-restrictor LoadRestrictionsNone` on every `kubectl apply -k` is a UX footgun and breaks the plan's bare `kustomize build` verify commands.
- **Fix:** Mirrored the 2 dashboard JSONs into `infra/k8s/monitoring/dashboards/` (byte-identical to the Plan-01 canonical source) and pointed the generator at the in-tree copies — so bare `kubectl apply -k` / `kustomize build` works with zero flags. `validate.sh` diffs the mirrors against the canonical source to catch drift (D-04 single-source-of-truth preserved).
- **Files modified:** infra/k8s/monitoring/kustomization.yaml, infra/k8s/monitoring/dashboards/*.json
- **Commit:** 31c5080

**2. [Rule 1 - Bug] validate.sh iterated over the wrong list (`GROUPS` is a bash built-in)**
- **Found during:** Task 2 (validate.sh authoring)
- **Issue:** The script's group list was named `GROUPS`, which is a bash BUILT-IN array holding the caller's group IDs. Assigning to it is silently ignored, so `for grp in $GROUPS` iterated over the GID `197609` and the script rendered a non-existent directory and failed.
- **Fix:** Renamed the variable to `K8S_GROUPS` (a plain space-separated list, not an array — `"${arr[@]}"` also mis-expands under `set -u` in Git-Bash). validate.sh then rendered all three groups and passed.
- **Files modified:** infra/k8s/validate.sh
- **Commit:** 31c5080

## Threat surface
No new surface beyond the plan's `<threat_model>`. The mitigations are implemented as specified: sensitive env in a Secret with placeholder values (T-11-10), requests+limits on every workload + the documented 3GB fit (T-11-11), the `kustomize build | kubeconform -strict` gate in validate.sh (T-11-12), the GHCR images + official upstream exporters (T-11-14). `/metrics` in-cluster exposure remains `accept` (T-11-13, no Ingress/TLS in scope).

## Manual-Only
- The LIVE deploy + explore→execute→dashboard e2e on kind / Docker-Desktop-K8s is Manual-Only: it needs a running cluster, populated data, and a provider key (ANTHROPIC_API_KEY / OPENAI_API_KEY) for the autonomous explore step. The full procedure (with the ES-off / monitoring-separate / scale-web-to-0 fit rules) is documented in `infra/k8s/README.md` and recorded for 11-VALIDATION.
- `kubeconform -strict` was NOT run here — this Windows box lacks the standalone CLI; validate.sh skip-cleaned to render-only (which still caught the Kustomize/YAML errors above). CI (which installs kustomize + kubeconform) runs the full strict schema gate.

## Self-Check: PASSED
- All 22 files on disk; the 11 base + 2 ES overlay + 4 monitoring manifests + 2 dashboard mirrors + validate.sh + README.
- Commits present: `a78a9f0` (Task 1), `31c5080` (Task 2).
- `bash infra/k8s/validate.sh` → VALIDATION PASSED (base 16 / ES 18 / monitoring 12).

---
*Phase: 11-hardening-ops*
*Completed: 2026-07-01*
