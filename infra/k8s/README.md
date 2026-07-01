# Kubernetes manifests — Autonomous QA Engineer Platform (INFRA-02)

A Kustomize manifest set that deploys the platform on **Docker Desktop Kubernetes** or
**kind** under realistic resource limits. It is a mechanical translation of
`infra/docker-compose.yml` (RESEARCH Pattern 3): the compose service names ARE the
in-cluster Service DNS names, so every in-cluster URL (`bolt://neo4j:7687`,
`redis://redis:6379/0`, `amqp://…@rabbitmq:5672/`, …) carries over verbatim.

```
infra/k8s/
├── base/                     # the 7 CORE workloads — the SC1 e2e set (always-on)
│   ├── namespace.yaml        # Namespace: qa-platform
│   ├── configmap.yaml        # NON-secret env (in-cluster URLs/hosts/flags)
│   ├── secret.example.yaml   # Secret with PLACEHOLDER values (real values gitignored)
│   ├── postgres.yaml         # StatefulSet + PVC + Service
│   ├── neo4j.yaml            # StatefulSet + PVC + Service (CORE — D-01, not a profile)
│   ├── redis.yaml            # Deployment + Service
│   ├── rabbitmq.yaml         # Deployment + Service (exposes 5672 AND 15692 metrics)
│   ├── api.yaml              # Deployment + Service (GHCR image, /health probes, /metrics)
│   ├── worker.yaml           # Deployment (no Service) — reuses the api image + worker_main
│   ├── web.yaml              # Deployment + Service (GHCR prod image, next start)
│   └── kustomization.yaml
├── overlays/elasticsearch/   # OPTIONAL ES search tier (layers on top of base)
│   ├── elasticsearch.yaml
│   └── kustomization.yaml    # resources: [../../base] + elasticsearch.yaml
├── monitoring/               # SEPARATE group — Prometheus + Grafana + exporters (D-04)
│   ├── prometheus.yaml       # Deployment + Service + scrape-config ConfigMap
│   ├── grafana.yaml          # Deployment + Service + datasource/provider ConfigMaps
│   ├── exporters.yaml        # postgres-exporter + redis-exporter (no Neo4j, no RabbitMQ)
│   ├── dashboards/*.json     # mirror of the Plan-01 dashboards-as-code (drift-checked)
│   └── kustomization.yaml
├── validate.sh               # keyless render + kubeconform -strict gate (skip-cleans)
└── README.md
```

## Keyless validation (no cluster, no credentials)

Every group renders offline and is schema-checked BEFORE any apply — malformed manifests
are caught here, never apply-to-discover-errors (T-11-12):

```bash
bash infra/k8s/validate.sh
```

`validate.sh` renders `base`, `overlays/elasticsearch`, and `monitoring`, diffs the
Grafana dashboard mirrors against their Plan-01 source, and — when `kubeconform` is
present — runs `kubeconform -strict`. If neither `kustomize` nor `kubectl kustomize` is
on PATH, or `kubeconform` is absent, it **skip-cleans** (exit 0) with a clear message:
this dev box may lack the standalone CLIs; CI installs them and runs the real gate.

Render a single group directly (kubectl bundles kustomize v5, so no standalone install
is needed for a quick check):

```bash
kubectl kustomize infra/k8s/base                 # 16 objects
kubectl kustomize infra/k8s/overlays/elasticsearch  # 18 objects (base + ES)
kubectl kustomize infra/k8s/monitoring           # 12 objects
```

## Sizing — the 3GB cap (RESEARCH Pitfall 4)

Docker Desktop K8s / kind on this Windows box runs under a **~3GB** memory envelope, so
the base + ES overlay + monitoring **cannot all fit at once**. The CORE set alone fits ≈
the same envelope as the already-validated compose `graph_mode` (~2.9GB):

| Service  | `resources.limits.memory` | Notes |
|----------|---------------------------|-------|
| postgres | 512Mi | StatefulSet + PVC |
| redis    | 256Mi | |
| rabbitmq | 512Mi | exposes 15692 (metrics) + 5672 (AMQP) |
| neo4j    | 1Gi   | StatefulSet + PVC; heap 512 + pagecache 256 |
| api      | 1Gi   | GHCR image, /health probes |
| worker   | 768Mi | reuses the api image (worker_main) |
| web      | 1536Mi | the heaviest — **scale to 0 during explore** (see the lever below) |

Each workload sets `resources.requests` (~50–70% of the limit) **and** `limits` from the
compose `mem_limit`, so the deploy cannot OOM the node when the fit rules below are honored
(T-11-11).

**Fit rules for the e2e (3GB):**
1. **ES overlay OFF** — apply `infra/k8s/base` only, NOT the ES overlay. Search
   graceful-degrades (the AsyncElasticsearch client opens lazily; a search query 503s
   honestly), so the base alone is a complete, runnable platform.
2. **Monitoring as a SEPARATE step** — do NOT deploy `infra/k8s/monitoring` during the
   core explore→execute→dashboard run. Layer it on afterward only if the node has headroom.
3. **Scale-web-to-0 during explore** — `web` is the heaviest workload. During the
   memory-heavy explore phase, scale it to 0 and back to 1 for the dashboard step (the
   Phase-3 `graph_mode` precedent that stops web before the memory-heavy work):
   ```bash
   kubectl -n qa-platform scale deploy/web --replicas=0   # before explore
   kubectl -n qa-platform scale deploy/web --replicas=1   # before the dashboard step
   ```

## Secrets (T-11-10 / Security V14)

Sensitive env lives in a **Secret**, never a ConfigMap and never inline in a Deployment.
Only `secret.example.yaml` (PLACEHOLDER values) is committed. For a real deploy:

```bash
cp infra/k8s/base/secret.example.yaml infra/k8s/base/secret.yaml   # gitignored
# edit secret.yaml — replace every CHANGE_ME_* value with a real secret, then:
kubectl apply -n qa-platform -f infra/k8s/base/secret.yaml
```

`secret.yaml` and `secret.*.local.yaml` are gitignored (see the repo `.gitignore`). NEVER
bake real secrets into a committed manifest or an image.

## Manual-Only end-to-end deploy (needs a cluster + a provider key)

The keyless validation above is automated; the LIVE deploy + explore→execute→dashboard
run is **Manual-Only** — it needs a running cluster, populated data, and a provider key
for the autonomous explore step. Recorded in `11-VALIDATION`.

```bash
# 1. A cluster: either enable Docker Desktop Kubernetes, or:
kind create cluster --name qa-platform

# 2. Deploy the CORE set (ES overlay OFF, monitoring separate — the 3GB fit rules).
kubectl apply -k infra/k8s/base
# (for a real deploy, apply your local secret.yaml too — see Secrets above)
kubectl -n qa-platform get pods -w        # wait for Ready

# 3. Reach the UI + API from the host.
kubectl -n qa-platform port-forward svc/web 3000:3000 &
kubectl -n qa-platform port-forward svc/api 8000:8000 &

# 4. The e2e under realistic limits (scale web to 0 during explore for the 3GB fit):
#    - open http://localhost:3000, sign in
#    - kick off an EXPLORE run against a target URL (needs a provider key set in the Secret)
#    - kick off an EXECUTE run of a generated suite
#    - open a dashboard and confirm results render
#    This exercises the core path (api + worker + postgres + neo4j + rabbitmq + redis + web).

# 5. OPTIONALLY, only if the node has headroom, layer monitoring and open Grafana:
kubectl apply -k infra/k8s/monitoring
kubectl -n qa-platform port-forward svc/grafana 3001:3000 &
#    open http://localhost:3001 — the Prometheus datasource + the 2 dashboards
#    (platform-health, domain-metrics) provision automatically (D-04, no clicking).

# 6. Teardown.
kubectl delete -k infra/k8s/monitoring   # if applied
kubectl delete -k infra/k8s/base
kind delete cluster --name qa-platform   # if you used kind
```

> **Note:** the explore step needs a provider key (Anthropic or OpenAI) set in the Secret,
> so the full live e2e is Manual-Only (a project-wide constraint — keyless lanes cannot
> run autonomous discovery). The ES overlay (`kubectl apply -k infra/k8s/overlays/elasticsearch`)
> and monitoring are each an additional memory tier — deploy them one at a time, not all at
> once, under the 3GB cap.
