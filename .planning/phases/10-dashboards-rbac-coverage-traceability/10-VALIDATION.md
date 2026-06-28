---
phase: 10
slug: dashboards-rbac-coverage-traceability
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-28
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (pytest-asyncio 1.4, asyncio_mode=auto) + pytest-playwright; frontend tsc/eslint/playwright. Invoke as `uv run python -m pytest` (Windows AppControl blocks the `pytest.exe` shim — os error 4551). |
| **Config file** | apps/api/pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd apps/api && uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional and not search" -q` (require_role gating + role→permission map, the graph-derived coverage formula on fixtures, the cross-store traceability join on fixtures, the ES index/search contract against a FAKE AsyncElasticsearch, the dashboard aggregation queries on seeded rows — keyless, no neo4j, no live ES) |
| **Full suite command** | `cd apps/api && uv run python -m pytest -m "not live_llm" -q` (adds graph-marked coverage/traceability over the live KG + the `search`-profile-gated live Elasticsearch round-trip) |
| **Frontend command** | `cd apps/web && npx tsc --noEmit && npx eslint "app/(dashboard)/dashboards" "app/(dashboard)/coverage" "app/(dashboard)/traceability" "app/(dashboard)/search" "app/(dashboard)/admin" && npx playwright test tests/e2e/dashboards.spec.ts tests/e2e/coverage-traceability-search.spec.ts tests/e2e/admin-users.spec.ts` (paths QUOTED — parens break POSIX sh) |
| **Estimated runtime** | ~4-6 min (the live-ES round-trip + graph-marked joins add wall time; the rest is fast unit/contract) |

---

## Sampling Rate

- **After every task commit:** `cd apps/api && uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional and not search" -q` (backend) / `cd apps/web && npx tsc --noEmit` (frontend)
- **After every plan wave:** full suite — bring ES up under `profiles:[search]` for the search round-trip; neo4j up (graph_mode) for graph-marked coverage/traceability; mind the 3GB cap (ES ~1.5GB + neo4j ~1.1GB cannot both run with the full app — sequence: run graph-marked tests under graph_mode, then search-marked under the search profile, not simultaneously)
- **Before `/gsd:verify-work`:** full deterministic + contract suite green; require_role 403 matrix green; coverage/traceability correct on fixtures + live KG; ES search round-trip green under the search profile + graceful-degrade (honest "search unavailable") when ES is down; the 3 dashboards + coverage panel + traceability viewer + search UI + admin users render to the UI-SPEC (e2e mocked)
- **Max feedback latency:** ~6 min

---

## Per-Task Verification Map

> Each task maps to PLAT-04 / DASH-01..06, a test type (unit deterministic on fixtures /
> FakeElasticsearch contract / graph+search-profile functional / e2e mocked / live-data-manual),
> a threat ref, and a keyless command. require_role gating, the coverage formula, the traceability
> join, the ES index/search contract (fake client), and the dashboard queries are ALL deterministic
> WITHOUT keys/live-ES; the live-ES round-trip is `search`-profile-gated; live-data realism
> (dashboards over a real explored+executed dataset) is the only Manual-Only slice.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01 T1 | 10-01 | 1 | PLAT-04 | T-10-05 | reversible migration 0010; admin row gets role; role NOT in JWT | integration (deterministic) | `uv run python -m pytest tests/integration/test_migration_0010.py -x -q` | ❌ W0 | ⬜ pending |
| 10-01 T2 | 10-01 | 1 | PLAT-04 | T-10-03, T-10-04 | require_role 403s a disallowed role, reads role off the row; static map | unit (deterministic) | `uv run python -m pytest tests/unit/test_require_role.py tests/unit/test_rbac_map.py -x -q` | ❌ W0 | ⬜ pending |
| 10-01 T3 | 10-01 | 1 | PLAT-04 | T-10-01, T-10-02 | admin-only role assign; non-admin 403; self-demote 400; invalid role 422 | integration (deterministic) | `uv run python -m pytest tests/integration/test_role_assign.py -x -q` | ❌ W0 | ⬜ pending |
| 10-02 T1 | 10-02 | 2 | DASH-04 | T-10-11 | graph-derived coverage (approved AND passing); honest definition; distinct from kg/coverage.py | unit (fixture) | `uv run python -m pytest tests/unit/test_coverage_dash.py -x -q` | ❌ W0 | ⬜ pending |
| 10-02 T2 | 10-02 | 2 | DASH-01, DASH-02, DASH-03 | T-10-09 | exec/qa/dev aggregates on seeded rows; run-relative artifact refs | integration (fixture) | `uv run python -m pytest tests/integration/test_dashboards.py::test_dashboards_aggregates -x -q` | ❌ W0 | ⬜ pending |
| 10-02 T3 | 10-02 | 2 | DASH-01, DASH-02, DASH-03, PLAT-04 | T-10-07, T-10-08, T-10-10 | dashboard/coverage 403 role matrix; unauth 401; graph-down honest | integration (fixture) | `uv run python -m pytest tests/integration/test_dashboards.py -x -q` | ❌ W0 | ⬜ pending |
| 10-03 T1 | 10-03 | 3 | DASH-05 | T-10-13, T-10-15 | chain from each entry id; honest gaps; NO graph writes (single-write-path green) | integration (fixture) | `uv run python -m pytest tests/integration/test_traceability.py::test_chain_from_each_entry_id -x -q` | ❌ W0 | ⬜ pending |
| 10-03 T2 | 10-03 | 3 | DASH-05, PLAT-04 | T-10-12, T-10-14, T-10-16 | role-gated; exactly one entry id (422); unknown id → honest empty | integration (fixture) | `uv run python -m pytest tests/integration/test_traceability.py -x -q` | ❌ W0 | ⬜ pending |
| 10-04 CP | 10-04 | 4 | DASH-06 | T-10-SC | elasticsearch install gated behind blocking human-verify (client major == server 9.x) | checkpoint:human-verify | (manual approval — pypi.org/project/elasticsearch + 9.x match) | n/a | ⬜ pending |
| 10-04 T1 | 10-04 | 4 | DASH-06 | T-10-20, T-10-22 | gated dep; lazy es_client + 503 handler; xpack-disable; FakeAsyncElasticsearch | smoke (deterministic import) | `uv run python -c "from app.core.es_client import init_es,get_es,close_es; from tests.fixtures.fake_es import FakeAsyncElasticsearch; print('ok')"` | ❌ W0 | ⬜ pending |
| 10-04 T2 | 10-04 | 4 | DASH-06 | T-10-19, T-10-21 | on-write index swallows ES failure (PG write unbroken); backfill; ensure-mappings graceful | unit (FakeElasticsearch contract) | `uv run python -m pytest tests/unit/test_search_contract.py -k "index or backfill or swallow" -x -q` | ❌ W0 | ⬜ pending |
| 10-04 T3 | 10-04 | 4 | DASH-06, PLAT-04 | T-10-17, T-10-18, T-10-20 | parameterized multi_match + highlight; role-gated; ES-down → honest 503 | unit + integration (FakeElasticsearch) | `uv run python -m pytest tests/unit/test_search_contract.py tests/integration/test_search_degrade.py -x -q` | ❌ W0 | ⬜ pending |
| 10-04 T3 (live) | 10-04 | 4 | DASH-06 | T-10-20 | live ES index→search round-trip | functional (search profile) | `docker compose --profile search up -d --wait elasticsearch && uv run python -m pytest -m search tests/functional/test_search_live.py -q` | ❌ W0 | ⬜ pending |
| 10-05 T1 | 10-05 | 5 | PLAT-04 | T-10-23 | role-filtered nav off /me; role badge; lib/rbac.ts mirrors API matrix | type-check | `cd apps/web && npx tsc --noEmit` | ❌ W0 | ⬜ pending |
| 10-05 T2 | 10-05 | 5 | DASH-01, DASH-02, DASH-03 | T-10-25 | dashboards zod client + accessible meter (server bands) + recharts (no new dep) | type-check | `cd apps/web && npx tsc --noEmit` | ❌ W0 | ⬜ pending |
| 10-05 T3 | 10-05 | 5 | DASH-01, DASH-02, DASH-03, PLAT-04 | T-10-24, T-10-26 | 3 dashboards all states; auth-gated artifact URLs (no raw paths); no-access; 2-coverage split | e2e (mocked API) | `cd apps/web && npx tsc --noEmit && npx playwright test tests/e2e/dashboards.spec.ts` | ❌ W0 | ⬜ pending |
| 10-06 T1 | 10-06 | 6 | DASH-04, DASH-05 | T-10-30, T-10-31 | coverage % + honest definition + per-flow + separate ground-truth; chain with honest gaps | type-check | `cd apps/web && npx tsc --noEmit` | ❌ W0 | ⬜ pending |
| 10-06 T2 | 10-06 | 6 | DASH-06 | T-10-29, T-10-30 | typed highlighted hits; honest "search unavailable" 503 distinct from no-results | type-check | `cd apps/web && npx tsc --noEmit` | ❌ W0 | ⬜ pending |
| 10-06 T3 | 10-06 | 6 | PLAT-04, DASH-04, DASH-05, DASH-06 | T-10-27, T-10-28 | admin role assign UI + self-demote guard + confirm + success-only toast; 4-surface e2e | e2e (mocked API) | `cd apps/web && npx tsc --noEmit && npx playwright test tests/e2e/coverage-traceability-search.spec.ts tests/e2e/admin-users.spec.ts` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] elasticsearch 9.4.x added to apps/api/pyproject.toml + `uv sync` (the ONE expected new BACKEND dep; gated checkpoint:human-verify in 10-04; client major MUST match the ES server 9.x)
- [ ] `ELASTICSEARCH_URL` added to core/config.py Settings (RESEARCH gap 2); the compose `elasticsearch` block gets `xpack.security.enabled=false` (+ ssl/enrollment off) so the async client connects over plain HTTP (RESEARCH gap 1) — 10-04 T1
- [ ] A `role` enum column on User + migration 0010 (chains after 0009; ADMIN_EMAIL seed → Admin) + the require_role(*roles) dependency + the static role→permission map — 10-01
- [ ] A FakeAsyncElasticsearch in-memory double (index/search/highlight/bulk) so the ES contract is keyless-CI-testable; live ES is `search`-profile-gated — 10-04 T1
- [ ] Seed/fixture data (flows + approved scenarios + passing/failing executions + classifications/defects) for the coverage formula, the traceability join, and the dashboard-aggregation queries — keyless (10-02/10-03 tests own their seed fixtures)
- [ ] Existing functional infra (authed_client, the exec-history query style, kg/reader, the neo4j-down→503 graceful-degrade handler, graph_mode) carries forward

*Existing infrastructure (get_current_user + the router-gate pattern, exec_history queries, kg/reader, the neo4j ServiceUnavailable→503 handler, recharts/react-query/the vendored shadcn table) covers most of the phase; elasticsearch + the role column + the FakeElasticsearch double + the compose-security fix are the new Wave-0 pieces. Wave-0 scaffolding (the missing test files + the role column + the ES dep + the fake double) is created inside the first task that needs each, per the Nyquist rule — there is no separate Wave-0 plan; each test file named in the Per-Task map above is authored RED-first within its task.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dashboards/coverage/traceability over a REAL explored+executed dataset | DASH-01..05 | Realism needs a live explore→generate→execute→classify run (provider keys) to populate non-fixture data | With keys, run the full pipeline against SauceDemo; open each dashboard + the coverage panel + the traceability viewer and confirm the numbers/chains match the real runs |
| Live Elasticsearch search at scale | DASH-06 | A real ES instance under the search profile (memory-heavy) | `docker compose --profile search up -d --wait elasticsearch`; backfill-reindex; search executions/failures/logs; confirm results + ranking; stop ES → confirm honest "search unavailable" |
| 3GB memory fit with ES up | (infra) | host Vmmem observation | `docker stats` with the search profile up (ES ~1.5GB); confirm sequencing keeps the box under the cap (ES and neo4j not both up with the full app) |

*Deterministic logic (require_role gating, the coverage formula, the traceability join, the ES index/search contract via FakeElasticsearch, the dashboard queries) is automated WITHOUT keys or a live ES.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (the one checkpoint:human-verify in 10-04 is the gated dep install per D-04; every code task carries an automated command)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (elasticsearch dep, ELASTICSEARCH_URL + compose-security, role column + migration 0010, FakeElasticsearch, seed fixtures)
- [x] No watch-mode flags
- [x] Feedback latency < 6 min
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-28 (planner — Per-Task map populated across the 6 plans; nyquist compliant)
