---
phase: 3
slug: tracer-bullet-minimal-end-to-end-loop
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-14
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (pytest-asyncio 1.4, asyncio_mode=auto) + pytest-playwright |
| **Config file** | apps/api/pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd apps/api && uv run pytest tests/unit -q` (logic that needs no live stack: status machine, event schemas, gherkin/jinja render) |
| **Full suite command** | `cd apps/api && uv run pytest tests -m "not live_llm" -q` (functional hit the live stack WITH the `graph` profile active + web stopped) |
| **Estimated runtime** | ~1-2 min (Playwright crawl + subprocess pytest execution add real wall time) |

---

## Sampling Rate

- **After every task commit:** Run `cd apps/api && uv run pytest -m "not live_llm and not e2e and not graph" -q` (fast, zero-spend, no neo4j needed)
- **After every plan wave:** Run the full suite with the graph profile active (`graph_mode` helper up: neo4j healthy, web stopped) — `uv run pytest -m "not live_llm" -q`
- **Before `/gsd:verify-work`:** Full suite green; the end-to-end tracer (explore→graph→generate→execute→result) demonstrated against live SauceDemo with provider keys
- **Max feedback latency:** ~2 min

---

## Per-Task Verification Map

> Each task maps to PLAT-02 and one of the 4 success criteria, a test type, and an automated command.
> Generation steps' deterministic-output assertions use mocked init_chat_model; the real end-to-end
> generation proof is a live_llm run with provider keys.

| Task ID | Plan | Wave | Requirement | SC | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|----|-----------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-T1 | 01 | 1 | PLAT-02 | SC4 | T-03-SC | Package legitimacy gate before uv add | checkpoint | (human-verify; PyPI confirm) | n/a | ⬜ pending |
| 03-01-T2 | 01 | 1 | PLAT-02 | SC1 | T-03-02/03/04 | Neo4j auth via env; trimmed memory; no plaintext in compose | unit/import | `uv run python -c "from app.core.neo4j_driver import init_neo4j,close_neo4j,get_neo4j; from app.core.config import settings; print(settings.neo4j_uri)"` + grep compose env names | ❌ W0 | ⬜ pending |
| 03-01-T3 | 01 | 1 | PLAT-02 | SC1 | T-03-01/04 | graph_mode argv-safe; stop-web-before-start-neo4j | unit | `uv run pytest tests/unit -q`; ast-parse graph_mode | ❌ W0 | ⬜ pending |
| 03-02-T1 | 02 | 2 | PLAT-02 | SC3/SC4 | T-03-09 | status machine guards VALID set | unit/import | `uv run alembic upgrade head` + import models/shared.events/run_service | ❌ W0 | ⬜ pending |
| 03-02-T2 | 02 | 2 | PLAT-02 | SC1 | T-03-05/06/07 | parameterized Cypher; single decrypt surface; auth gate; fresh session | import + grep | `uv run python -c "import explore/executions routers + explorer"`; grep MERGE/SessionLocal | ❌ W0 | ⬜ pending |
| 03-02-T3 | 02 | 2 | PLAT-02 | SC1 | T-03-05/06/07 | explore→Neo4j; 401 unauth | functional (graph) | `uv run pytest tests/functional/test_explore.py -q -m graph` | ❌ W0 | ⬜ pending |
| 03-03-T1 | 03 | 3 | PLAT-02 | SC2 | T-03-10/11/12 | gateway-only LLM; gherkin validate; observed selectors only | unit (mocked) | `uv run pytest tests/unit/test_generation_render.py -q` | ❌ W0 | ⬜ pending |
| 03-03-T2 | 03 | 3 | PLAT-02 | SC2 | T-03-13/14 | auth gate; budget-enforced gateway | import + grep | import generate router; grep generate_router in main | ❌ W0 | ⬜ pending |
| 03-03-T3 | 03 | 3 | PLAT-02 | SC2 | T-03-10/13 | zero-spend determinism + gated live_llm proof | unit + live_llm | `uv run pytest tests/unit/test_generation_render.py -q`; `-m live_llm` for real | ❌ W0 | ⬜ pending |
| 03-04-T1 | 04 | 4 | PLAT-02 | SC3 | T-03-15/16 | subprocess argv-safe; never in-process pytest; fresh session | import + grep | import execution/execute router; grep create_subprocess_exec / no pytest.main | ❌ W0 | ⬜ pending |
| 03-04-T2 | 04 | 4 | PLAT-02 | SC4 | T-03-19 | 501 only, never fabricated; auth gate | import | import stubs router; assert 5 paths | ❌ W0 | ⬜ pending |
| 03-04-T3 | 04 | 4 | PLAT-02 | SC3/SC4 | T-03-15/17/18/19 | execute result row; 10-endpoint surface; run_id thread | functional (+graph/live_llm) | `uv run pytest tests/functional/test_surface.py -q`; `test_execute.py -m graph`; `test_run_thread.py -m live_llm` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Neo4j test access: `neo4j_session` host-Bolt fixture to assert Page/NavigatesTo nodes exist (graph profile active) — **Plan 01 Task 3**
- [ ] BackgroundTask polling helper: `poll_until_terminal(client, run_id, ...)` GETs /executions/{run_id} until terminal — **Plan 01 Task 3**
- [ ] Mocked init_chat_model fixture reused from Phase 2 (tests/unit/conftest.py) for generation-logic tests without provider spend — **carried; used Plan 03**
- [ ] `graph` marker registered in pyproject.toml; `graph_mode` helper invocable before functional graph runs — **Plan 01 Task 3**

*Existing functional infra (tests/conftest.py live-HTTP client, authed_client, asyncio_mode=auto) carries forward from Phases 1-2.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full end-to-end tracer with REAL LLM keys | PLAT-02 (SC-2) | generate-bdd/generate-scripts call the live LLM gateway (real spend) to produce the actual Gherkin + runnable spec | Set ANTHROPIC_API_KEY/OPENAI_API_KEY in .env, bring up the graph profile (web stopped via graph_mode), POST /explore → /generate-bdd → /generate-scripts → /execute against SauceDemo, confirm a passed executions row via GET /executions (`test_run_thread.py -m live_llm`) |
| Memory fit under the 3GB WSL cap with graph profile | PLAT-02 | host-level (Vmmem) observation under load | With `graph_mode` active (neo4j up, web down), run the tracer and confirm no OOM; `docker stats` stays under cap |

*Budget/status-machine/event-schema/gherkin-validation logic has automated verification with mocked providers.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (neo4j assert helper, BackgroundTask poll helper, graph_mode harness — Plan 01 Task 3)
- [x] No watch-mode flags
- [x] Feedback latency < 2 min
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned (pending execution)
