---
phase: 05-knowledge-graph-flow-learning
verified: 2026-06-20T00:30:00Z
status: human_needed
score: 5/5 success criteria implemented + deterministically verified; 1 Manual-Only live proof pending provider keys
overrides_applied: 0
re_verification:
  previous_status: none
---

# Phase 5 — Knowledge Graph & Flow Learning — Verification

**Goal:** "Discovered structure becomes a queryable, idempotent, fresh knowledge graph that derives risk-scored business flows — measured against ground truth."

**Verdict: human_needed.** Every success criterion's implementing code exists and is genuinely tested (not hollow). The full deterministic contract is green WITHOUT provider keys. The remaining items are the LIVE LLM-driven proofs (live flow categorization names + the ≥80% coverage gate on a real discovered graph), which are the documented Manual-Only items because provider keys are intentionally empty in `.env`.

## Evidence (run by the orchestrator)

- **Deterministic suite:** `cd apps/api && uv run pytest -m "not live_llm and not graph and not e2e" -q` → **238 passed, 32 deselected** (risk formula, flow-mining, coverage metric known-%, single-write-path grep, etc. — no keys, no neo4j).
- **Graph suite under graph_mode (neo4j up, web down):** `uv run pytest -m graph -q` → **16 passed, 6 skipped** (writer MERGE/freshness/idempotency, schema, element-repo, kg endpoints incl. 401-unauth + coverage measured=true; the 6 skips are live_llm tests that skip cleanly without keys).
- **Coverage metric:** `test_coverage.py` → 9 passed (fixture KG vs fixture ground-truth → known % 6/7 = 85.7).
- **Frontend (05-03):** tsc + eslint clean; `kg-browse.spec.ts` 6 passed (mocked API). Zero new shadcn / zero new deps.
- **GET /coverage robustness:** returns a clean **503** "graph unavailable" when neo4j is down (was an unhandled 500 — fixed), and `measured=true` honest coverage under graph_mode.

## Success criteria

| SC | Requirement(s) | Implementation | Automated proof | Status |
|----|----------------|----------------|-----------------|--------|
| SC1 | KG-01 | kg/writer.py + kg/schema.py (Page/Form/Workflow/Button/Element/BusinessEntity + NavigatesTo/Submits/Creates/Updates/Deletes/HAS_*/STEP); /graph browse UI | schema graph test + kg-browse e2e | ✅ |
| SC2 | KG-03 | fingerprint-keyed MERGE, ON CREATE first_seen / ON MATCH last_verified, uniqueness constraint (lazy at startup, graceful when neo4j down), key→fingerprint migration | deterministic ~0-duplicate re-run proof under graph_mode (counts unchanged, first_seen immutable, last_verified bumped) | ✅ proven w/o keys |
| SC3 | KG-04 | bounded deterministic path-mining + pure risk formula (no neo4j/llm imports) + LLM categorization with deterministic no-key fallback; risk visible in Flows UI + Risk breakdown | risk + mining + categorize-fallback unit tests | ✅ logic; live semantic naming = manual |
| SC4 | KG-05 | single-writer kg/writer.py (Cypher lifted from explorer); test_single_write_path.py asserts zero write-Cypher outside writer/schema; Element Repository read (chain + history per element) | single-write-path grep + element-repo graph test | ✅ |
| SC5 | QUAL-01 | committed JSON ground-truth fixture (in-package + diffable copy, pinned in sync); pure coverage metric (fp-primary/url-fallback); GET /coverage honest measured=false when empty, never fabricated | coverage metric known-% unit test + endpoint test (measured under graph_mode) | ✅ metric proven w/o keys; live ≥80% = manual |

## Carried invariants (all hold)

- Single-writer enforced (grep test green; explorer persist node is a thin delegate).
- execute_write + read-back guard kept INSIDE the writer; parameterized Cypher only.
- Gateway-only LLM (flow categorization via llm_gateway.complete, deterministic fallback).
- Graceful-without-neo4j: lazy driver, graceful ensure_constraints, AND (fixed this verification) KG read endpoints now 503 instead of 500 when neo4j is down.
- Zero new packages; zero new shadcn in the browse UI.

## Defects found and fixed during verification

1. **GET /coverage 500 — fixture path (real, in-container):** 05-04 created the in-package ground-truth copy but `coverage.py` still pointed at the `.dockerignore`'d `tests/` path → FileNotFoundError 500. Fixed `_GROUND_TRUTH_PATH` to the in-package copy (commit on master).
2. **KG reads 500 when neo4j down (robustness, all endpoints):** unhandled `ServiceUnavailable`. Added an app-level handler → clean 503 "graph unavailable", consistent with the graceful-without-neo4j contract + the UI's graph-down state (commit on master).
3. **live_llm graph tests failed instead of skipping without keys (test hygiene):** test_explore.py::test_explore_writes_page_navigatesto_for_run_id (became LLM-driven in Phase 4) and test_generation.py end-to-end lacked the skipif-on-no-key guard. Added live_llm + skipif; graph suite is now clean (commit on master).

## Human-needed items (expected, non-blocking for the build)

These need a provider API key (`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`) + a live exploration — the documented Manual-Only verifications (05-VALIDATION.md):

- **Live ≥80% coverage (QUAL-01 / SC5):** set a key, `graph_mode up`, run an exploration of SauceDemo, `GET /coverage` → confirm ≥80% vs the committed ground truth (or `uv run pytest -m "graph and live_llm" tests/functional/test_coverage_live.py`).
- **Live flow categorization (KG-04):** after an exploration, `GET /flows` → confirm flows carry LLM-assigned business-workflow names (deterministic fallback names appear without keys).
- **Live idempotent re-explore (KG-03):** explore twice; confirm ~0 duplicate nodes + last_verified advanced (the deterministic fixture re-run already proves the writer logic without keys).

---
*Phase: 05-knowledge-graph-flow-learning*
*Verified (deterministic): 2026-06-20 — live LLM coverage/categorization are the pending Manual-Only gate*
