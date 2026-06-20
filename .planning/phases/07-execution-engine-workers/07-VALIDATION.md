---
phase: 7
slug: execution-engine-workers
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-20
---

# Phase 7 — Execution Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (pytest-asyncio 1.4, asyncio_mode=auto) + pytest-playwright + pytest-bdd; frontend tsc/eslint/playwright |
| **Config file** | apps/api/pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd apps/api && uv run pytest -m "not live_llm and not graph and not e2e" -q` (tier→marker mapping, the flaky classifier, history queries, the aio-pika producer/consumer with a fake/in-memory broker or a real rabbitmq under the `queue` profile, the kill-flag drain, the per-flow job runner over a planted spec — no provider keys, no neo4j) |
| **Full suite command** | `cd apps/api && uv run pytest -m "not live_llm" -q` (adds graph-marked + queue-marked integration: real RabbitMQ enqueue→worker→result, per-step artifact capture, the determinism harness vs a reset SauceDemo, the seeded-bug-style planted-spec proof) |
| **Frontend command** | `cd apps/web && npx tsc --noEmit && npx eslint <touched> && npx playwright test tests/e2e/executions.spec.ts` |
| **Estimated runtime** | ~4-6 min (parallel browser subprocess runs + N-retry attempts add real wall time) |

---

## Sampling Rate

- **After every task commit:** `cd apps/api && uv run pytest -m "not live_llm and not graph and not e2e" -q`
- **After every plan wave:** full suite with RabbitMQ up under the `queue` profile (`docker compose --profile queue up -d rabbitmq worker`); neo4j OFF during run-phase tests (3GB cap)
- **Before `/gsd:verify-work`:** full deterministic suite green; the kill-drain + flaky classifier + determinism harness green on planted specs; live tier run (generate→approve→execute→artifacts→history→live-view→kill) demonstrated with provider keys + a real generated suite
- **Max feedback latency:** ~6 min

---

## Per-Task Verification Map

> Populated by the planner. Each task maps to EXEC-01..06, a test type (unit deterministic /
> queue+graph integration / live_llm-manual), a threat ref, and a keyless command. The
> tier→marker mapping, risk-based selection, the aio-pika producer/consumer, the per-flow job
> runner (over a planted spec), the flaky classifier, the kill-flag drain, the history model +
> queries, and the determinism harness are ALL deterministic WITHOUT keys; the live
> generate→execute end-to-end is Manual-Only.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | EXEC-01..06 | — | populated by planner | — | — | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] aio-pika 9.6.x added to apps/api/pyproject.toml + `uv sync` (the ONE expected new dep; locked in CLAUDE.md)
- [ ] A planted template-rendered spec (reuse the Phase-3/6 test_login.py.j2 path, TARGET_BASE_URL-overridable) for the deterministic per-flow-job / N-run / kill / determinism proofs — no keys
- [ ] RabbitMQ test harness: either a real `rabbitmq` under the `queue` profile for queue-marked integration tests, or an in-process fake for the unit-level producer/consumer contract (decide in planning)
- [ ] execution-history fixtures (runs / test_results / artifacts) + migration 0007 (chains after 0006)
- [ ] worker compose service (queue profile) + neo4j-off run-phase sequencing note (3GB cap)
- [ ] Existing functional infra (live-HTTP client, authed_client, the subprocess runner, Redis pub/sub→SSE seam, reset_target.py) carries forward

*Existing infrastructure (asyncio_mode=auto, authed_client, poll_until_terminal, the execution.py subprocess runner, the explorer Redis→SSE seam) covers most of the phase; aio-pika + the planted-spec harness are the new Wave-0 pieces.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live tier run end-to-end | EXEC-01..06 | Needs provider keys (a real LLM-generated/approved suite) + a real explored graph | Set keys, generate+approve scenarios + codegen, enqueue a `smoke` tier run, watch the live view, confirm artifacts + history + flaky detection, kill a run mid-flight |
| GitHub Actions trigger reaching the local API | EXEC-02 | GH-hosted runners can't reach local host port 8001 | Configure a self-hosted runner on the dev box; trigger the workflow; confirm it starts a tier via the API and reports status back |
| Memory fit under 3GB during a parallel run | (infra) | host Vmmem observation | `docker stats` during a `prefetch=2` run with neo4j OFF — confirm RabbitMQ + worker + 2 Chromium + Postgres/Redis stay under the cap |

*Deterministic logic (tier mapping, risk selection, producer/consumer contract, per-flow job over a planted spec, flaky classifier, kill drain, history queries, determinism harness) is automated without keys.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (aio-pika, planted spec, RabbitMQ harness, history migration, worker service)
- [ ] No watch-mode flags
- [ ] Feedback latency < 6 min
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
