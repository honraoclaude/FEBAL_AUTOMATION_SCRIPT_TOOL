---
phase: 4
slug: explorer-agent
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-15
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (pytest-asyncio 1.4, asyncio_mode=auto) + pytest-playwright |
| **Config file** | apps/api/pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd apps/api && uv run pytest -m "not live_llm and not graph" -q` (pure logic: risk classifier, fingerprint, budget/loop/convergence, locator extraction, SSE event shapes — mocked gateway + fixture snapshots, zero spend) |
| **Full suite command** | `cd apps/api && uv run pytest -m "not live_llm" -q` (adds graph-marked functional under graph_mode: neo4j up, web down) |
| **Frontend command** | `cd apps/web && npx tsc --noEmit && npx eslint ... && npx playwright test tests/e2e/explore-live.spec.ts` |
| **Estimated runtime** | ~2-3 min (Playwright crawl + LangGraph loop add wall time) |

---

## Sampling Rate

- **After every task commit:** `cd apps/api && uv run pytest -m "not live_llm and not graph" -q`
- **After every plan wave:** full suite under graph_mode (`python infra/scripts/graph_mode.py up` first; stop neo4j + restore web after)
- **Before `/gsd:verify-work`:** full suite green; the convergence proof (two consecutive runs collapse to ~the same fingerprinted graph) passes deterministically on fixture snapshots; live exploration demonstrated with provider keys
- **Max feedback latency:** ~3 min

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| P01-T1 | 04-01 | 1 | (pkg gate) | T-04-SC | Package-legitimacy human-verify before uv add | checkpoint | (blocking-human) | ✅ existing audit | ⬜ pending |
| P01-T2 | 04-01 | 1 | EXPL-05 | T-04-03 | Code-enforced budget caps + loop detector (no spend tracking); checkpointer.setup() not Alembic | unit | `uv run pytest tests/unit/test_budget.py -q` | ❌ W0 | ⬜ pending |
| P01-T3 | 04-01 | 1 | EXPL-03, EXPL-05 | T-04-01,05 | aria_snapshot perceive; gateway-index decide; managed execute_write + read-back; param Cypher | graph + unit | `uv run pytest -m graph tests/functional/test_explore_discovery.py -x` | ❌ W0 | ⬜ pending |
| P02-T1 | 04-02 | 2 | EXPL-06 | T-04-09 | Pure tunable structural fingerprint; text/ids stripped | unit | `uv run pytest tests/unit/test_fingerprint.py -q` | ❌ W0 | ⬜ pending |
| P02-T2 | 04-02 | 2 | EXPL-05 | T-04-10 | Two-run convergence (mocked gateway, zero spend) → identical fp set + stop_reason=saturation | unit | `uv run pytest tests/unit/test_convergence.py -q` | ❌ W0 | ⬜ pending |
| P02-T3 | 04-02 | 2 | EXPL-02 | T-04-07,08 | Login heuristic; creds via single decrypt surface; storageState; relogin | unit | `uv run pytest tests/unit/test_auth_detect.py -q` | ❌ W0 | ⬜ pending |
| P03-T1 | 04-03 | 3 | EXPL-07, EXPL-08 | T-04-11,12,13 | Deterministic deny-list + origin allowlist before act; untrusted delimiting; injection defense-in-depth | unit | `uv run pytest tests/unit/test_risk.py tests/unit/test_safety.py -q` | ❌ W0 | ⬜ pending |
| P03-T2 | 04-03 | 3 | EXPL-09 | T-04-14,15 | Locator chain (data-test alias) + history; param Cypher Element write + read-back | unit | `uv run pytest tests/unit/test_locators.py -q` | ❌ W0 | ⬜ pending |
| P03-T3 | 04-03 | 3 | EXPL-04 | T-04-14,15 | Workflow/STEP chain + Form.validation_rules; validation submit gated by risk | unit | `uv run pytest tests/unit/test_workflow_detect.py -q` | ❌ W0 | ⬜ pending |
| P04-T1 | 04-04 | 4 | EXPL-01 | T-04-16,18 | ExploreProgressEvent; redis publish; auth-gated SSE; disconnect cleanup | unit + functional | `uv run pytest tests/unit/test_explore_events.py -q` + functional SSE | ❌ W0 | ⬜ pending |
| P04-T2 | 04-04 | 4 | EXPL-01 | T-04-17,20 | Live page 9 states; 200-row cap; reconnect reconcile; a11y; auto-escaped feed; zero new shadcn | e2e/typecheck | `npx tsc --noEmit && npx eslint ...` | ❌ W0 | ⬜ pending |
| P04-T3 | 04-04 | 4 | EXPL-01 | T-04-16 | Targets Explore action + sidebar; mocked-SSE e2e states | e2e | `npx playwright test tests/e2e/explore-live.spec.ts` | ❌ W0 | ⬜ pending |
| SC-live | all | gate | EXPL-01..06 | — | Real SauceDemo exploration + two-run convergence | live_llm/manual | `pytest -m "live_llm and graph" tests/functional/test_explore_live.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Sampling continuity check:** every task above has an `<automated>` verify (or is the blocking package gate); no 3 consecutive tasks lack automated verification. Nyquist-compliant.

---

## Wave 0 Requirements

- [ ] Fixture DOM/aria snapshots (SauceDemo pages) under `tests/fixtures/aria/` so perception/decision/fingerprint/convergence are testable WITHOUT a live browser or LLM (created in 04-01 Task 2 conftest + 04-02 Task 1)
- [ ] Mocked gateway fixture `fake_gateway` (extends Phase-2 fake_chat_model) returning a chosen action index — deterministic, zero spend (04-01 Task 2)
- [ ] Two-run convergence test harness: run the loop twice over the same fixtures, assert the second run adds ~0 new fingerprinted states (04-02 Task 2, EXPL-05)
- [ ] neo4j_session fixture + graph_mode (carried from Phase 3) for graph-marked functional exploration
- [ ] SSE test client helper: subscribe to the progress stream and assert event sequence/shape (04-04 Task 1)
- [ ] langgraph-checkpoint-postgres `.setup()` invoked in app startup (NOT in the Alembic chain — psycopg3-managed checkpoint tables) (04-01 Task 2)

*Existing functional infra (live-HTTP client, authed_client, poll_until_terminal, asyncio_mode=auto) carries forward.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full live autonomous exploration of SauceDemo | EXPL-01..06 | Needs real provider keys (LLM-driven decisions = real spend) + a live browser under graph_mode | Set provider keys, graph_mode up, POST /explore, watch the SSE live view, confirm pages/forms/elements discovered, screenshots captured, converges within budget on two runs |
| Live progress view in the browser | EXPL-01 | Visual real-time SSE rendering | Open the live exploration page during a run; confirm counters, action feed (incl. a refused row), current page + screenshot update live; terminal banner on convergence |
| Memory fit: api + neo4j + Chromium + LangGraph under 3GB cap | (infra) | host Vmmem observation under load | Under graph_mode (web down), run a live exploration; `docker stats` stays under the cap; no OOM |

*Deterministic logic (risk classifier, fingerprint, budgets/loop/convergence, locator extraction, origin allowlist, SSE event shapes) is automated with mocked gateway + fixtures.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (fixture snapshots, convergence harness, SSE test helper, checkpoint setup)
- [x] No watch-mode flags
- [x] Feedback latency < 3 min
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
