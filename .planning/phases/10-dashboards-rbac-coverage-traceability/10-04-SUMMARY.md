---
phase: 10-dashboards-rbac-coverage-traceability
plan: 04
subsystem: search
tags: [search, elasticsearch, full-text, on-write-index, swallow-and-log, graceful-degrade, role-gate, backfill]

# Dependency graph
requires:
  - phase: 10-dashboards-rbac-coverage-traceability
    plan: 01
    provides: require_role(*roles) gate + rbac.ROLE_PERMISSIONS endpoint->role matrix (search -> all authed roles)
  - phase: 09-defect-jira
    provides: Classification + Defect (run_id/flow_id/classification/fingerprint/jira_key) — the failures on-write source + backfill rows
  - phase: 07-execution-engine
    provides: TestResult/TestArtifact (run_id/flow_id/verdict/error_text) — the executions on-write source + backfill rows; worker/job.py commit seam
  - phase: 03-tracer-bullet
    provides: core.neo4j_driver lazy-singleton + ensure_constraints graceful-boot precedent + the main.py 503 handler shape mirrored here
provides:
  - core.es_client lazy init_es/get_es/close_es AsyncElasticsearch singleton (api boots when ES down)
  - search.indexer ensure_indices + index_execution/index_failure (on-write swallow-and-log) + backfill (async_bulk)
  - search.query.search(q, *, index, es) — parameterized multi_match + highlight returning typed hits
  - role-gated GET /api/search (all authenticated roles) with honest ES-down 503
  - SearchHit/SearchResponse schemas + FakeAsyncElasticsearch keyless contract double
affects: [10-06-search-ui, search-viewer]

# Tech tracking
tech-stack:
  added:
    - "elasticsearch[async]==9.4.* (gated backend dep; client major == ES server major 9.x; async extra pulls aiohttp transport)"
  patterns:
    - "lazy AsyncElasticsearch singleton mirroring neo4j_driver — constructed at lifespan, opens socket on first request, so the api boots when the search profile is down"
    - "on-write dual-index AFTER the Postgres commit, wrapped swallow-and-log (es_index_skipped) — incl. client construction inside the try — so an ES outage NEVER breaks the Postgres write (T-10-19)"
    - "ensure_indices idempotent + graceful (exists-then-create, swallow-when-down) — the ensure_constraints boot precedent"
    - "ConnectionError NOT swallowed on the READ path — it bubbles to a main.py @exception_handler -> honest 503 'search unavailable', never a fake empty list (T-10-20)"
    - "parameterized multi_match — q is a STRUCTURED query VALUE, never string-concatenated into the DSL (T-10-17, the reader.py discipline)"
    - "backfill via an injectable bulk_runner (defaults to elasticsearch.helpers.async_bulk) so the keyless contract asserts the action stream without driving async_bulk's deep client internals"
    - "keyless contract double (FakeAsyncElasticsearch) for CI; the live round-trip is search-profile-gated and SKIPS when ES is unreachable"

key-files:
  created:
    - apps/api/app/core/es_client.py
    - apps/api/app/services/search/__init__.py
    - apps/api/app/services/search/indexer.py
    - apps/api/app/services/search/query.py
    - apps/api/app/schemas/search.py
    - apps/api/app/routers/search.py
    - apps/api/tests/fixtures/fake_es.py
    - apps/api/tests/unit/test_search_contract.py
    - apps/api/tests/integration/test_search_degrade.py
    - apps/api/tests/functional/test_search_live.py
  modified:
    - apps/api/app/main.py
    - apps/api/app/core/config.py
    - apps/api/app/services/worker/job.py
    - apps/api/app/services/defects/pipeline.py
    - apps/api/pyproject.toml
    - apps/api/uv.lock
    - infra/docker-compose.yml

decisions:
  - "Added the elasticsearch async extra (aiohttp transport) rather than the base package: AsyncElasticsearch is the chosen interface and is non-functional without an async HTTP node — enabling the already-gated/approved package, not a new package choice (the greenlet-for-SQLAlchemy-async precedent in CLAUDE.md)"
  - "get_es() construction sits INSIDE the on-write try/except: AsyncElasticsearch(...) can raise at construct (missing transport / misconfigured host) before any request — that must be swallowed too, never escape into the Postgres write path"
  - "backfill takes an injectable bulk_runner so the keyless test verifies the produced action stream without faking async_bulk's transport/serializer internals"

metrics:
  duration_min: 21
  completed: 2026-06-29
  tasks: 3
  files_created: 10
  files_modified: 7
  tests_added: 13
requirements: [DASH-06]
---

# Phase 10 Plan 04: Elasticsearch-Backed Search (DASH-06) Summary

Full-text search over executions/failures/logs served by Elasticsearch: a lazy lifespan-managed
AsyncElasticsearch client (api boots when ES is down), on-write dual-indexing that swallow-and-logs
so an ES outage never breaks the Postgres source of truth, a backfill reindexer, and a role-gated
`GET /api/search` with parameterized multi_match + highlight that graceful-degrades to an honest 503
— all keyless-testable against a FakeAsyncElasticsearch double, with the live round-trip
search-profile-gated.

## What Was Built

- **Gated dep (Task 1):** `elasticsearch[async]==9.4.*` — the single new backend dep (client major
  9 == ES server 9.x), approved at the blocking checkpoint. Zero frontend deps.
- **es_client.py (Task 1):** `init_es/get_es/close_es` lazy AsyncElasticsearch singleton mirroring
  `neo4j_driver.py`. Wired into the `main.py` lifespan + an `ESConnectionError -> 503` handler.
- **compose/config (Task 1):** the three `xpack.security.*=false` vars on the ES block (Pitfall 1),
  `ELASTICSEARCH_URL` enumerated on the api service, host 9200 publish for the live test;
  `elasticsearch_url` already in `config.py` (pre-gate groundwork).
- **indexer.py (Task 2):** typeless mappings for `executions`/`failures`/`logs`; idempotent +
  graceful `ensure_indices`; `index_execution`/`index_failure` on-write hooks (swallow-and-log,
  wired AFTER `db.commit()` in `worker/job.py` and `defects/pipeline.py`); `backfill` via
  `async_bulk` (injectable runner).
- **query.py + router + schemas (Task 3):** parameterized `multi_match` + `highlight` returning typed
  hits; `GET /api/search` role-gated for all authenticated roles, registered before `stubs_router`;
  ES-down bubbles to the honest 503 (never a fake empty list).
- **FakeAsyncElasticsearch + tests:** the keyless contract double; the unit contract suite, the
  integration degrade suite (role matrix + honest 503), and the search-profile-gated live round-trip.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] On-write swallow must cover client construction**
- **Found during:** Task 2 (the full deterministic suite tripped `test_defect_pipeline`)
- **Issue:** `index_execution`/`index_failure` acquired the client (`get_es()`) BEFORE the
  try/except. Constructing `AsyncElasticsearch(...)` can itself raise (transport/host issue) before
  any request — that escaped into the Postgres write path and failed three pipeline tests.
- **Fix:** moved `get_es()` INSIDE the try block in both hooks, so client construction failure is
  swallowed-and-logged like a request failure (T-10-19 holds for the construct path too).
- **Files modified:** apps/api/app/services/search/indexer.py
- **Commit:** 600896a

**2. [Rule 3 - Blocking] AsyncElasticsearch needs the async transport (aiohttp)**
- **Found during:** Task 2/3 (real-client construction raised `ValueError: must have 'aiohttp'`)
- **Issue:** the base `elasticsearch` install ships no async HTTP node; `AsyncElasticsearch` — the
  chosen interface — cannot construct without `aiohttp`, so both the on-write path (under the swallow
  it would always skip) and the live round-trip were non-functional.
- **Fix:** changed the gated dep to the `elasticsearch[async]==9.4.*` extra (pulls `aiohttp` +
  transitives). This enables the already-approved package's chosen async interface — not a new
  third-party package choice (the greenlet-for-SQLAlchemy-async precedent). Documented as a decision.
- **Files modified:** apps/api/pyproject.toml, apps/api/uv.lock
- **Commit:** 87ae8f7

**3. [Rule 1 - Bug] FakeAsyncElasticsearch lacked `options()` for async_bulk + backfill testability**
- **Found during:** Task 2 (backfill test)
- **Issue:** `elasticsearch.helpers.async_bulk` calls `client.options()` then reaches into
  `client.transport.serializers` — internals the in-memory fake cannot mirror.
- **Fix:** added `options()` (returns self) to the fake AND made `backfill` accept an injectable
  `bulk_runner` (defaults to the real `async_bulk`); the keyless test injects a recording runner that
  consumes the SAME async action iterator, asserting the action stream + stable ids.
- **Files modified:** apps/api/tests/fixtures/fake_es.py, apps/api/app/services/search/indexer.py,
  apps/api/tests/unit/test_search_contract.py
- **Commit:** 600896a

## Authentication / Setup Gates

- **checkpoint:human-verify (D-04, package legitimacy):** the `elasticsearch` install was gated
  behind a blocking checkpoint. The human approved it ("APPROVED — the human cleared the
  elasticsearch install gate"); the install then proceeded as Task 1. Normal flow, not a deviation.

## Verification Results

- Keyless contract + degrade: `pytest tests/unit/test_search_contract.py
  tests/integration/test_search_degrade.py` -> 11 passed.
- Grep gates: `es_index_skipped` present in indexer.py; both on-write call sites are AFTER their
  `db.commit()` inside swallow; `multi_match` present in query.py with q as a VALUE (no
  f-string/%/+ DSL build); `ESConnectionError` + "Search is unavailable" present in main.py.
- Frontend untouched: `git diff --quiet apps/web/package.json` -> exit 0. Only `elasticsearch[async]`
  added to apps/api/pyproject.toml + transitives in uv.lock.
- Full deterministic suite: `pytest -m "not live_llm and not e2e and not graph and not functional and
  not search"` -> 458 passed, no regressions.
- Live (Manual-Only / search profile): `tests/functional/test_search_live.py` collects + SKIPS
  cleanly when ES is unreachable; run it under `docker compose --profile search up -d --wait
  elasticsearch` (neo4j OFF — 3GB cap).

## Manual-Only Items

- The live ES round-trip (`pytest -m search tests/functional/test_search_live.py`) requires the
  `search` compose profile; sequence it with neo4j OFF under the 3GB WSL cap.

## Self-Check: PASSED

All 10 created files exist on disk; all three task commits (c8283ef, 600896a, 87ae8f7) are present
in git history.
