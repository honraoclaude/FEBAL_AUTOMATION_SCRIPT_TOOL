---
phase: 04-explorer-agent
verified: 2026-06-15T18:40:00Z
status: human_needed
score: 5/5 success criteria implemented + deterministically verified; 1 Manual-Only live proof pending provider keys
overrides_applied: 0
re_verification:
  previous_status: none
---

# Phase 4 — Explorer Agent — Verification

**Goal:** "User points the platform at a registered app and it autonomously maps pages, workflows, and elements — converging, staying safe, on budget — with a live progress view."

**Verdict: human_needed.** Every success criterion's implementing code exists and is genuinely tested (not hollow). The full deterministic contract is green WITHOUT provider keys. The ONE remaining item is the integrated **live LLM-driven exploration of real SauceDemo**, which is the documented Manual-Only item because provider keys are intentionally empty in `.env` — its absence is expected, not a code gap.

## Evidence (run by the orchestrator)

- **Backend deterministic suite:** `cd apps/api && uv run pytest -m "not live_llm and not graph" -q` → **201 passed, 10 deselected** (after fixing a real defect — see below).
- **Frontend:** `npx tsc --noEmit` clean; `npx playwright test tests/e2e/explore-live.spec.ts` → **1 passed** (connecting → running → refused → terminal render from a mocked SSE stream); **zero** new shadcn ui components added (`git diff` over apps/web/components/ui/ empty across the phase).

## Success criteria

| SC | Requirement(s) | Implementation | Automated proof | Status |
|----|----------------|----------------|-----------------|--------|
| SC1 | EXPL-01 live view | SSE route (EventSourceResponse, auth-gated, Redis pub/sub, unsubscribe in finally, snapshot on resubscribe); ExploreProgressEvent (11 fields); live page (9 states, 200-row cap, reconnect reconcile, a11y); auth-gated traversal-safe screenshot route; cooperative Stop | functional SSE (in-order + 401) + screenshot (200/401/traversal) + mocked-SSE e2e | ✅ deterministic; live stream demo = manual |
| SC2 | EXPL-02 auth | login-form detection, credential injection via the single decrypt surface, storageState reuse, logout/relogin recovery | unit-tested (detection/logic) | ✅ logic; live login = manual |
| SC3 | EXPL-03/05/06 discovery + convergence + fingerprint dedup | LangGraph loop (perceive aria_snapshot → gateway-index decide → act → Neo4j execute_write+read-back), pure tunable structural fingerprint, code-enforced budgets + loop detector + saturation | **deterministic two-run convergence proof** (mocked gateway + fixtures → run 2 adds ~0 new states, stop_reason=saturation) + fingerprint unit tests | ✅ logic proven w/o keys; live two-run SauceDemo = manual |
| SC4 | EXPL-04 workflow + validation | Workflow→STEP→Page chain + Form.validation_rules (validation submit gated by the risk classifier) | unit-tested | ✅ |
| SC5 | EXPL-07/08/09 safety + locators | **code-enforced** risk classifier (deny-list + safe-verb default, sandbox-lifted, evaluated in the act node BEFORE the action — NOT LLM judgment), origin allowlist, untrusted-content delimiting, prioritized locator chain (data-testid→aria-label→role→text→xpath) + history | 34 risk/safety + 8 locator unit tests; risk.py confirmed pure (no llm/playwright/db) | ✅ fully verified w/o keys |

## Carried invariants (all hold)

- **LangGraph raw StateGraph** (NOT create_agent) — confirmed in graph.py (the only `create_agent` token is a docstring negation).
- **H-1: browser handle OUTSIDE checkpointed state** — ExplorerState docstring "NO browser handle is ever stored here"; the live handle lives in a per-run registry; the serialization-invariant unit test passes (the checkpointer serializer raises on a non-serializable handle).
- **H-2: frontier advancement** — enumerate/converge push unvisited in-origin targets; navigate pops; the discovery test asserts ≥2 distinct Page fingerprints + ≥1 NavigatesTo edge.
- **AsyncPostgresSaver `.setup()` at startup, NOT Alembic** — migration 0005 is APP tables only (its docstring explicitly states the checkpoint tables are owned by setup()); 0 checkpoint create_table in alembic.
- **Gateway-only LLM** — explorer's only init_chat_model reference is a comment; the real call is llm_gateway.complete(operation_type, run_id).
- **Neo4j writes** — managed execute_write + read-back guard (SC1 lesson) + parameterized Cypher.
- **Zero new shadcn.**

## Defect found and fixed during verification

- **pytest basename collision (real, blocking the whole suite):** 04-04 created `tests/functional/test_explore_events.py` alongside `tests/unit/test_explore_events.py`; with no package `__init__.py`, pytest collects by basename and errored on the duplicate, halting collection. Fixed by renaming the functional one to `test_explore_sse.py` (commit on master). The full deterministic suite (201) only passes after this fix — the executor's per-file runs masked it.

## Human-needed item (expected, non-blocking for the build)

The **integrated live LLM-driven exploration** — a real model choosing actions to autonomously map SauceDemo, converging on two consecutive real runs, with screenshots streaming live in the browser — has NOT been run because `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` are intentionally empty in `.env`. This is the documented Manual-Only verification (04-VALIDATION.md). The agent loop is proven to run end-to-end through login→navigate→perceive→enumerate (slice 1) and fails only at the real gateway decide call (auth, not a code defect).

**To close it:** set a provider key in `.env`, then:
```
python infra/scripts/graph_mode.py up
cd apps/api && uv run pytest -m "graph and live_llm" tests/functional/test_explore_discovery.py -x
# and open the live view in the browser during a real POST /explore to watch SSE
python infra/scripts/graph_mode.py down   # then stop neo4j if it lingers
```
Also worth a `docker stats` memory check (api + neo4j + Chromium + LangGraph under the 3GB WSL cap) during that live run.

---
*Phase: 04-explorer-agent*
*Verified (deterministic): 2026-06-15 — live LLM exploration is the pending Manual-Only gate*
