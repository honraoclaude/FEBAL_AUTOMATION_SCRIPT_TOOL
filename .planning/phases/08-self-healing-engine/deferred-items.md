# Phase 08 — Deferred / Out-of-Scope Items

Discovered during execution; NOT caused by the current plan's changes.

## Pre-existing functional-test failures (require live RabbitMQ queue profile — not up)

Observed during the full-suite run for plan 08-01. These are Phase-7 execution-plane
functional tests that REQUIRE the queue profile (`docker compose --profile queue up -d --wait rabbitmq`)
and were failing with `AMQPConnectionError: ... connection refused` because the broker is not
running in this environment. They have NO relationship to the Phase-8 pure scorer (no healing
imports). NOT fixed (environmental, out of scope per the executor scope boundary):

- `tests/functional/test_execute_tier.py::test_authed_post_smoke_tier_round_trip`
- `tests/functional/test_kill_drain.py::test_kill_run_purges_the_queue`
- `tests/functional/test_worker_consume.py::test_enqueue_consume_subprocess_lands_result_row`
- `tests/functional/test_worker_consume.py::test_consumer_sets_prefetch_count_two_on_the_channel`

Resolution: start the queue profile (and SauceDemo) before running the functional suite, exactly
as each module's docstring documents. Not a code defect.
