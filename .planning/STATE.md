---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: phase-complete
stopped_at: Phase 04 code-complete + deterministically verified (201 backend + frontend e2e green); LIVE LLM exploration is the pending Manual-Only gate (provider keys empty). Next: Phase 05 (Knowledge Graph) OR add provider keys to live-demo the Explorer.
last_updated: "2026-06-15T18:45:00.000Z"
last_activity: 2026-06-15 -- Phase 04 complete (EXPL-01..09; explorer logic verified; live demo needs API key)
progress:
  total_phases: 11
  completed_phases: 4
  total_plans: 19
  completed_plans: 19
  percent: 36
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-11)

**Core value:** Autonomous discovery — point the platform at a URL with credentials and it maps the application, learns its workflows, and builds the knowledge graph by itself.
**Current focus:** Phase 05 — Knowledge Graph & Flow Learning — next up (or live-demo the Explorer with a provider key first)

## Current Position

Phase: 04 (Explorer Agent) — ✅ CODE-COMPLETE + deterministically verified (2026-06-15); live LLM exploration pending provider keys (Manual-Only gate)
Plan: 4 of 4 complete
Status: Phase 04 done (logic verified); ready for Phase 05
Last activity: 2026-06-15 -- Phase 04 complete (EXPL-01..09)

Progress: [████░░░░░░] 36% (4 of 11 phases)

## ⚠ Project-wide note (from Phase 04)
From Phase 04 onward the platform's core value (autonomous LLM-driven discovery) requires a provider API key to DEMONSTRATE. Code is built + unit/integration-verified deterministically (mocked gateway), but the live autonomous behavior — and the live-verification half of Phases 4-9 — needs ANTHROPIC_API_KEY or OPENAI_API_KEY in .env. Decide whether to add a key before Phase 5 to live-prove the loop, or continue building + deterministically verifying and batch the live demos later.

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P03 | ~12min | 2 tasks | 13 files |
| Phase 01 P04 | ~26min | 3 tasks | 48 files |
| Phase 01 P05 | ~15min | 2 tasks | 10 files |
| Phase 01 P06 | ~35min | 3 tasks | 8 files |
| Phase 01 P01-07 | ~12min | 2 tasks | 5 files |
| Phase 02 P01 | 40min | 3 tasks | 15 files |
| Phase 02 P02-03 | ~16m | 2 tasks | 9 files |
| Phase 03 P01 | ~9min | 2 tasks | 9 files |
| Phase 03 P03-02 | 20min | 3 tasks | 17 files |
| Phase 03 P03-03 | 70min | 3 tasks | 5 files |
| Phase 03 P04 | ~95min | 3 tasks | 15 files |
| Phase 04 P04-01 | 75min | 2 tasks | 19 files |
| Phase 04 P04-02 | 15min | 3 tasks | 11 files |
| Phase 04 P04-03 | 10min | 3 tasks | 10 files |
| Phase 04 P04 | 60 | 3 tasks | 22 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 11-phase vertical-slice structure adopted from research dependency spine (Foundation → LLM Gateway → Tracer Bullet → Explorer → KG → Generation → Execution → Healing → Defect+Jira → Dashboards → Hardening)
- [Roadmap]: Staggered infra activation — Phase 1 runs only Postgres + Redis; Neo4j enters Phase 3, RabbitMQ/MinIO Phase 7, Elasticsearch Phase 9/10, Prometheus/Grafana/K8s Phase 11
- [Roadmap]: LLM gateway with budgets/kill-switch built BEFORE any agent (Phase 2) so no agent can spend unmetered money
- [Roadmap]: Trust gates are phase launch requirements — draft-mode Jira, heal audit trails, ground-truth harnesses (QUAL-01/02/03 mapped to Phases 5/8/9)
- [Roadmap]: REQUIREMENTS.md actually contains 57 v1 REQ-IDs (initial count of 49 was incorrect); all 57 mapped
- [Phase ?]: 01-03: JWT tokens carry a jti claim beyond sub/type/iat/exp — 1s iat resolution made same-second refresh rotation unobservable
- [Phase ?]: 01-03: pydantic[email] extra adopted (EmailStr requires email-validator); test data must avoid special-use TLDs which 422 at the schema boundary
- [Phase 01]: 01-04: shadcn CLI 4.x dropped init style/base-color flags — manual components.json path used to honor the locked UI-SPEC preset (new-york/zinc/CSS variables)
- [Phase 01]: 01-04: hybrid-mode Next rewrite fallback is http://localhost:8001 per the 01-02 host-port decision (Next does not read repo-root .env)
- [Phase 01]: 01-06: added api.patch to client wrapper (targets uses PATCH) and mounted sonner Toaster in dashboard layout (installed in 01-04 but never hosted)
- [Phase ?]: [Phase 01]: 01-07: saucedemo healthcheck uses 127.0.0.1 not localhost — container localhost resolves to ::1 (IPv6) but nginx listens IPv4-only
- [Phase ?]: [Phase 01]: 01-07: node:16 base IS the OpenSSL-3 mitigation; --openssl-legacy-provider removed (node:16 rejects it in NODE_OPTIONS)
- [Phase ?]: [Phase 02]: 02-01: usage-event token keys must avoid the substring 'token' (SENSITIVE regex) — tokens_in/tokens_out still redact; used tok_in/tok_out
- [Phase ?]: [Phase 02]: 02-01: pricing keyed on bare model name; lookup_price normalizes the provider-prefixed init_chat_model string via _bare_model (FIX-1)
- [Phase ?]: [Phase 02]: 02-01: LLM_DEFAULT_MODEL required — wired into compose api env (compose does not pass whole .env); provider keys empty placeholders
- [Phase ?]: Custom Redis response cache (not native LangChain cache): SHA-256 exact-match key, temp==0-only, env TTL, $0 cache_hit ledger row, checked AFTER kill-switch so a halt refuses hits (D-06)
- [Phase ?]: Two-provider live_llm parity test (Anthropic+OpenAI by config alone) gated off the default suite via skipif + budget-raising fixture; proves PLAT-05 Success Criterion 1
- [Phase 03]: 03-01: gherkin-official is 29.x TRANSITIVE via pytest-bdd 8.1 (which hard-pins gherkin-official>=29,<30) — a direct gherkin-official==40.* pin is INCOMPATIBLE. CLAUDE.md stack table (gherkin-official 40.x) is WRONG and should be corrected. Standalone Gherkin validation imports the SAME parser pytest-bdd uses (from gherkin.parser import Parser).
- [Phase 03]: 03-01: neo4j driver opens LAZILY (AsyncGraphDatabase.driver does not connect until first session) so init_neo4j() never blocks startup when neo4j is down; api has NO depends_on:neo4j (graph-profile-gated). Verified api boots healthy with neo4j absent.
- [Phase 03]: 03-01: graph_mode helper stops web (1.5g) BEFORE starting neo4j — VERIFIED neo4j reaches healthy at ~1.14GB total, well under the 3GB WSL cap. After graph_mode down, callers must stop neo4j before relying on the full default stack (web+neo4j together exceed headroom).
- [Phase 03]: 03-01: neo4j compose mem env-var underscore-doubling (Pitfall 1): NEO4J_server_memory_heap_max__size (DOUBLE) / NEO4J_server_memory_pagecache_size (single).
- [Phase ?]: 03-02: get_status_by_run_id is the single run_id-keyed poll surface — Execution row for execute-path run_ids else the Run row for explore-path run_ids (FIX 1).
- [Phase ?]: 03-02: shared/ mounted (not COPY-d) into the api container at /app/shared because it is outside the apps/api build context; pyproject pythonpath adds the repo root for host tests, so import shared.events resolves identically in container and host.
- [Phase ?]: 03-02: chromium plus OS libs baked into the api image via playwright install --with-deps; playwright promoted from transitive dev dep to runtime pin; alembic/ bind-mounted so new migrations reach the self-migrating entrypoint without a rebuild.
- [Phase ?]: 03-03: generation routes both generate-bdd and generate-scripts through llm_gateway.complete() with the explore run_id (D-07) — no direct provider call; gherkin-official validates the .feature before any write; the Jinja2 skeleton owns all spec structure and selectors (LLM fills only narrow slots, Pitfall 5).
- [Phase 03]: 03-04: /execute discovers the run's spec by the workspaces/<run_id>/test_login.py filesystem convention (404 if absent, FIX 3) and runs it ONLY via asyncio.create_subprocess_exec (argv list, no shell) — never in-process pytest (Pitfall 3); spec_path is run_id-derived, never client input (T-03-15); the runner finishes the run_id-keyed Execution row (FIX 1).
- [Phase 03]: 03-04: the 10-endpoint PLAT-02 surface is completed with 5 honest 501 stubs (heal/create-defect/flows/coverage/dashboard) carrying documented OpenAPI contracts but NEVER fabricated results (T-03-19) — PLAT-02 now COMPLETE.
- [Phase 03]: 03-04: workspaces root + execution cwd are settings-driven (WORKSPACES_DIR=/app/workspaces, EXECUTION_CWD=/app in-container) with the host workspaces/ bind-mounted; fixes a latent 03-03 parents[4] resolution that never worked in the container and lets generate WRITE / execute DISCOVER+RUN the same spec. uvicorn --reload scoped to --reload-dir app so spec/artifact writes don't restart the server mid-run.
- [Phase ?]: explorer.py relocated to explorer/driver.py (package/module name collision); run_explore re-exported from __init__.py
- [Phase ?]: ExploreBudget bound into converge via closure, never in the checkpointed JSON-serializable ExplorerState (H-1)
- [Phase ?]: Graph discovery test marked graph+live_llm: in-container BackgroundTask drives the real gateway; skipped without a provider key
- [Phase 04]: 04-02: fingerprint hashing path is import-pure (AST-gated) — structural_fingerprint eats a {role/tag/attrs/children} tree; the live page->tree walk (page_fingerprint/_page_node_tree via page.evaluate) is a separate adapter so no playwright import enters the pure module
- [Phase 04]: 04-02: page_key is no longer the state dedup key — it now scopes only to the frontier (URL identity); fingerprint(...) is the converge/persist dedup key (EXPL-06)
- [Phase 04]: 04-02: convergence proof is a run_over_fixtures harness driving the REAL converge+fingerprint+budget over fixtures (not the live StateGraph, which needs a live page per node) — two runs collapse to an identical fingerprint set + stop_reason=saturation, zero spend
- [Phase 04]: 04-02: Rule-1 fix — the Slice-1 loop detector checked seen_pairs AFTER appending the current pair, so every first-occurrence step self-detected as converged; now check PRIOR pairs then record
- [Phase 04]: 04-02: mid-run relogin reuses creds cached on a per-run dict (auth._RUN_CREDS) set at first login and cleared in the driver finally — never a second decrypt, never on the serialized state (T-04-07)
- [Phase ?]: EXPL-01 live view: SSE via sse-starlette EventSourceResponse over Redis pub/sub (explore:{run_id}); snapshot-on-subscribe reconciles reconnects without replay
- [Phase ?]: Cooperative Stop (L-3) is a Redis cancel flag checked at the LangGraph loop top; durable/forceful cancel deferred to Phase 7
- [Phase ?]: First apps/web Playwright e2e harness added (@playwright/test 1.60.0); explore-live e2e is self-contained (mocks all /api + SSE), no backend/keys

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 3 memory — RESOLVED in 03-CONTEXT]: 5.7 GB host / 3GB WSL cap. Strategy locked (D-01/02/03): run neo4j LOCAL but trimmed (heap 512m/pagecache 256m/mem_limit 1g) behind the 'graph' profile; a scripted graph_mode helper STOPS web (1.5g) during graph work so postgres+redis+api+neo4j+saucedemo ≈ 2.9g fits under 3g. Re-evaluate sizing at Phase 5 (real KG). Elasticsearch (1.5g, Phase 9/10) is still an OPEN memory question for later.
- [Phase 4]: Most novel component (perception prompts, state-abstraction fingerprints, action risk heuristics) — plan with `--research-phase`
- [Phase 5]: Cypher schema + reconciliation strategy synthesized from research, no canonical reference — plan with `--research-phase`
- [Phase 8]: Similarity scoring weights/thresholds need experimentation — plan with `--research-phase`
- [Phase 9]: Confidence calibration methodology + hand-rolled ADF generation (no Python ADF library) — plan with `--research-phase`
- [General]: MFA/SSO target-app auth is a known limitation (v2 EXT-04); demo targets don't exercise it

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| docs/stack | Correct CLAUDE.md Browser-Automation stack table: gherkin-official is constrained to 29.x by pytest-bdd 8.1 (>=29,<30) — the listed 40.x is incompatible and must not be a direct pin | Open | 03-01 |

## Session Continuity

Last session: 2026-06-15 (opus)
Stopped at: Phase 04 COMPLETE (code + deterministic verification: 201 backend + frontend e2e green; pytest basename-collision fixed). Live LLM exploration = pending Manual-Only gate (keys empty). Next: /gsd-discuss-phase 5, OR add a provider key and run the Phase-4 live exploration demo first.
Resume file: None

ENVIRONMENT FACTS (2026-06-13):

- Host has 5.7 GB RAM; %USERPROFILE%\.wslconfig tuned to memory=3GB/processors=2/swap=4GB (16GB template value wedged the WSL VM; required reboot)
- API host-facing port is 8001 (host 8000 permanently held by another local project's auto-starting container, user's choice); container-internal port stays 8000
