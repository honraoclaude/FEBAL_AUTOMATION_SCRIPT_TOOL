# Phase 3: Tracer Bullet — Minimal End-to-End Loop - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning

<domain>
## Phase Boundary

One deliberately THIN slice through the entire pipeline against SauceDemo, proving the loop end-to-end before any engine is built deep: explore → write minimal Page/NavigatesTo nodes to Neo4j → generate one Gherkin scenario + one runnable Playwright spec from the graph (via the Phase-2 LLM gateway) → execute that spec → land a result row in Postgres → retrieve via GET /executions. Plus the full PLAT-02 REST surface exists (all 10 endpoints) — real where the slice covers them, honest stubs elsewhere — with queue message schemas defined in `shared/events/`.

**In scope:** Neo4j activation (trimmed, local), a deterministic Playwright tracer Explorer, minimal Neo4j writes, LLM-gateway-backed generate-bdd/generate-scripts, a spec executor, the run/execution model in Postgres, all 10 REST endpoints (real + 501 stubs), shared/events Pydantic schemas.
**Out of scope (own phases):** the intelligent Explorer (Phase 4 — perception, budgets, risk, fingerprints, LangGraph), the real Knowledge Graph single-writer + idempotent MERGE + flow mining (Phase 5), quality-gated generation with review queue + N-run stability (Phase 6), RabbitMQ-distributed workers + suite tiers + artifacts (Phase 7), healing (Phase 8), defect/Jira (Phase 9), dashboards/RBAC (Phase 10). The tracer touches each seam minimally; depth comes later.

</domain>

<decisions>
## Implementation Decisions

### Neo4j on a constrained host (the carried blocker — 5.7 GB RAM / 3 GB WSL cap)
- **D-01:** Run Neo4j LOCALLY (honors the CLAUDE.md "all services run locally via Docker Compose" constraint) — NOT remote Aura. `neo4j:2025` stays behind the existing `graph` compose profile (not in default `up`).
- **D-02:** Trim Neo4j memory hard for the tracer's tiny graph: heap max 512m, pagecache 256m, container `mem_limit` 1g. (Tune up in Phase 5 when the real KG lands.) The current Conservative alternative (2g) was rejected as too risky on this host.
- **D-03:** A SCRIPTED helper (e.g. `infra/scripts/graph_mode.py` or a compose-profile wrapper) performs the container juggling: STOP the web container (~1.5g) during graph work, ensure neo4j is up+healthy, run the work, then restore web. One repeatable command — not error-prone manual steps. Memory math while exploring: postgres 512m + redis 256m + api 1g + neo4j 1g + saucedemo 128m ≈ 2.9g (fits under 3g; web is down). The tracer exercises the API via httpx, so web being down during exploration is fine.

### Long-running job model (/explore, /execute) — no RabbitMQ until Phase 7
- **D-04:** `/explore` and `/execute` are ASYNC-STYLE: POST returns **202 + a run_id immediately**; the work runs IN-PROCESS via FastAPI BackgroundTasks; status (queued → running → passed/failed) and results are polled via GET (e.g. GET /executions, GET /executions/{id}). This mirrors the eventual queue contract (caller gets an id, polls for result) so Phase 7 swaps BackgroundTasks → RabbitMQ workers with NO API-contract change. Synchronous blocking was rejected (blocks the request; would force an API change in Phase 7).
- **D-05:** `shared/events/` gets Pydantic MESSAGE SCHEMAS ONLY (e.g. ExploreJob, ExecuteJob, and result/status events) — the shapes the in-process BackgroundTasks path produces/consumes now and Phase 7 publishes to RabbitMQ later. NO broker, NO aio-pika wiring, NO queue abstraction layer this phase (the thin-abstraction alternative was rejected as over-design before Phase 7's real worker needs are known).

### Tracer Explorer minimalism (full Explorer is Phase 4)
- **D-06:** Exploration is a DETERMINISTIC Playwright crawl, NO LLM in the explore step: log into SauceDemo (known login form), capture the landing/inventory page as a Page node, click one link capturing a NavigatesTo edge. Proves the Playwright→Neo4j seam without LLM non-determinism. (Minimal LLM-driven perception was rejected as Phase-4 scope creep.)
- **D-07:** The Phase-2 LLM GATEWAY is exercised by generate-bdd and generate-scripts (the right place to prove the gateway end-to-end) — one Gherkin scenario and one runnable Playwright spec generated from the explored graph, routed through `app/services/llm_gateway.complete()` with an operation_type + run_id (never a direct provider call).
- **D-08:** Defer LangGraph to Phase 4. The deterministic tracer Explorer is plain async Playwright — there is no agent loop to orchestrate or checkpoint yet. LangGraph + langgraph-checkpoint-postgres enter with the real Explorer (Phase 4, raw StateGraph per CLAUDE.md).

### Claude's Discretion
- **Stub contract for the 5 unbuilt endpoints** (heal, create-defect, flows, coverage, dashboard): default to **501 Not Implemented with documented OpenAPI contracts** describing each endpoint's eventual request/response shape, so the PLAT-02 surface is COMPLETE and HONEST (the contract exists; the behavior is explicitly not-yet-implemented). Research/planner may refine, but the surface must be complete and must not fake results.
- Generated-artifact storage layout (the `.feature` + Playwright `.py` spec) under the gitignored `workspaces/` tree, keyed by run_id, and how `/execute` locates the spec to run — left to research/planner, provided it ties to the run_id.
- The minimal Neo4j Cypher write seam (direct driver writes for Page/NavigatesTo) is intentionally NOT the Phase-5 single-writer service — keep it minimal and clearly marked as a tracer seam to be superseded.
- How a single run_id threads explore → graph → generate → execute → result for the slice's traceability.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — PLAT-02 (the 10-endpoint REST surface this phase delivers).
- `.planning/ROADMAP.md` (Phase 3 section) — the 4 success criteria are the contract: real Page/NavigatesTo in Neo4j from POST /explore; generate-bdd + generate-scripts produce one scenario + one runnable spec; /execute runs it and a result row lands in Postgres retrievable via GET /executions; all 10 endpoints exist (real or honest stub) + queue schemas in shared/events/.

### Locked stack (do not re-litigate)
- `CLAUDE.md` — Neo4j driver 6.2.x (`neo4j` package, AsyncGraphDatabase, Bolt); Playwright 1.60 async for exploration; pytest-bdd/gherkin-official + Jinja2 for generation; LangGraph slotted for the Phase-4 Explorer (NOT this phase); "all services run locally via Docker Compose" dev constraint (drives D-01). Note the Neo4j-Prometheus caveat (Enterprise-only) — irrelevant this phase.

### Existing code this phase builds on
- `apps/api/app/services/llm_gateway.py` — `complete(db, messages, *, operation_type, run_id, model=None, temperature, max_tokens, no_cache)` is the ONLY LLM path (generate-bdd/generate-scripts call it; D-07).
- `apps/api/app/main.py` — FastAPI app + lifespan (engine, redis); new routers (explore/generate/execute/executions + stubs) include here; a Neo4j async driver may be lifespan-managed like redis.
- `apps/api/app/routers/targets.py` — router-level `Depends(get_current_user)` gate + service-layer + 404/409 translation pattern to mirror for new routers.
- `apps/api/app/db/{base,session}.py` + `apps/api/alembic/` (chain 0001→0002→0003_llm_usage) — new `runs`/`executions` tables chain after 0003.
- `infra/docker-compose.yml` — neo4j dormant service (profiles [graph], mem_limit 2g → trim to 1g per D-02) + the web service to stop during graph work (D-03).
- `infra/scripts/reset_target.py` — the existing scripted-helper pattern to mirror for the graph_mode helper (D-03).
- `shared/events/README.md` — the directory PLAT-02 queue schemas live in (D-05).
- `apps/api/tests/conftest.py` — live-stack functional test fixtures (authed_client, etc.) carried from Phase 1.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **LLM gateway** (`llm_gateway.complete()`): generation steps route through it; budgets/kill-switch/caching/logging come for free.
- **Service-layer + router pattern** (`target_service.py` / `targets.py`): mirror for explore/generate/execute services + routers with router-level auth.
- **Scripted-helper pattern** (`infra/scripts/reset_target.py`): the analog for the `graph_mode` web-stop/neo4j-up helper (D-03).
- **Lifespan-managed driver pattern** (`app/core/redis_client.py` + main.py lifespan): the analog for a single long-lived Neo4j `AsyncGraphDatabase` driver.
- **Async Alembic chain** (0001→0002→0003): new `runs`/`executions` migrations chain after 0003.
- **Dormant compose profile** (`graph`): neo4j already gated; just trim memory and wire the helper.

### Established Patterns
- Functional tests hit the LIVE stack over HTTP (D-02 Phase-1 philosophy). Tracer e2e tests need neo4j + saucedemo up (web down) — the test harness must invoke the graph_mode helper or assume the graph profile is active.
- Secrets/config via env only (NEO4J_AUTH, bolt URL in .env/.env.example). API host port 8001; container-internal 8000.
- Generated artifacts live under gitignored `workspaces/` (Phase-1 scaffold).

### Integration Points
- New routers in `app/main.py`; new Neo4j driver in lifespan; new alembic migrations; `shared/events/` Pydantic schemas; `infra/docker-compose.yml` neo4j trim; `infra/scripts/graph_mode.*` helper; `workspaces/<run_id>/` generated `.feature` + `.py` spec.

</code_context>

<specifics>
## Specific Ideas

- The memory math is a hard constraint, not a guideline: with web stopped, postgres+redis+api+neo4j(1g)+saucedemo ≈ 2.9g under the 3g WSL cap. Neo4j at 2g would blow it — D-02's trim is mandatory, and the graph_mode helper (D-03) must stop web BEFORE starting neo4j.
- "Honest stubs" means the contract is real (OpenAPI-documented) but the behavior returns 501 — never fabricated results. The slice must not look more complete than it is.
- One run_id should thread the whole slice so traceability (a Phase-10 requirement) has a seam from day one.

</specifics>

<deferred>
## Deferred Ideas

- **Intelligent/LLM-driven exploration, perception, budgets, risk policy, element fingerprints** → Phase 4 (Explorer). The tracer's deterministic crawl is explicitly a placeholder.
- **LangGraph + langgraph-checkpoint-postgres** → Phase 4 (no loop to orchestrate yet; D-08).
- **Real Knowledge Graph: single-writer service, idempotent fingerprint MERGE, freshness, flow mining** → Phase 5. Tracer uses minimal direct Cypher writes.
- **RabbitMQ broker + aio-pika workers + suite tiers + per-step artifacts** → Phase 7. Tracer uses in-process BackgroundTasks against the same message schemas (D-04/D-05).
- **Review queue + N-run stability for generation; healing; defect/Jira; dashboards/coverage/traceability UI** → Phases 6/8/9/10. Tracer ships honest 501 stubs for heal/create-defect/flows/coverage/dashboard.
- **Neo4j memory tuning + possibly more RAM / managed Neo4j** → revisit at Phase 5 when the real KG sizing is known; the tracer's 1g trim is a tracer-only setting.

None of these block Phase 3 — discussion stayed within the tracer-bullet scope.

</deferred>

---

*Phase: 3-Tracer Bullet — Minimal End-to-End Loop*
*Context gathered: 2026-06-13*
