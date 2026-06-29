---
phase: 11-hardening-ops
plan: 01
subsystem: observability
tags: [prometheus, metrics, grafana, dashboards-as-code, custom-collector, background-snapshot, monitoring-profile, INFRA-04]
requirements-completed: [INFRA-04]
completed: 2026-06-29
---

# Phase 11 Plan 01: Observability — /metrics + domain gauges + monitoring config (INFRA-04)

**App-level Prometheus instrumentation: a background-refreshed cached snapshot feeds a sync custom Collector that emits the four domain gauges (heal success rate, classification precision, coverage %, LLM cost) at `/metrics`, plus prometheus-fastapi-instrumentator HTTP metrics — scrape-tolerant (a down source omits its gauge, /metrics still 200). Monitoring (Prometheus + Grafana) runs as a compose `monitoring` profile (off by default) with the datasource + dashboards provisioned as code. No Enterprise Neo4j endpoint.**

## Performance
- **Completed:** 2026-06-29
- **Tasks:** 3
- **Files:** ~12 (created + modified)

## Accomplishments
- **Gated deps (Task 1, `54452de`):** prometheus-client==0.25.* + prometheus-fastapi-instrumentator==8.0.* added to apps/api/pyproject.toml; `uv lock && uv sync` added ONLY those two + transitives (instrumentator 8.0.2 verified inside the uv venv). Human-verified install gate (blocking-human).
- **Collector + /metrics (Task 2, `63080cc` RED → `9fe4858` GREEN):** `apps/api/app/core/metrics.py` — a lifespan async task refreshes a cached snapshot (4 metrics → plain floats) every ~30s; a SYNC prometheus_client custom `Collector.collect()` reads the floats O(1) (NEVER asyncio.run() in collect()). The 4 gauges: `heal_success_rate` (healing/stats), `classification_precision` = applied/(applied+rejected) over reviewed `defects.status` (D-05; zero-reviewed → gauge ABSENT), `coverage_percent` (coverage_dash), `llm_cost_usd` (llm_usage). Per-source try/except → a down source omits its gauge, `/metrics` still 200 (mirrors the main.py degrade contract). `/metrics` + the instrumentator mounted in the FastAPI lifespan. App-level only (no Enterprise Neo4j Prometheus endpoint).
- **Monitoring config (Task 3, `2878e2b`):** infra/monitoring/prometheus.yml (scrapes the api `/metrics` + the postgres/redis/rabbitmq exporters) + grafana provisioning (datasource + dashboards provider + 2 dashboard JSONs: platform-health + the 4 domain metrics) + the compose `monitoring` profile (OFF by default — 3GB cap). Dashboards-as-code.

## Verification Results
- `tests/unit/test_metrics_collector.py` + `tests/integration/test_metrics_endpoint.py` → **6 passed** (the 4 gauges from seeded Postgres rows + the coverage source monkeypatched keyless like test_dashboards.py; a down-source → /metrics still 200 + that gauge absent).
- `tests/unit/test_dashboards_json.py` → 4 passed (dashboard JSON valid + all 4 gauge names referenced).
- `promtool check config` → prometheus.yml valid; `docker compose config` → monitoring profile OFF by default, ON with `--profile monitoring`.
- `git diff` deps → only the 2 gated prometheus packages added.

## Decisions / carries honored
- D-03 pull-on-scrape (background snapshot, no hot-path metric coupling); D-04 monitoring profile off-by-default + dashboards-as-code; D-05 precision = applied/(applied+rejected) over defects.status (zero-reviewed → absent). CHECKER LOW-1 honored: the metrics integration test monkeypatches coverage_dash.mine_flows_from_neo4j (keyless, no Neo4j) — the coverage gauge being absent in a Neo4j-less lane is correct degrade.

## Manual-Only
- Live Grafana rendering the 4 domain panels + platform-health over real scrapes needs `docker compose --profile monitoring up -d` + a populated platform (08-VALIDATION Manual-Only).

## Self-Check: PASSED
metrics.py on disk; the 2 deps in pyproject; 4 task commits (2878e2b/54452de/63080cc/9fe4858) present; 6 metrics tests + 4 dashboard-JSON tests green.

*Note: this SUMMARY + the STATE/ROADMAP/REQUIREMENTS closeout were written by the orchestrator — the executor's stream dropped after committing all 3 tasks (9fe4858) but before the metadata step. All production work was committed + independently re-verified (6 passed).*

---
*Phase: 11-hardening-ops*
*Completed: 2026-06-29*
