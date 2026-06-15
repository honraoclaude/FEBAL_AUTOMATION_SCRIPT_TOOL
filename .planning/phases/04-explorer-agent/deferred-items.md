# Phase 04 Explorer Agent — Deferred / Out-of-Scope Items

Items discovered during execution that are outside the current task's scope (SCOPE BOUNDARY).
Logged, not fixed.

## From 04-02 (fingerprint + convergence + auth)

- **`tests/functional/test_usage_ledger.py::test_complete_writes_one_ledger_row` flaked on an
  out-of-memory error** (`OSError: [Errno 12] Cannot allocate memory: '/app/app/models'`) during a
  `docker compose exec` into the api container. This is an environment/memory artifact under the
  documented Windows Docker Desktop 3GB stack cap (the api container is bounded to 1GiB and was
  near the limit while web held ~814MiB), NOT a code defect — it is unrelated to the fingerprint /
  convergence / auth files this plan touched. The deterministic unit suite (88 tests, zero spend)
  is fully green. Re-run the functional test alone after freeing container memory (e.g. stop the
  web container or raise the api memory limit) to confirm:
  `cd apps/api && uv run pytest tests/functional/test_usage_ledger.py -q`
