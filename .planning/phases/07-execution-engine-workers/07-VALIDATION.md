---
phase: 7
slug: execution-engine-workers
status: planned
nyquist_compliant: true
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
| **Full suite command** | `cd apps/api && uv run pytest -m "not live_llm" -q` (adds graph-marked + functional integration: real RabbitMQ enqueue→worker→result, per-step artifact capture, the determinism harness vs a reset SauceDemo, the seeded-bug-style planted-spec proof) |
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
> queue+functional integration / live_llm-manual), a threat ref, and a keyless command. The
> tier→marker mapping, risk-based selection, the aio-pika producer/consumer, the per-flow job
> runner (over a planted spec), the flaky classifier, the kill-flag drain, the history model +
> queries, and the determinism harness are ALL deterministic WITHOUT keys; the live
> generate→execute end-to-end is Manual-Only.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| P01-T1 | 07-01 | 1 | EXEC-03 | T-07-SC | gated aio-pika install (supply chain) | manual-gate | (human-verify: pypi.org/project/aio-pika + clean lock diff) | n/a | ⬜ pending |
| P01-T2 | 07-01 | 1 | EXEC-03 | T-07-04 | history model + SC3 NO-LLM import gate | unit + migration | `cd apps/api && uv run alembic upgrade head && uv run pytest tests/unit/test_no_llm_in_worker.py -q` | ❌ W0 | ⬜ pending |
| P01-T3 | 07-01 | 1 | EXEC-03 | T-07-01,02,03 | worker consume + subprocess argv-list + prefetch bound | functional | `cd apps/api && uv run pytest tests/functional/test_worker_consume.py -m functional -q` | ❌ W0 | ⬜ pending |
| P02-T1 | 07-02 | 2 | EXEC-01 | T-07-05,06 | tier allow-list selector + risk ranking (frozen weights, cold-start) | unit | `cd apps/api && uv run pytest tests/unit/test_exec_tiers.py tests/unit/test_risk_ranking.py -q` | ❌ W0 | ⬜ pending |
| P02-T2 | 07-02 | 2 | EXEC-01 | T-07-05 | generated-project marker registration | functional | `cd apps/api && uv run pytest tests/functional/test_codegen_markers.py -m functional -q` | ❌ W0 | ⬜ pending |
| P05-T1 | 07-05 | 2 | EXEC-02 | T-07-07,08,09 | scoped never-echoed CI token + start/poll contract | unit (yaml/contract) | `cd apps/api && uv run pytest tests/unit/test_ci_workflow_contract.py -q` | ❌ W0 | ⬜ pending |
| P05-T2 | 07-05 | 2 | EXEC-02 | T-07-06 | two-runs-identical vs reset target (status/verdict not timing) | functional | `cd apps/api && uv run pytest tests/functional/test_determinism.py -m functional -q` | ❌ W0 | ⬜ pending |
| P03-T1 | 07-03 | 3 | EXEC-04, EXEC-05 | T-07-11,12,04 | capture flags + retry loop + pure flaky classifier + paths-only | unit + functional | `cd apps/api && uv run pytest tests/unit/test_flaky_classifier.py -q && uv run pytest tests/functional/test_artifact_capture.py -m functional -q` | ❌ W0 | ⬜ pending |
| P03-T2 | 07-03 | 3 | EXEC-05, EXEC-01 | T-07-10,05 | history queries + auth-gated tier round-trip | functional | `cd apps/api && uv run pytest tests/functional/test_exec_history.py tests/functional/test_execute_tier.py -m functional -q` | ❌ W0 | ⬜ pending |
| P04-T1 | 07-04 | 4 | EXEC-06 | T-07-13,14,16 | per-test SSE + kill drain + purge + path guard (no SIGKILL) | functional | `cd apps/api && uv run pytest tests/functional/test_live_exec.py tests/functional/test_kill_drain.py -m functional -q` | ❌ W0 | ⬜ pending |
| P04-T2 | 07-04 | 4 | EXEC-06 | (supply chain) | gated recharts install OR native fallback | manual-gate | (human-verify: npmjs.com/package/recharts + clean diff, or fallback) | n/a | ⬜ pending |
| P04-T3 | 07-04 | 4 | EXEC-06 | T-07-13,14,17 | executions UI (server-authoritative, flaky-vs-failed, artifact basenames) | e2e | `cd apps/web && npx tsc --noEmit && npx playwright test tests/e2e/executions.spec.ts` | ❌ W0 | ⬜ pending |
| Manual | — | — | EXEC-01..06 | — | live LLM-generated suite end-to-end | manual | (documented manual steps; needs provider key) | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Every non-gate, non-manual task has an `<automated>` command. The two install tasks (P01-T1, P04-T2) are blocking human-verify gates by policy. No 3 consecutive tasks lack an automated verify.

---

## Wave 0 Requirements

- [ ] aio-pika 9.6.x added to apps/api/pyproject.toml + `uv sync` (the ONE expected new dep; locked in CLAUDE.md) — Plan 01 Task 1 (gated)
- [ ] A planted template-rendered spec (reuse the Phase-3/6 test_login.py.j2 path, TARGET_BASE_URL-overridable) for the deterministic per-flow-job / N-run / kill / determinism proofs — no keys (Plans 01/03/05)
- [ ] RabbitMQ test harness: a real `rabbitmq` under the `queue` profile for queue-marked functional tests, OR an in-process fabricated message dict for the unit-level producer/consumer contract (Plan 01 Task 3)
- [ ] execution-history fixtures (runs / test_results / artifacts) + migration 0007 (chains after 0006) — Plan 01 Task 2
- [ ] worker compose service (queue profile) + neo4j-off run-phase sequencing note (3GB cap) — Plan 01 Task 3
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

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (the two install tasks are blocking human-verify gates by policy)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (aio-pika, planted spec, RabbitMQ harness, history migration, worker service)
- [x] No watch-mode flags
- [x] Feedback latency < 6 min
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner, 2026-06-20)
