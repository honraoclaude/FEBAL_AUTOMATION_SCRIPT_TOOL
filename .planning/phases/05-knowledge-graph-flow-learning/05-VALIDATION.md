---
phase: 5
slug: knowledge-graph-flow-learning
status: draft
nyquist_compliant: false
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
| **Quick run command** | `cd apps/api && uv run pytest -m "not live_llm and not graph" -q` (pure logic: risk formula, coverage metric, path-mining, single-write-path grep — no keys, no neo4j) |
| **Full suite command** | `cd apps/api && uv run pytest -m "not live_llm" -q` (adds graph-marked writer/MERGE/freshness/idempotency + read-API functional under graph_mode: neo4j up, web down) |
| **Frontend command** | `cd apps/web && npx tsc --noEmit && npx eslint <touched> && npx playwright test tests/e2e/kg-browse.spec.ts` |
| **Estimated runtime** | ~2-3 min |

---

## Sampling Rate

- **After every task commit:** `cd apps/api && uv run pytest -m "not live_llm and not graph" -q`
- **After every plan wave:** full suite under graph_mode (`python infra/scripts/graph_mode.py up` first; stop neo4j + restore web after)
- **Before `/gsd:verify-work`:** full suite green; idempotency re-run proof green; coverage-metric unit test green; live ≥80% coverage + live flow categorization demonstrated with provider keys
- **Max feedback latency:** ~3 min

---

## Per-Task Verification Map

> Populated by the planner against the PLAN.md tasks. Each maps to KG-01..05/QUAL-01, a test type
> (unit deterministic / graph functional under graph_mode / live_llm-manual), and a command. The
> idempotent MERGE/freshness, risk formula, coverage metric, path-mining, and single-write-path
> enforcement are ALL deterministically testable WITHOUT provider keys; LIVE flow categorization +
> the ≥80% coverage gate on a real discovered graph are the Manual-Only items.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _planner fills_ | | | KG-0x/QUAL-01 | | | unit/graph/live_llm | | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Fixture KG dataset (a small set of node/edge rows, JSON or Cypher seed) so writer MERGE/freshness, idempotency, path-mining, risk, and coverage are testable WITHOUT a live browser/LLM
- [ ] Committed ground-truth fixture (JSON) for SauceDemo pages + key flows (QUAL-01 reference)
- [ ] Idempotency re-run harness: run the writer twice over the same fixture node set; assert counts unchanged + last_verified bumped + first_seen immutable
- [ ] neo4j uniqueness constraint (REQUIRE fingerprint IS UNIQUE) created at writer/startup (NOT Alembic — Neo4j schema)
- [ ] graph_mode + neo4j_session fixture (carried from Phase 3/4) for graph-marked functional tests
- [ ] One-time DETACH DELETE / migration note for any pre-existing Phase-4 graph (MERGE key changes key→fingerprint)
- [ ] Mocked gateway fixture (carried from Phase 2) for flow-categorization-logic tests with the deterministic fallback (no keys)

*Existing functional infra (live-HTTP client, authed_client, poll_until_terminal, asyncio_mode=auto) carries forward.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live ≥80% coverage on a real discovered SauceDemo graph | QUAL-01 / SC5 | Needs a real exploration (provider keys) to populate the KG, then coverage vs the ground-truth fixture | Set keys, graph_mode up, run an exploration, GET /coverage → confirm ≥80% vs the committed ground truth |
| Live flow categorization (business-workflow names) | KG-04 | LLM names mined flows via the gateway (real spend) | Set keys, GET /flows after an exploration → confirm flows carry LLM-assigned business-workflow names (deterministic fallback names appear without keys) |
| Idempotent re-explore (~0 duplicates) on the LIVE graph | KG-03 | Needs two real explorations | Explore twice; confirm node counts ~unchanged + last_verified advanced (the deterministic fixture re-run proves the writer logic without keys) |
| Browse UI renders the live graph | KG-02 | Visual | Open the KG browse pages after an exploration; confirm Pages/Flows(risk)/Element Repository populate |

*Deterministic logic (writer MERGE/freshness, idempotency on fixtures, risk formula, coverage metric, path-mining, single-write-path grep, read-API shapes) is automated without keys.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (fixture KG, ground-truth fixture, idempotency harness, constraint, graph_mode, migration note)
- [ ] No watch-mode flags
- [ ] Feedback latency < 3 min
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
