---
phase: 3
slug: tracer-bullet-minimal-end-to-end-loop
status: draft
nyquist_compliant: false
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

- **After every task commit:** Run `cd apps/api && uv run pytest tests/unit -q`
- **After every plan wave:** Run the full suite with the graph profile active (`graph_mode` helper up: neo4j healthy, web stopped)
- **Before `/gsd:verify-work`:** Full suite green; the end-to-end tracer (explore→graph→generate→execute→result) demonstrated against live SauceDemo
- **Max feedback latency:** ~2 min

---

## Per-Task Verification Map

> Populated by the planner against the PLAN.md tasks. Each task maps to PLAT-02 and one of the
> 4 success criteria, a test type (unit / functional-live / live_llm for generation), and an
> automated command. Generation steps (generate-bdd/generate-scripts) hit the LLM gateway —
> the deterministic-output assertions use mocked init_chat_model; the real end-to-end generation
> proof is a live_llm/manual run with provider keys.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _planner fills_ | | | PLAT-02 | | | unit/functional/live_llm | | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Neo4j test access: a helper/fixture to assert Page/NavigatesTo nodes exist (cypher query over the lifespan driver) — graph profile must be active
- [ ] BackgroundTask polling helper: poll GET /executions/{run_id} (or run status) until a terminal state (passed/failed) with a timeout, so async jobs are testable deterministically
- [ ] Mocked init_chat_model fixture reused from Phase 2 (tests/unit/conftest.py) for generation-logic tests without provider spend
- [ ] `graph_mode` helper invocable from the test harness (or docs state the graph profile must be up + web down before functional runs)

*Existing functional infra (tests/conftest.py live-HTTP client, authed_client, asyncio_mode=auto) carries forward from Phases 1-2.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full end-to-end tracer with REAL LLM keys | PLAT-02 (SC-2) | generate-bdd/generate-scripts call the live LLM gateway (real spend) to produce the actual Gherkin + runnable spec | Set ANTHROPIC_API_KEY/OPENAI_API_KEY in .env, bring up the graph profile (web stopped), POST /explore → /generate-bdd → /generate-scripts → /execute against SauceDemo, confirm a passed executions row via GET /executions |
| Memory fit under the 3GB WSL cap with graph profile | PLAT-02 | host-level (Vmmem) observation under load | With `graph_mode` active (neo4j up, web down), run the tracer and confirm no OOM; `docker stats` stays under cap |

*Budget/status-machine/event-schema/gherkin-validation logic has automated verification with mocked providers.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (neo4j assert helper, BackgroundTask poll helper, graph_mode harness)
- [ ] No watch-mode flags
- [ ] Feedback latency < 2 min
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
