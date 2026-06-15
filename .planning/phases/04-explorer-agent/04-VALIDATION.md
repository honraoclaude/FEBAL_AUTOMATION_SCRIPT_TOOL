---
phase: 4
slug: explorer-agent
status: draft
nyquist_compliant: false
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
| **Estimated runtime** | ~2-3 min (Playwright crawl + LangGraph loop add wall time) |

---

## Sampling Rate

- **After every task commit:** `cd apps/api && uv run pytest -m "not live_llm and not graph" -q`
- **After every plan wave:** full suite under graph_mode (`python infra/scripts/graph_mode.py up` first; stop neo4j + restore web after)
- **Before `/gsd:verify-work`:** full suite green; the convergence proof (two consecutive runs collapse to ~the same fingerprinted graph) passes deterministically on fixture snapshots; live exploration demonstrated with provider keys
- **Max feedback latency:** ~3 min

---

## Per-Task Verification Map

> Populated by the planner against the PLAN.md tasks. Each task maps to one+ of EXPL-01..09,
> a test type, and an automated command. The experimental fingerprint + convergence are proven
> DETERMINISTICALLY (fixture snapshots + mocked gateway); live LLM exploration is a live_llm/manual proof.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _planner fills_ | | | EXPL-0x | | | unit/graph/live_llm | | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Fixture DOM/aria snapshots (SauceDemo pages) so perception/decision/fingerprint/convergence are testable WITHOUT a live browser or LLM
- [ ] Mocked init_chat_model fixture (carried from Phase 2 tests/unit/conftest.py) returning a chosen action index — deterministic, zero spend
- [ ] Two-run convergence test harness: run the loop twice over the same fixtures, assert the second run adds ~0 new fingerprinted states (EXPL-05)
- [ ] neo4j_session fixture + graph_mode (carried from Phase 3) for graph-marked functional exploration
- [ ] SSE test client helper: subscribe to the progress stream and assert event sequence/shape
- [ ] langgraph-checkpoint-postgres `.setup()` invoked in app startup (NOT in the Alembic chain — psycopg3-managed checkpoint tables)

*Existing functional infra (live-HTTP client, authed_client, poll_until_terminal, asyncio_mode=auto) carries forward.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full live autonomous exploration of SauceDemo | EXPL-01..06 | Needs real provider keys (LLM-driven decisions = real spend) + a live browser under graph_mode | Set provider keys, graph_mode up, POST /explore, watch the SSE live view, confirm pages/forms/elements discovered, screenshots captured, converges within budget on two runs |
| Live progress view in the browser | EXPL-01 | Visual real-time SSE rendering | Open the live exploration page during a run; confirm counters, action feed, current page + screenshot update live |
| Memory fit: api + neo4j + Chromium + LangGraph under 3GB cap | (infra) | host Vmmem observation under load | Under graph_mode (web down), run a live exploration; `docker stats` stays under the cap; no OOM |

*Deterministic logic (risk classifier, fingerprint, budgets/loop/convergence, locator extraction, origin allowlist, SSE event shapes) is automated with mocked gateway + fixtures.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (fixture snapshots, convergence harness, SSE test helper, checkpoint setup)
- [ ] No watch-mode flags
- [ ] Feedback latency < 3 min
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
