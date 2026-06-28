# Phase 10: Dashboards, RBAC & Coverage/Traceability - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning (needs --research-phase — the elasticsearch 9.4 client index/search shapes + on-write dual-index wiring, the cross-store traceability join, the graph-derived coverage query, and the dashboard aggregation queries have no canonical reference)

<domain>
## Phase Boundary

Every role sees the truth of the system, gated by permissions. Three role-scoped dashboards — Executive (coverage, pass rate, defect counts, trends), QA (execution history, failed tests, screenshots, videos), Developer (root-cause groupings, error trends, module failure breakdowns) — render the EXISTING Phase-4..9 data. An Admin assigns one of four roles (Admin / QA Lead / QA Engineer / Developer) that gate API endpoints AND dashboard views. A graph-derived coverage engine reports the % of discovered flows covered by approved scenarios AND passing executions, with the honest definition displayed. A traceability engine answers the flow↔scenario↔script↔execution↔defect chain for any artifact. Search across executions, failures, and logs is served by Elasticsearch. Delivers PLAT-04 + DASH-01..06. UI hint: yes — this IS the dashboards phase (3 dashboards + traceability viewer + search UI + role-gated nav); a UI-SPEC is REQUIRED at plan-phase (no deferral).

**In scope:** the 4-role RBAC (role enum on User + admin role-assignment API + require_role API gating + role-gated dashboard views) (PLAT-04); the Executive/QA/Developer dashboards over existing data via recharts (DASH-01/02/03); the graph-derived coverage engine + honest-definition display (DASH-04); the cross-store traceability engine + viewer (DASH-05); Elasticsearch on-write dual-index + backfill reindexer + search API/UI, graceful-degrade when ES is down (DASH-06).
**Out of scope (own phases):** K8s manifests + CI/CD for platform images + Prometheus/Grafana platform metrics (Phase 11 — this phase emits app-level dashboards/metrics-as-data, NOT the ops observability stack); the upstream engines themselves (explore/generate/execute/heal/classify — Phase 4-9, reused as data sources, not rebuilt); bi-directional Jira sync (out of v1). No NEW domain capability — this phase VISUALIZES + GATES + SEARCHES what Phases 4-9 already produce.

</domain>

<decisions>
## Implementation Decisions

### RBAC model & enforcement (PLAT-04)
- **D-01:** A `role` enum column on the User model (Admin / QA Lead / QA Engineer / Developer) via a migration; the Phase-1 ADMIN_EMAIL seed defaults to Admin. An admin-only API assigns roles (`POST /users/{id}/role`-style). The JWT carries the role; `/me` returns it. A `require_role(*roles)` FastAPI dependency (built on the existing get_current_user) gates endpoints → 403 on mismatch. The frontend gates dashboard nav + views off the role from `/me`. A STATIC role→permission map (NOT a permissions table): Admin = all; QA Lead = manage suites/scenarios + all dashboards; QA Engineer = run executions + QA dashboard; Developer = read + Developer dashboard. (Research: the exact endpoint→role matrix across the existing routers; how require_role composes with the existing auth dependency.)

### Coverage definition (DASH-04)
- **D-02:** A discovered flow counts as COVERED iff it has ≥1 approved scenario AND ≥1 passing execution. coverage % = covered flows / total discovered flows — GRAPH-DERIVED (kg/reader flows joined with Postgres approved scenarios + execution results). The exact definition is DISPLAYED in the UI (honest). This is the NEW DASH-04 metric; the Phase-5 ground-truth coverage (% discovered vs a committed ground-truth fixture) STAYS as a SEPARATE exploration-completeness number — the two are distinct and both shown with their definitions. (Research: the join query across Neo4j flows + scenarios.status='approved' + execution_history passing results; per-flow drill-down.)

### Traceability architecture (DASH-05)
- **D-03:** A CROSS-STORE JOIN service assembles the flow↔scenario↔script↔execution↔defect chain on READ, keyed by ANY artifact id, by joining Neo4j (flows, via kg/reader) + Postgres (scenarios, generated scripts, executions/test_results, defects — already FK-linked by run_id/flow_id + jira_key from Phase 9). NO new graph writes — Neo4j stays the discovered-structure graph (the single-writer discipline holds); relational lifecycle data is NOT coupled into the KG. Keyless, deterministic, fixture-testable. (Research: the chain assembly + the "any artifact" entry points (flow_id / scenario_id / run_id / defect_id) + the response shape the viewer renders.)

### Elasticsearch search (DASH-06)
- **D-04:** ON-WRITE DUAL-INDEX + a backfill reindexer. Executions / failures / logs are indexed into ES as they are written (a thin `es.index(...)` alongside the Postgres write) PLUS a backfill/reindex command for existing rows. The elasticsearch 9.4 client is a GATED new dependency (checkpoint:human-verify; client major MUST match the ES server 9.x — CLAUDE.md). Search is GRACEFUL-DEGRADE when ES is down (profiles:[search] off) — an honest "search unavailable" (mirroring the neo4j-down 503 pattern), never a crash. A search API + UI over the indices. (Research: the elasticsearch 9.4 AsyncElasticsearch index/search/bulk shapes; the index mappings for executions/failures/logs; how on-write indexing stays non-blocking + failure-tolerant; the structlog→ES log path.)

### Claude's Discretion / for research (--research-phase)
- The dashboard AGGREGATION queries (DASH-01/02/03): coverage/pass-rate/defect-count/trends (Exec), execution-history/failed-tests/screenshots/videos (QA), root-cause-groupings/error-trends/module-failure-breakdowns (Dev). Computed ON-READ from Postgres/Neo4j (live queries + TanStack Query, mirroring the Phase-7 execution-history queries) unless research shows a materialization need. "Root-cause groupings" = grouping by the Phase-9 classification + fingerprint; "module failure breakdowns" = by flow/page.
- The require_role endpoint→role matrix across all existing routers; admin role-assignment API + a minimal admin role UI vs API-only.
- The ES index mappings + the on-write hook points + the backfill command + the search-result ranking/highlighting.
- The traceability response shape + the viewer interaction (pick an artifact → render the chain).
- Whether any new migration is needed (the role column at least → migration 0010, chains after 0009).
- The UI-SPEC: 3 role-scoped dashboards + the coverage panel (with honest definition) + the traceability viewer + the search UI + role-gated nav — recharts (installed) for charts, zero new frontend deps preferred.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — PLAT-04, DASH-01..DASH-06.
- `.planning/ROADMAP.md` (Phase 10 section) — the 5 success criteria.

### Locked stack & carried conventions
- `CLAUDE.md` — elasticsearch 9.4.x (AsyncElasticsearch; client major MUST match ES server 9.x — strict), recharts 3.8 (installed Phase 7; all dashboards), @tanstack/react-query (dashboard polling/caching), @tanstack/react-table (history/failure tables), PyJWT + `Depends(require_role(...))` per-route (CLAUDE.md's stated RBAC pattern — "no extra library needed for 4 static roles"), structlog (→ ES ingestion), SQLAlchemy/Alembic (role column + migration 0010). The dashboards reuse the locked design system (zero new shadcn / native-styled where unvendored, the Phase-6/7/9 precedent).

### Reusable seams (read the summaries + code)
- `apps/api/app/core/security.py` (get_current_user) + `apps/api/app/models/user.py` + `apps/api/app/routers/auth.py` + `.planning/phases/01-foundation-dev-environment/01-*-SUMMARY.md` — the auth seam require_role extends (no role exists yet).
- `apps/api/app/services/kg/reader.py` (flows, coverage inputs) + `apps/api/app/services/kg/coverage.py` (the Phase-5 GROUND-TRUTH coverage — DASH-04 is a SEPARATE graph-derived metric) + `.planning/phases/05-knowledge-graph-flow-learning/05-*-SUMMARY.md`.
- `apps/api/app/models/execution_history.py` + `apps/api/app/models/scenario.py` + `apps/api/app/models/defects.py` + `.planning/phases/06/07/09-*-SUMMARY.md` — the scenarios.status='approved', execution results, defect+jira_key+links = the coverage + traceability + dashboard sources.
- `apps/api/app/routers/executions.py` + `scenarios.py` + `defects.py` + `heals.py` — the auth-gated router + history-query patterns the dashboards/coverage/traceability/search routers mirror.
- `apps/web/app/(dashboard)/executions/` (recharts trend cards) + `scenarios/`/`defects/` (list+detail, TanStack Query) + `components/app-sidebar.tsx` (role-gated nav) + the Phase-7/9 UI-SPECs — the dashboard/viewer/search UI precedent + the locked design system.
- `infra/docker-compose.yml` (elasticsearch:9.4.1 under profiles:[search]; the neo4j profiles:[graph] graceful-degrade pattern) + `apps/api/app/core/logging.py` (structlog) — the ES integration + graceful-degrade + log-ingestion seams.

### Known issues / project-wide
- Empty provider keys do NOT gate this phase — dashboards, RBAC, coverage, traceability, and search are all deterministic + keyless once Phase-4..9 data exists (seed/fixture data drives the tests).
- 3GB WSL cap: elasticsearch:9.4.1 is mem-heavy (compose sets ES_JAVA_OPTS -Xms512m -Xmx1g, mem_limit 1536m) — like neo4j it cannot run alongside the full stack indefinitely; sequence ES tests under its profile, and graceful-degrade when off. Windows AppControl: tests run via `uv run python -m pytest`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- security.py get_current_user + user.py + auth.py — RBAC extends these (role column + require_role + JWT role claim).
- kg/reader (flows) + execution_history + scenario + defects models — coverage + traceability + dashboard data; the Phase-9 test↔flow↔execution↔defect FK links already exist.
- executions/scenarios/defects routers — the auth-gated router + aggregation-query pattern for the new dashboard/coverage/traceability/search routers.
- web executions (recharts) + scenarios/defects (list+detail, TanStack Query) + app-sidebar — the dashboard/viewer/search UI + role-gated nav.
- compose elasticsearch:9.4.1 (profiles:[search]) + the neo4j graceful-degrade-503 pattern + structlog — the ES integration + degrade + ingestion.
- Postgres models + Alembic chain (latest 0009) — the role column → migration 0010.

### Established Patterns
- Auth-gated routers + get_current_user; deterministic read-query services (kg/reader, exec-history) fixture-testable; graceful-degrade with honest 503/"unavailable" when a profile service is down (neo4j precedent → ES); recharts dashboards (Phase 7); honest server-authoritative UI states; gated new deps behind checkpoint:human-verify (aio-pika/recharts/atlassian-python-api precedent → elasticsearch); single-writer Neo4j (traceability does NOT add graph writes); migrations in apps/api/alembic/versions/; tests via `uv run python -m pytest`.
- Carry forward: honest definitions DISPLAYED (coverage); deterministic + keyless dashboards/search (data-driven, no LLM); zero new shadcn/frontend deps (recharts already present); graceful-degrade over crash.

### Integration Points
- A role column + migration 0010 + require_role DI + the admin role-assignment API + JWT role claim + frontend role-gated nav; coverage + traceability + dashboard-aggregation read services + their auth-gated routers; the ES client (gated dep) + on-write index hooks + backfill command + search API; 3 dashboard pages + a coverage panel + a traceability viewer + a search UI + the role-gated sidebar (a new UI-SPEC).

</code_context>

<specifics>
## Specific Ideas

- RBAC is the simplest thing that satisfies 4 fixed roles + a single operator: a role enum + a static permission map + require_role — NOT a permissions table (the spec says "4 roles", CLAUDE.md says no extra library needed).
- Coverage is HONEST: covered = approved-scenario AND passing-execution (a flow with an approved-but-failing test is NOT covered); the definition is shown on the dashboard; the Phase-5 ground-truth number stays separate so neither is conflated.
- Traceability is a read-time cross-store JOIN — it does NOT pollute the discovered-structure KG with relational lifecycle nodes (single-writer discipline preserved); the Phase-9 FK links make the join cheap.
- ES search graceful-degrades exactly like neo4j: profile off → honest "search unavailable", never a crash; on-write dual-index keeps results fresh, the backfill seeds existing data.

</specifics>

<deferred>
## Deferred Ideas

- K8s manifests + CI/CD for platform images + Prometheus/Grafana platform observability → Phase 11 (this phase ships app-level dashboards as DATA + the RBAC/coverage/traceability/search engines, not the ops stack).
- A granular permissions table / custom role creation → REJECTED for v1 (4 fixed roles + a static map; revisit only if roles become dynamic).
- Graph-native traceability (writing scenario/exec/defect into Neo4j) → REJECTED for v1 (cross-store join keeps the KG clean + the single-writer discipline; revisit if read-time joins become a bottleneck).
- Bi-directional Jira status sync into the dashboards → out of v1 scope.
- Real-time dashboard push (SSE/websocket live tiles) → not required (TanStack Query polling suffices; the live execution view already exists in Phase 7).

None of these block Phase 10 — discussion stayed within the dashboards/RBAC/coverage/traceability/search scope.

</deferred>

---

*Phase: 10-dashboards-rbac-coverage-traceability*
*Context gathered: 2026-06-28*
