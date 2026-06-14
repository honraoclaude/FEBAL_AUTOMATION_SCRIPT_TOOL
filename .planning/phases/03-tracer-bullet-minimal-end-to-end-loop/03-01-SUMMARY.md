---
phase: 03-tracer-bullet-minimal-end-to-end-loop
plan: 01
subsystem: infra
tags: [neo4j, bolt, docker-compose, pytest-bdd, gherkin, jinja2, knowledge-graph, memory-budget]

# Dependency graph
requires:
  - phase: 01-foundation-dev-environment
    provides: lifespan-managed client pattern (redis_client.py), Settings config, reset_target.py stdlib-helper contract, conftest host-rewrite fixtures, dormant compose profiles
provides:
  - Lifespan-managed async Neo4j driver singleton (init/close/get, lazy connect)
  - Trimmed neo4j compose service that boots healthy under the 3GB WSL cap
  - graph_mode helper enforcing stop-web-before-start-neo4j choreography
  - Wave-0 test scaffold — neo4j_session host Bolt fixture, poll_until_terminal helper, graph marker
  - Four new deps (neo4j, pytest-bdd, jinja2 top-level; gherkin-official transitive)
affects: [explore-to-graph, generation, execution, knowledge-graph, phase-05-kg]

# Tech tracking
tech-stack:
  added: [neo4j==6.2.*, pytest-bdd==8.1.*, jinja2==3.1.*, "gherkin-official==29.0.0 (transitive)"]
  patterns:
    - "Lazy lifespan driver = one connection pool for the whole process (mirror of redis_client.py)"
    - "Profile-gated dormant service with no depends_on so the api boots when the service is absent"
    - "Stop-web-first memory choreography helper (stdlib subprocess, argv lists, exit codes)"

key-files:
  created:
    - apps/api/app/core/neo4j_driver.py
    - infra/scripts/graph_mode.py
    - .planning/phases/03-tracer-bullet-minimal-end-to-end-loop/03-01-SUMMARY.md
  modified:
    - apps/api/pyproject.toml
    - apps/api/app/core/config.py
    - apps/api/app/main.py
    - infra/docker-compose.yml
    - .env.example
    - apps/api/tests/conftest.py

key-decisions:
  - "Option A: gherkin-official is TRANSITIVE at 29.x via pytest-bdd 8.1 — a direct gherkin-official==40.* pin is INCOMPATIBLE (pytest-bdd 8.1 hard-requires gherkin-official>=29,<30). CLAUDE.md's stack table is wrong on this point and should be corrected."
  - "Neo4j driver opens lazily so init_neo4j() at startup never blocks/fails when neo4j is down (graph profile inactive); no depends_on:neo4j on the api service."
  - "neo4j env-var underscore-doubling honored exactly (Pitfall 1): NEO4J_server_memory_heap_max__size (double) / NEO4J_server_memory_pagecache_size (single)."

patterns-established:
  - "graph_mode stop-web-first: free web's 1.5g BEFORE neo4j starts so the stack stays under the 3GB WSL cap"
  - "Host-side Bolt fixture rewrites in-cluster 'neo4j' host to localhost (mirrors the redis host rewrite)"
  - "202-then-poll run contract: poll_until_terminal never asserts immediately after enqueue"

requirements-completed: [PLAT-02]

# Metrics
duration: 9min
completed: 2026-06-14
---

# Phase 3 Plan 01: Neo4j Seam + Wave-0 Test Harness Summary

**Lifespan-managed async Neo4j driver, a memory-trimmed graph-profile compose service verified healthy under the 3GB WSL cap, and the stop-web-first graph_mode helper plus the Wave-0 Bolt fixture / poll helper / graph marker the rest of Phase 3 builds on.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-06-14T18:33:20Z
- **Completed:** 2026-06-14T18:42:29Z
- **Tasks:** 2 auto (Task 1 package-legitimacy gate was approved by a prior executor)
- **Files modified:** 9 (2 created, 7 modified) + this SUMMARY

## Accomplishments

- Installed the four phase deps per the approved Option A: `neo4j`, `pytest-bdd`, `jinja2` as top-level pins; `gherkin-official` arrives transitively at 29.x (the SAME parser pytest-bdd uses, so validate-then-execute stays consistent). Verified `from gherkin.parser import Parser` imports.
- Added `neo4j_driver.py` — a lazy lifespan `AsyncGraphDatabase` singleton (one driver = one pool) mirroring `redis_client.py`, wired symmetrically into `main.py`'s lifespan, with required `neo4j_uri/user/password` Settings fields.
- Trimmed the dormant neo4j compose service to heap 512m / pagecache 256m / mem_limit 1g with the exact (non-self-invalidating) env-var names, a 7474 wget healthcheck, and 7687/7474 ports; added `NEO4J_*` to the api env WITHOUT a `depends_on:neo4j`, so the api still boots when neo4j is absent (verified healthy after rebuild).
- Built `graph_mode.py` (stdlib-only) enforcing stop-web → `--profile graph up neo4j` → poll-7474-healthy → exit 0, with a `down` restore path and 0/1/2 exit codes.
- **Ran the real memory test on the host:** `graph_mode up` brought neo4j to **healthy** with web stopped at **~1.14 GB total** (neo4j 777 MiB) — well under the 3 GB cap. `graph_mode down` restored web healthy.
- Seeded the Wave-0 test scaffold: `neo4j_session` host Bolt fixture (neo4j→localhost rewrite, lazy import), `poll_until_terminal` deadline-loop helper, and a registered `graph` marker. Unit suite stays green (31 passed).

## Task Commits

Each task was committed atomically:

1. **Task 1: Package-legitimacy gate** — approved by the prior executor (no code commit; gate only)
2. **Task 2: Deps + trimmed neo4j compose + env/config/driver + lifespan wiring** — `39292fa` (feat)
3. **Task 3: graph_mode helper + Wave-0 test scaffold** — `ba830bd` (feat)

**Plan metadata:** committed separately with SUMMARY.md / STATE.md / ROADMAP.md (docs)

## Files Created/Modified

- `apps/api/app/core/neo4j_driver.py` — lazy lifespan AsyncGraphDatabase singleton (init/close/get)
- `infra/scripts/graph_mode.py` — stop-web-first graph choreography (up/down, exit 0/1/2)
- `apps/api/pyproject.toml` — neo4j/pytest-bdd/jinja2 deps + `graph` marker
- `apps/api/app/core/config.py` — required neo4j_uri/user/password Settings fields
- `apps/api/app/main.py` — init_neo4j()/close_neo4j() in lifespan
- `infra/docker-compose.yml` — trimmed neo4j block (exact mem env vars, healthcheck, ports) + api NEO4J_* env
- `.env.example` — four NEO4J_* keys (please-change flagged)
- `apps/api/tests/conftest.py` — neo4j_session fixture + poll_until_terminal helper

## Decisions Made

- **Option A on the gherkin/pytest-bdd conflict (see Deviations).**
- Neo4j driver opens lazily → graceful api boot without neo4j, no `depends_on`.
- Honored the exact env-var underscore-doubling (Pitfall 1).

## Deviations from Plan

### Locked-stack correction (Rule 4 — architectural decision, resolved before this executor ran)

**1. [Rule 4 / locked-stack] gherkin-official is 29.x TRANSITIVE, not a 40.* direct pin**
- **Found during:** Task 2 (`uv add`) by the prior executor, which returned a decision checkpoint.
- **Issue:** `pytest-bdd==8.1.*` hard-requires `gherkin-official>=29,<30`, so a direct `gherkin-official==40.*` pin (as named in PLAN.md Task 2 and in CLAUDE.md's stack table) is a hard, unresolvable dependency conflict — the two cannot coexist.
- **Decision (Option A, approved):** Do NOT add a direct `gherkin-official` pin. Run `uv add "neo4j==6.2.*" "pytest-bdd==8.1.*" "jinja2==3.1.*"`; gherkin-official arrives transitively at 29.0.0 via pytest-bdd. For standalone Gherkin validation (Plan 03), import the parser from the transitively-installed 29.x (`from gherkin.parser import Parser`) — the SAME parser pytest-bdd executes with, keeping validate-then-execute consistent. This stays inside the user-approved package set (neo4j, gherkin-official, pytest-bdd, jinja2) — gherkin-official is still present, just transitive at a different version. No new package, no new gate.
- **Files modified:** apps/api/pyproject.toml (3 top-level pins, not 4), apps/api/uv.lock
- **Verification:** `uv pip list` shows gherkin-official 29.0.0; `from gherkin.parser import Parser` imports cleanly.
- **Committed in:** `39292fa` (Task 2 commit)
- **ACTION REQUIRED — CLAUDE.md correction:** The Browser Automation & BDD stack table names `gherkin-official 40.x`. That is INCOMPATIBLE with the locked `pytest-bdd 8.1.x` (which pins `gherkin-official>=29,<30`). CLAUDE.md should be corrected to note gherkin-official is constrained to 29.x by pytest-bdd 8.1, and should not be declared as a direct 40.x top-level dependency.

---

**Total deviations:** 1 (locked-stack correction, pre-resolved as Option A).
**Impact on plan:** No scope change — same approved package set, same downstream parser. PLAN.md Task 2's `gherkin-official==40.*` instruction was superseded by the approved decision. Flags a CLAUDE.md doc fix.

## Known Stubs

- `poll_until_terminal` targets `GET /api/executions/{run_id}`, which does not exist yet (created by Plans 02-04). This is intentional Wave-0 scaffolding — the helper is defined-but-uncalled and tolerates the missing endpoint, so it does not break the current suite. Resolved when Plan 02 adds the executions endpoint.
- `neo4j_session` requires the neo4j graph profile to be active (tests must carry the `graph` marker and run under `graph_mode`). Intentional — no graph tests exist yet; downstream Phase-3 slices consume it.

## Threat Flags

None — no new security surface beyond the threat_model already registered (Bolt auth, compose argv, NEO4J_PASSWORD handling, host OOM all covered by T-03-01..T-03-SC and mitigated as planned).

## Issues Encountered

- The known hard dependency conflict (gherkin-official 40 vs pytest-bdd 8.1) — resolved via the approved Option A before this executor ran.
- After `graph_mode down` restores web, web (1.5g) + neo4j (1g) both run, which exceeds safe headroom; stopped neo4j afterward to return the host to the default 5-service footprint. (graph_mode intentionally leaves neo4j up so a caller can keep doing graph work; callers must stop neo4j before relying on the full default stack.)

## User Setup Required

None for this plan — `.env` was populated with the four `NEO4J_*` keys (gitignored). The `please-change` Neo4j password is a flagged dev default; change it for any network-exposed deployment.

## Next Phase Readiness

- Neo4j seam is reachable, memory-safe, and assertable in tests — the Wave-0 floor for explore→graph / generate / execute is in place.
- Plan 02 can now add the executions endpoint that `poll_until_terminal` targets and the first graph-writing path that `neo4j_session` asserts.
- Carry-forward: CLAUDE.md stack-table gherkin-official correction (see Deviations).

## Self-Check: PASSED

- FOUND: apps/api/app/core/neo4j_driver.py
- FOUND: infra/scripts/graph_mode.py
- FOUND: .planning/phases/03-tracer-bullet-minimal-end-to-end-loop/03-01-SUMMARY.md
- FOUND commit: 39292fa (Task 2)
- FOUND commit: ba830bd (Task 3)

---
*Phase: 03-tracer-bullet-minimal-end-to-end-loop*
*Completed: 2026-06-14*
