---
phase: 07-execution-engine-workers
plan: 01
subsystem: api
tags: [execution-engine, rabbitmq, aio-pika, worker, subprocess-runner, migration, prefetch, sc3-gate, planted-spec, compose]

# Dependency graph
requires:
  - phase: 06-bdd-playwright-generation
    provides: "stability._run_spec_once subprocess primitive (argv list, no shell, _run_cwd, output cap, TARGET_BASE_URL override); test_login.py.j2 planted-spec skeleton + planted helpers"
  - phase: 03-tracer-bullet-minimal-end-to-end-loop
    provides: "execution.run_execution fresh-SessionLocal finish shape; workspaces.spec_path run_id-derived convention; run_service create/VALID conventions"
  - phase: 04-explorer-agent
    provides: "explorer/progress.py Redis pub/sub publish seam; redis_client.get_redis single shared client"
provides:
  - "aio-pika 9.6.2 (the one new backend dep) for the RabbitMQ execution plane"
  - "TestRun/TestResult/TestArtifact ORM models + migration 0007 (test_runs/test_results/test_artifacts; artifact kind = screenshot|trace|video only)"
  - "schemas/execution.py: ExecuteTierRequest + TestRun/Result/Artifact responses (from_attributes)"
  - "services/worker/consumer.run_consumer (connect_robust, set_qos prefetch=2, durable exec.jobs, message.process)"
  - "services/worker/job.run_flow_job (per-flow runner reusing stability._run_spec_once verbatim; fresh-session TestResult)"
  - "services/worker/progress.publish_test_event (exec:{run_id} channel via shared get_redis)"
  - "services/exec_service: create_test_run + enqueue_jobs (default_exchange persistent publish)"
  - "app/worker_main.py worker container entrypoint (init_redis + run_consumer; no neo4j/checkpointer/LLM)"
  - "infra/docker-compose worker service (profiles:[queue], mem_limit 768m, command python -m app.worker_main) + rabbitmq healthcheck/ports + api AMQP_URL"
  - "SC3 NO-LLM import gate (tests/unit/test_no_llm_in_worker.py) over the worker package + worker_main"
  - "settings.amqp_url + settings.exec_prefetch_count (default 2)"
affects: [07-02, 07-03, 07-04, 07-05]

# Tech tracking
tech-stack:
  added:
    - "aio-pika==9.6.* (9.6.2) + transitives aiormq, pamqp, yarl (multidict, propcache) — gated install"
  patterns:
    - "aio-pika robust consumer: connect_robust + channel.set_qos(prefetch_count=2) + declare_queue(durable=True) + queue.iterator() + message.process(requeue=True); poison/non-JSON body ack-drops (T-07-02)"
    - "aio-pika persistent producer: connect_robust (transient per enqueue) + default_exchange.publish(Message(delivery_mode=PERSISTENT), routing_key=exec.jobs) awaiting publisher confirm"
    - "Per-flow job runner = thin wrapper over stability._run_spec_once (DRY verbatim reuse, NOT copy-paste) + fresh SessionLocal TestResult write (Pitfall 2)"
    - "spec_path is run_id-derived via workspaces.spec_path(run_id) — NEVER taken raw from the AMQP body (T-07-01 / carry-forward T-03-15)"
    - "prefetch_count=2 hard bound = parallel Chromium capacity under the 3GB WSL cap (worker mem_limit 768m, neo4j off during runs)"
    - "SC3 import grep gate: comment-stripped scan of the worker plane for init_chat_model/llm_gateway/langchain/langgraph/app.services.explorer (mirrors the KG-05 single-write-path gate)"
    - "Worker container = SAME api image, different command (reuse, not a second build)"

key-files:
  created:
    - apps/api/app/models/execution_history.py
    - apps/api/alembic/versions/0007_execution_history.py
    - apps/api/app/schemas/execution.py
    - apps/api/app/services/worker/__init__.py
    - apps/api/app/services/worker/progress.py
    - apps/api/app/services/worker/job.py
    - apps/api/app/services/worker/consumer.py
    - apps/api/app/services/exec_service.py
    - apps/api/app/worker_main.py
    - apps/api/tests/unit/test_no_llm_in_worker.py
    - apps/api/tests/functional/test_worker_consume.py
  modified:
    - apps/api/pyproject.toml
    - apps/api/uv.lock
    - apps/api/app/models/__init__.py
    - apps/api/app/main.py
    - apps/api/alembic/env.py
    - apps/api/app/core/config.py
    - infra/docker-compose.yml
    - .env.example

key-decisions:
  - "run_flow_job REUSES stability._run_spec_once VERBATIM (the plan's 'reused verbatim' directive + RESEARCH 'Don't Hand-Roll' table) rather than re-pasting create_subprocess_exec into job.py — the create_subprocess_exec call lives in the reused primitive, satisfying the job.py->subprocess key_link transitively while staying DRY"
  - "Plan-01 verdict is the THIN single-attempt shape (passed if exit 0 else product_failure, exit_codes a one-element list, attempts=1); the kill-check + retry loop + flaky classifier are explicitly deferred to Plan 03 (no placeholder stub for the live kill flag)"
  - "artifact kind = screenshot|trace|video ONLY (W4 (a)) — console+network live inside the Playwright trace; no console_log/network_log kinds, no binary columns (paths reference MinIO/workspaces)"
  - "migration 0007 hand-written (chains down_revision='0006'); run_id unique index on test_runs, run_id+flow_id indexed on results/artifacts; APP-TABLES-ONLY (LangGraph checkpoint tables stay AsyncPostgresSaver-owned)"
  - "settings.amqp_url is Optional (None default) so the api boots without the queue profile up — only an enqueue then errors (mirrors the graceful-without-neo4j contract)"
  - "The round-trip functional test (test_worker_consume.py) exercises the REAL queue-profile broker (W5) — enqueue via exec_service.enqueue_jobs, consume via the REAL run_consumer task, subprocess on a planted SauceDemo spec, asserting a passed TestResult row; a SEPARATE pure-channel test asserts prefetch_count==2 on a live channel"
  - "AMQP_URL added to .env (host/hybrid localhost value) + .env.example (documented) so host-driven functional tests reach the queue-profile broker at localhost:5672"

patterns-established:
  - "Execution plane = AMQP producer (exec_service in the api) + durable exec.jobs queue + stateless worker consumer (worker_main) running uv-run-pytest subprocesses; horizontal scale by worker replicas (deferred)"
  - "Worker progress over the SAME Redis pub/sub seam as the explorer, run-scoped channel exec:{run_id} (kill flag will be run:{run_id}:kill in Plan 03)"

requirements-completed: [EXEC-03]

metrics:
  duration: ~1h
  tasks-completed: 3
  files-created: 11
  files-modified: 8
  completed-date: 2026-06-21
---

# Phase 7 Plan 01: Execution-Engine Foundation (RabbitMQ Worker) Summary

Stood up the execution plane foundation: installed the one new backend dependency (aio-pika 9.6.2, behind the blocking verification gate), added the execution-history data model (migration 0007 with test_runs/test_results/test_artifacts), and built the stateless worker that consumes a RabbitMQ job and runs it as the battle-tested `uv run pytest` subprocess — proven end-to-end (enqueue → consume → subprocess → result row) on a planted SauceDemo spec with NO provider keys, against a REAL queue-profile broker, with prefetch_count=2 bounding concurrent browser capacity and the SC3 NO-LLM import gate green.

## What Was Built

**Task 1 — Gated aio-pika install (`c74b49a`):** `uv add aio-pika==9.6.*` resolved to 9.6.2; the lock diff shows ONLY aio-pika + its transitives (aiormq, pamqp, yarl, and yarl's multidict/propcache) — no other package. Human-approved blocking checkpoint per the package-legitimacy policy (T-07-SC).

**Task 2 — History model + migration 0007 + schemas + NO-LLM gate (`3d5031c` test, `0115702` feat):** Three ORM models mirroring run.py/scenario.py conventions; hand-written migration 0007 chaining after 0006 (run_id unique on test_runs, run_id+flow_id indexed on results/artifacts, downgrade drops in reverse); `schemas/execution.py` (ExecuteTierRequest + from_attributes responses); and the SC3 grep gate scanning the worker plane for forbidden LLM/explorer imports (mirrors the KG-05 single-write-path gate).

**Task 3 — Worker package + producer + worker_main + compose + round-trip (`06f7fb3`):** `worker/consumer.py` (connect_robust, set_qos prefetch=2, durable exec.jobs, message.process(requeue) with poison-payload ack-drop), `worker/job.py` (per-flow runner reusing `stability._run_spec_once` verbatim, run_id-derived spec_path, fresh-session TestResult), `worker/progress.py` (publish_test_event to exec:{run_id}), `exec_service.py` (create_test_run + enqueue_jobs persistent publish), `worker_main.py` (init_redis + run_consumer, no neo4j/LLM); compose `worker` service under profiles:[queue] (mem_limit 768m, `python -m app.worker_main`), rabbitmq healthcheck + ports, api AMQP_URL; and the real-broker round-trip + prefetch tests.

## Verification Evidence

- `uv run python -c "import aio_pika; print(aio_pika.__version__)"` → `9.6.2`; lock diff clean (aio-pika + transitives only).
- `uv run alembic upgrade head` → `0007 (head)`; downgrade→0006→upgrade→0007 round-trips cleanly; the three tables exist with the documented columns (ix_test_runs_run_id UNIQUE; run_id+flow_id indexed on results/artifacts).
- `TestRunResponse.model_validate(<ORM TestRun>)` parses without error.
- `tests/functional/test_worker_consume.py -m functional` → **2 passed in 17.89s**: a queued job → consumed by the REAL `run_consumer` → `uv run pytest` subprocess on a planted SauceDemo spec → a `test_results` row with the message's run_id/flow_id and verdict `passed`; prefetch_count==2 asserted on a live channel.
- Full deterministic suite `pytest -m "not live_llm and not graph and not e2e"` → **289 passed, 44 deselected in 92.54s** (NO-LLM gate green over the real worker source; no keys/neo4j).
- `docker compose --profile queue config` shows the `worker` service (profiles:[queue], mem_limit 805306368=768m, command python -m app.worker_main, depends_on rabbitmq service_healthy) and the rabbitmq `rabbitmq-diagnostics -q ping` healthcheck + 5672/15672 ports; rabbitmq reached **Healthy** on `--wait`.
- Acceptance greps: `_run_spec_once` reuse in job.py (verbatim subprocess), NO `shell=True`/`pytest.main` in worker code, `default_exchange.publish` in exec_service.py, `connect_robust` in consumer.py.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] AMQP_URL absent from the host environment**
- **Found during:** Task 3 (round-trip functional test)
- **Issue:** `exec_service.enqueue_jobs` reads `settings.amqp_url`, which was None in host/hybrid mode (.env had no AMQP_URL), so the round-trip test could not enqueue against the broker.
- **Fix:** Added `AMQP_URL=amqp://guest:guest@localhost:5672/` + `EXEC_PREFETCH_COUNT=2` to the repo-root `.env` (gitignored, host/hybrid localhost value matching the DATABASE_URL/REDIS_URL/NEO4J_URI convention) and documented both in the tracked `.env.example`. The compose api/worker blocks already set the in-cluster `rabbitmq` host value.
- **Files modified:** `.env` (gitignored, not committed), `.env.example` (committed)
- **Commit:** `06f7fb3`

### Interpretation note (not a deviation)

The plan's acceptance grep `grep -rn "create_subprocess_exec" app/services/worker/job.py` expects the literal call in job.py. job.py instead REUSES `stability._run_spec_once` (where `create_subprocess_exec` lives) — this is exactly the plan's stated action ("via the stability `_run_spec_once` argv shape reused verbatim") and the SendMessage directive ("reusing execution.py/stability._run_spec_once VERBATIM") and RESEARCH's "Don't Hand-Roll" table. The job.py→subprocess key_link is satisfied transitively through the reused primitive; copy-pasting the call would have violated the verbatim-reuse directive and DRY.

## Authentication Gates

None — the round-trip is proven keyless (planted spec, no provider keys, no neo4j).

## Known Stubs

The Plan-01 worker is intentionally the thin single-attempt slice. Deferred to **Plan 03** (documented in code docstrings, not silent):
- Kill-check (`run:{run_id}:kill` flag) — NOT stubbed (no placeholder), arrives in Plan 03.
- Per-attempt retry loop + flaky classifier (verdict flaky/aborted) — Plan 01 records `passed`/`product_failure` from one attempt's exit code.
- Per-step artifact capture (--screenshot/--tracing/--video flags + TestArtifact rows) — model/table exist; population arrives in Plan 03.

These do not block EXEC-03's goal (the enqueue→consume→subprocess→result-row round-trip), which is fully proven.

## Self-Check: PASSED

- Created files verified present: execution_history.py, 0007_execution_history.py, schemas/execution.py, worker/{__init__,progress,job,consumer}.py, exec_service.py, worker_main.py, test_no_llm_in_worker.py, test_worker_consume.py — all on disk.
- Commits verified in git log: c74b49a, 3d5031c, 0115702, 06f7fb3 — all present.
