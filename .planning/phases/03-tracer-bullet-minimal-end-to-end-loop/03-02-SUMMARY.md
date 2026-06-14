---
phase: 03-tracer-bullet-minimal-end-to-end-loop
plan: 02
subsystem: explore-to-graph
tags: [explore, neo4j, playwright, background-task, runs, executions, run-id, shared-events, async-job]

# Dependency graph
requires:
  - phase: 03-tracer-bullet-minimal-end-to-end-loop
    plan: 01
    provides: lazy lifespan Neo4j driver get_neo4j(), graph_mode helper, neo4j_session fixture, poll_until_terminal helper, graph marker
  - phase: 01-foundation-dev-environment
    plan: 05
    provides: target_service.get_decrypted_credentials (single decrypt surface), Target model/base_url
provides:
  - runs/executions Postgres tables (migration 0004) + Run/Execution models
  - run_service status machine (VALID guard) + get_status_by_run_id resolver (Execution row else Run row, FIX 1)
  - shared/events Pydantic schemas (ExploreJob/ExecuteJob/RunStatusEvent) — schemas only, no broker
  - deterministic LLM-free Playwright explore crawl writing Page/NavigatesTo to Neo4j in a fresh-session BackgroundTask
  - POST /api/explore (202 + run_id) + GET /api/executions(/{run_id}) — auth-gated
  - api image baked with chromium --with-deps; shared/ + alembic/ bind-mounted into the api container
affects: [generation, execution, phase-04-explorer, phase-05-kg, phase-07-broker]

# Tech tracking
tech-stack:
  added: ["playwright==1.60.* (promoted transitive→runtime dep)"]
  patterns:
    - "BackgroundTask owns its OWN SessionLocal (Pitfall 2); the lifespan neo4j driver is reused across tasks"
    - "One run_id-keyed status surface for both paths: get_status_by_run_id prefers the Execution row, falls back to the Run row (FIX 1)"
    - "Parameterized Cypher MERGE only — never f-string page-derived text into the query (T-03-05)"
    - "Cross-service shared/ mounted at /app/shared so `import shared.events` resolves identically in container and host"

key-files:
  created:
    - apps/api/app/models/run.py
    - apps/api/alembic/versions/0004_runs_executions.py
    - apps/api/app/schemas/run.py
    - apps/api/app/services/run_service.py
    - apps/api/app/services/explorer.py
    - apps/api/app/routers/explore.py
    - apps/api/app/routers/executions.py
    - shared/__init__.py
    - shared/events/__init__.py
    - apps/api/tests/unit/test_run_status_machine.py
    - apps/api/tests/functional/test_explore.py
  modified:
    - apps/api/app/main.py
    - apps/api/alembic/env.py
    - apps/api/pyproject.toml
    - apps/api/uv.lock
    - apps/api/Dockerfile
    - infra/docker-compose.yml

key-decisions:
  - "shared/ is mounted (not COPY'd) into the api container at /app/shared because it sits outside the apps/api build context; WORKDIR /app is on sys.path so `import shared.events` resolves; pyproject pythonpath adds the repo root for host tests."
  - "alembic/ bind-mounted into the api container so new migrations (0004) reach the self-migrating entrypoint without an image rebuild."
  - "chromium + its OS libs baked into the api image via `playwright install --with-deps chromium`; playwright promoted from a transitive dev dep to an explicit runtime pin so --no-dev builds include it."
  - "The explore _page_key (normalized-url node identity) is an explicit TRACER seam — Phase 5 replaces write_page_graph with the structural fingerprint."

patterns-established:
  - "202-then-poll async-job contract live end-to-end: explore enqueues, poll_until_terminal observes terminal status by run_id."
  - "Status integrity centralized in run_service (VALID set guard); a crawl failure is captured as run.error, never a silent task crash (T-03-09)."

requirements-completed: []  # PLAT-02 stays OPEN — full 10-endpoint surface lands in 03-04

# Metrics
duration: 20min
completed: 2026-06-14
---

# Phase 3 Plan 02: Explore → Graph Seam + Async-Job Contract Summary

**The runs/executions Postgres model + migration 0004, the shared/events message schemas, the run-status service, and a deterministic LLM-free Playwright crawl that logs into SauceDemo and writes real Page/NavigatesTo nodes to Neo4j inside a fresh-session BackgroundTask — surfaced by POST /explore (202 + run_id) and GET /executions polling, with one run_id threading explore → graph.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 3 auto (Task 1 TDD: RED test → GREEN impl)
- **Files:** 11 created, 6 modified + this SUMMARY

## Accomplishments

- **Task 1 — persistence + schemas + status machine (TDD).** Wrote a failing unit spec (`test_run_status_machine.py`) for the four-state VALID guard and the shared/events schemas, then implemented: `Run`/`Execution` models (executions.run_id indexed — the execute-path poll key, FIX 1); migration 0004 chained `down_revision='0003'`; `run_service` with `create_run`/`set_status`/`create_execution`/`finish_execution` (keyed BY run_id) and the `get_status_by_run_id` resolver that returns the Execution row for execute-path run_ids and the Run row for explore-path run_ids; and `shared/events` ExploreJob/ExecuteJob/RunStatusEvent (Pydantic v2, no broker). Migration applied to the live Postgres (`alembic_version` = 0004). 17 unit tests green.
- **Task 2 — deterministic crawl + routers.** `explorer.run_explore` opens its OWN `SessionLocal` (Pitfall 2), reads creds ONLY via `get_decrypted_credentials`, drives chromium through the SauceDemo login (`#user-name`/`#password`/`#login-button` → `.inventory_list`), captures landing + a second (item-detail) page, and writes them via a PARAMETERIZED Cypher MERGE (`MERGE (a:Page {key:$a_key}) … MERGE (a)-[:NavigatesTo]->(b)`) using the reused lifespan neo4j driver. The whole body is guarded so a failure flips the run to `failed` with an error string (T-03-09). `POST /api/explore` returns 202 + run_id and registers the BackgroundTask; `GET /api/executions` lists rows and `GET /api/executions/{run_id}` resolves status via `get_status_by_run_id` (404 when neither row exists). Both routers behind `Depends(get_current_user)`.
- **Task 3 — SC1 functional proof (graph profile).** `test_explore.py` (functional + graph) registers a SauceDemo target at the in-cluster URL, POSTs /explore, polls to `passed` (never asserting immediately after the 202), and asserts ≥ 1 `(:Page)-[:NavigatesTo]->(:Page)` edge for the run_id via `neo4j_session`; plus a 401 auth-gate assertion. **Ran green under graph_mode** (neo4j up, web down): 2 passed in ~58s. Unit suite stays green (48 passed).
- **Verified the real seam on the host:** under graph_mode the crawl drove a real chromium in the api container against the live SauceDemo, wrote nodes to a healthy neo4j, and the poll observed `passed` — credentials never appeared in api logs (0 mentions).

## Task Commits

1. **Task 1 RED** — `3dbb1c5` (test): failing unit specs for the status machine + shared/events schemas.
2. **Task 1 GREEN** — `c731bf1` (feat): models + migration 0004 + run_service + shared/events.
3. **Task 2** — `e5c5b55` (feat): explorer crawl + explore/executions routers + infra wiring (chromium image, bind mounts).
4. **Task 3** — `94ccc82` (test): graph-marked functional proof of explore → Neo4j (SC1).

Plan metadata (this SUMMARY + STATE/ROADMAP) committed separately.

## Deviations from Plan

### Auto-fixed blocking issues (Rule 3)

**1. [Rule 3 — Blocking] `shared/` was not importable in either the container or host tests**
- **Found during:** Task 1 (`import shared.events`).
- **Issue:** `shared/` lives at the repo root, outside the `apps/api` build context and not on any sys.path. `import shared.events` failed in host tests, and the api container had no `shared/` at all.
- **Fix:** Added `shared/__init__.py` + `shared/events/__init__.py` as a real package; bind-mounted `../shared:/app/shared` into the api container (WORKDIR `/app` is on sys.path → resolves at runtime); added `"../.."` to pyproject `pythonpath` so host pytest resolves it identically.
- **Files:** `shared/__init__.py`, `shared/events/__init__.py`, `infra/docker-compose.yml`, `apps/api/pyproject.toml`.
- **Commits:** `3dbb1c5` (pythonpath), `c731bf1` (package), `e5c5b55` (mount).

**2. [Rule 3 — Blocking] migration 0004 unreachable by the container's self-migrating entrypoint**
- **Found during:** Task 1 (applying 0004). The container only bind-mounts `app/`; its baked alembic dir stopped at 0003, so the DB stamped 0004 while the container's alembic head was 0003 — a restart would have failed with "Can't locate revision 0004".
- **Fix:** Bind-mounted `../apps/api/alembic:/app/alembic` so new migrations reach the entrypoint without a rebuild; also rebuilt the api image so 0004 is baked. Restart now applies cleanly (DB and container both at 0004).
- **Files:** `infra/docker-compose.yml`.
- **Commit:** `e5c5b55`.

**3. [Rule 3 — Blocking] chromium absent / unlaunchable in the api container**
- **Found during:** Task 2/3 setup. `python:3.13-slim` had no playwright browser binaries, and after downloading them chromium failed to launch (`libglib-2.0.so.0` missing — no OS libs).
- **Fix:** Added `RUN uv run playwright install --with-deps chromium` to the Dockerfile (installs browser + apt OS libs durably) and promoted `playwright` from a transitive dev dep to an explicit `playwright==1.60.*` runtime pin so `--no-dev` builds include it. Rebuilt the api image; the crawl then logged into SauceDemo and launched chromium successfully.
- **Files:** `apps/api/Dockerfile`, `apps/api/pyproject.toml`, `apps/api/uv.lock`.
- **Commit:** `e5c5b55`.

**Total deviations:** 3 (all Rule 3 infrastructure-enablement fixes; no scope change). No Rule 4 architectural decisions, no auth gates.

## Known Stubs

- `explorer._page_key` / `write_page_graph` are an explicit TRACER seam: a normalized-url node identity and a minimal landing→second MERGE, NOT the Phase-5 structural fingerprint. Documented in-code; Phase 5 replaces `write_page_graph`. This is intentional per D-06 and does not block SC1 (the crawl writes real, query-able Page/NavigatesTo nodes today).
- The execute path (`create_execution`/`finish_execution`/Execution-row resolution in `get_status_by_run_id`) is implemented and unit/import-verified but not exercised end-to-end here — Plan 03-03/03-04's `/execute` slice drives it. Intentional: this plan delivers the explore half; the resolver is built now so the poll surface is run_id-keyed for both paths from the start.

## Threat Flags

None — all new surface (Cypher MERGE on page strings, decrypted creds, unauth /explore, run-status integrity) is covered by the plan's registered threat_model (T-03-05/06/07/09) and mitigated as planned: parameterized Cypher, single decrypt surface with no cred logging (verified 0 log mentions), router-level auth gate with a 401 test, and VALID-guarded status transitions.

## Issues Encountered

- The browser/OS-deps install and image rebuild (chromium ~113MB) is the slow part of running the graph functional test; baked into the image now so it is a one-time build cost.
- `graph_mode down` restores web but intentionally leaves neo4j up (web 1.5g + neo4j 1g exceeds safe headroom); stopped neo4j afterward to return the host to the default 5-service footprint.

## Next Phase Readiness

- The explore→graph seam and the 202-then-poll async-job contract are live and assertable. Plans 03-03/03-04 can build generate-bdd/generate-scripts/execute on the run_id contract; the Execution-row execute path resolver is already in place.
- PLAT-02 stays OPEN — the full 10-endpoint surface (with 501 stubs) lands in 03-04.

## Self-Check: PASSED

- FOUND: apps/api/app/models/run.py
- FOUND: apps/api/alembic/versions/0004_runs_executions.py
- FOUND: apps/api/app/services/run_service.py
- FOUND: apps/api/app/services/explorer.py
- FOUND: apps/api/app/routers/explore.py
- FOUND: apps/api/app/routers/executions.py
- FOUND: shared/events/__init__.py
- FOUND: apps/api/tests/functional/test_explore.py
- FOUND commit: 3dbb1c5 (Task 1 RED)
- FOUND commit: c731bf1 (Task 1 GREEN)
- FOUND commit: e5c5b55 (Task 2)
- FOUND commit: 94ccc82 (Task 3)

---
*Phase: 03-tracer-bullet-minimal-end-to-end-loop*
*Completed: 2026-06-14*
