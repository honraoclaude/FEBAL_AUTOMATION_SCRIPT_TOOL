---
phase: 5
slug: knowledge-graph-flow-learning
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-19
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (pytest-asyncio 1.4, asyncio_mode=auto) + pytest-playwright; frontend tsc/eslint/playwright |
| **Config file** | apps/api/pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd apps/api && uv run pytest -m "not live_llm and not graph and not e2e" -q` (pure logic: risk formula, coverage metric, path-mining, flow-categorize fallback, single-write-path grep — no keys, no neo4j) |
| **Full suite command** | `cd apps/api && uv run pytest -m "not live_llm" -q` (adds graph-marked writer/MERGE/freshness/idempotency + read-API functional under graph_mode: neo4j up, web down) |
| **Frontend command** | `cd apps/web && npx tsc --noEmit && npx eslint <touched> && npx playwright test tests/e2e/kg-browse.spec.ts` |
| **Estimated runtime** | ~2-3 min |

---

## Sampling Rate

- **After every task commit:** `cd apps/api && uv run pytest -m "not live_llm and not graph and not e2e" -q`
- **After every plan wave:** full suite under graph_mode (`python infra/scripts/graph_mode.py up` first; `docker compose stop neo4j` + restore web after)
- **Before `/gsd:verify-work`:** full suite green; idempotency re-run proof green; coverage-metric unit test green; live ≥80% coverage + live flow categorization demonstrated with provider keys
- **Max feedback latency:** ~3 min

---

## Per-Task Verification Map

> Each task maps to KG-01..05/QUAL-01, a test type (unit deterministic / graph functional under
> graph_mode / live_llm-manual), a threat ref, and a command. The idempotent MERGE/freshness, risk
> formula, coverage metric, path-mining, flow-categorize fallback, and single-write-path enforcement
> are ALL deterministically testable WITHOUT provider keys; LIVE flow categorization + the ≥80%
> coverage gate on a real discovered graph are the Manual-Only items.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| P1-T0 | 05-01 | 1 | KG-05 | T-05-02 | Zero write-Cypher outside writer/schema (grep) | unit (default) | `uv run pytest tests/unit/test_single_write_path.py -x` | ❌ W0 | ⬜ pending |
| P1-T0 | 05-01 | 1 | KG-03 | T-05-04 | Re-run → counts unchanged, first_seen immutable, last_verified bumped | graph | `uv run pytest -m graph tests/functional/test_kg_idempotency.py -x` | ❌ W0 | ⬜ pending |
| P1-T0 | 05-01 | 1 | KG-01 | T-05-01 | Canonical labels/edges (Button/BusinessEntity/Submits/Creates) created | graph | `uv run pytest -m graph tests/functional/test_kg_schema.py -x` | ❌ W0 | ⬜ pending |
| P1-T1 | 05-01 | 1 | KG-03/KG-01 | T-05-04/T-05-01 | Idempotent fingerprint-MERGE + freshness + uniqueness constraint (graceful boot) | graph | `uv run pytest -m graph tests/functional/test_kg_idempotency.py tests/functional/test_kg_schema.py -x` | ❌ W0 | ⬜ pending |
| P1-T2 | 05-01 | 1 | KG-05 | T-05-02 | Explorer delegates; constraints wired into lifespan | unit + default | `uv run pytest tests/unit/test_single_write_path.py -x && uv run pytest -m "not live_llm and not graph and not e2e" -q` | ❌ W0 | ⬜ pending |
| P2-T1 | 05-02 | 2 | KG-04 | T-05-06 | Pure deterministic risk_score clamped 0-100 + tiers | unit (no keys) | `uv run pytest tests/unit/test_risk.py -x -q` | ❌ W0 | ⬜ pending |
| P2-T2 | 05-02 | 2 | KG-04 | T-05-05/T-05-07/T-05-08 | Bounded path-mining; categorize via gateway (flow.categorize) + deterministic no-key fallback; untrusted fence | unit (no keys) | `uv run pytest tests/unit/test_flow_mining.py tests/unit/test_flow_categorize.py -x -q` | ❌ W0 | ⬜ pending |
| P2-T3 | 05-02 | 2 | KG-05 | T-05-08 | Element Repository returns chain + history per element (read-only, LIMIT) | graph | `uv run pytest -m graph tests/functional/test_element_repo.py -x` | ❌ W0 | ⬜ pending |
| P3-T1 | 05-03 | 3 | KG-02 | T-05-09 | Real /flows /coverage /graph /pages /elements read-only, auth-gated (401 unauth) | functional/graph | `uv run pytest -m graph tests/functional/test_kg_endpoints.py -x` | ❌ W0 | ⬜ pending |
| P3-T2 | 05-03 | 3 | KG-02 | T-05-10/T-05-11 | Browse UI Pages/Flows(risk badge)/Element Repo + drill-in + honest coverage; no XSS; zero new deps | e2e (web) | `cd apps/web && npx playwright test tests/e2e/kg-browse.spec.ts` | ❌ W0 | ⬜ pending |
| P4-T1 | 05-04 | 4 | QUAL-01 | T-05-13/T-05-14 | compute_coverage(fixture_GT, fixture_KG) → KNOWN %; fp-primary/url-fallback; honest empty | unit (no keys) | `uv run pytest tests/unit/test_coverage.py -x -q` | ❌ W0 | ⬜ pending |
| P4-T2 | 05-04 | 4 | QUAL-01 | T-05-14/T-05-15 | Real GET /coverage (measured flag, never fabricated); live ≥80% Manual-Only | functional/graph + live_llm-manual | `uv run pytest -m graph tests/functional/test_kg_endpoints.py -x` / `-m "graph and live_llm" tests/functional/test_coverage_live.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Fixture KG dataset (`tests/fixtures/kg/pages.json`) so writer MERGE/freshness, idempotency, path-mining, risk, and coverage are testable WITHOUT a live browser/LLM (plan 05-01 Task 0)
- [ ] Committed ground-truth fixture (`tests/fixtures/ground_truth/saucedemo.json`) for SauceDemo pages + key flows (QUAL-01 reference; plan 05-04 Task 1)
- [ ] Idempotency re-run harness (`tests/functional/test_kg_idempotency.py`): run the writer twice over the same fixture node set; assert counts unchanged + last_verified bumped + first_seen immutable (plan 05-01)
- [ ] neo4j uniqueness constraint (REQUIRE fingerprint IS UNIQUE) created at startup via `kg/schema.ensure_constraints` (NOT Alembic — Neo4j schema; graceful when neo4j down) (plan 05-01)
- [ ] graph_mode + `neo4j_session` fixture (carried from Phase 3/4) for graph-marked functional tests
- [ ] One-time DETACH DELETE / migration note for any pre-existing Phase-4 graph (MERGE key changes key→fingerprint) — the idempotency/schema tests clear the graph in setup; documented in plan 05-01 Task 0
- [ ] Mocked gateway fixture (`fake_gateway`, carried from Phase 2) for flow-categorization-logic tests with the deterministic fallback (no keys) (plan 05-02)
- [ ] Grep enforcement test (`tests/unit/test_single_write_path.py`) — created RED in 05-01 Task 0, turns GREEN at 05-01 Task 2

*Existing functional infra (live-HTTP client, authed_client, poll_until_terminal, asyncio_mode=auto) carries forward.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live ≥80% coverage on a real discovered SauceDemo graph | QUAL-01 / SC5 | Needs a real exploration (provider keys) to populate the KG, then coverage vs the ground-truth fixture | Set keys, graph_mode up, run an exploration, `GET /coverage` → confirm ≥80% vs the committed ground truth; or `uv run pytest -m "graph and live_llm" tests/functional/test_coverage_live.py` |
| Live flow categorization (business-workflow names) | KG-04 | LLM names mined flows via the gateway (real spend) | Set keys, `GET /flows` after an exploration → confirm flows carry LLM-assigned business-workflow names (deterministic fallback names appear without keys) |
| Idempotent re-explore (~0 duplicates) on the LIVE graph | KG-03 | Needs two real explorations | Explore twice; confirm node counts ~unchanged + last_verified advanced (the deterministic fixture re-run proves the writer logic without keys) |
| Browse UI renders the live graph | KG-02 | Visual | Open the KG browse pages after an exploration; confirm Pages/Flows(risk)/Element Repository populate |

*Deterministic logic (writer MERGE/freshness, idempotency on fixtures, risk formula, coverage metric, path-mining, flow-categorize fallback, single-write-path grep, read-API shapes) is automated without keys.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (fixture KG, ground-truth fixture, idempotency harness, constraint, graph_mode, migration note, grep test)
- [x] No watch-mode flags
- [x] Feedback latency < 3 min
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planner-filled (pending checker)
