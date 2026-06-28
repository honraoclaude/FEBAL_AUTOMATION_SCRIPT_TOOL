---
phase: 10
slug: dashboards-rbac-coverage-traceability
status: draft
nyquist_compliant: false
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
| **Frontend command** | `cd apps/web && npx tsc --noEmit && npx eslint "app/(dashboard)/dashboard" <touched> && npx playwright test tests/e2e/dashboards.spec.ts` (path QUOTED — parens break POSIX sh) |
| **Estimated runtime** | ~4-6 min (the live-ES round-trip + graph-marked joins add wall time; the rest is fast unit/contract) |

---

## Sampling Rate

- **After every task commit:** `cd apps/api && uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional and not search" -q`
- **After every plan wave:** full suite — bring ES up under `profiles:[search]` for the search round-trip; neo4j up (graph_mode) for graph-marked coverage/traceability; mind the 3GB cap (ES ~1.5GB + neo4j ~1.1GB cannot both run with the full app — sequence: run graph-marked tests under graph_mode, then search-marked under the search profile, not simultaneously)
- **Before `/gsd:verify-work`:** full deterministic + contract suite green; require_role 403 matrix green; coverage/traceability correct on fixtures + live KG; ES search round-trip green under the search profile + graceful-degrade (honest "search unavailable") when ES is down; the 3 dashboards + traceability viewer + search UI render to the UI-SPEC (e2e mocked)
- **Max feedback latency:** ~6 min

---

## Per-Task Verification Map

> Populated by the planner. Each task maps to PLAT-04 / DASH-01..06, a test type (unit deterministic
> on fixtures / FakeElasticsearch contract / graph+search-profile functional / e2e mocked /
> live-data-manual), a threat ref, and a keyless command. require_role gating, the coverage formula,
> the traceability join, the ES index/search contract (fake client), and the dashboard queries are ALL
> deterministic WITHOUT keys/live-ES; the live-ES round-trip is `search`-profile-gated; live-data
> realism (dashboards over a real explored+executed dataset) is the only Manual-Only slice.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | PLAT-04, DASH-01..06 | — | populated by planner | — | — | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] elasticsearch 9.4.x added to apps/api/pyproject.toml + `uv sync` (the ONE expected new BACKEND dep; gated checkpoint:human-verify; client major MUST match the ES server 9.x)
- [ ] `ELASTICSEARCH_URL` added to core/config.py Settings (RESEARCH gap 2); the compose `elasticsearch` block gets `xpack.security.enabled=false` (+ ssl/enrollment off) so the async client connects over plain HTTP (RESEARCH gap 1)
- [ ] A `role` enum column on User + migration 0010 (chains after 0009; ADMIN_EMAIL seed → Admin) + the require_role(*roles) dependency + the static role→permission map
- [ ] A FakeAsyncElasticsearch in-memory double (index/search/highlight/bulk) so the ES contract is keyless-CI-testable; live ES is `search`-profile-gated
- [ ] Seed/fixture data (flows + approved scenarios + passing/failing executions + classifications/defects) for the coverage formula, the traceability join, and the dashboard-aggregation queries — keyless
- [ ] Existing functional infra (authed_client, the exec-history query style, kg/reader, the neo4j-down→503 graceful-degrade handler, graph_mode) carries forward

*Existing infrastructure (get_current_user + the router-gate pattern, exec_history queries, kg/reader, the neo4j ServiceUnavailable→503 handler, recharts/react-query/react-table) covers most of the phase; elasticsearch + the role column + the FakeElasticsearch double + the compose-security fix are the new Wave-0 pieces.*

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (elasticsearch dep, ELASTICSEARCH_URL + compose-security, role column + migration 0010, FakeElasticsearch, seed fixtures)
- [ ] No watch-mode flags
- [ ] Feedback latency < 6 min
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
