---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: completed
stopped_at: "Phase 4 planned (4 slices, checker-passed + revised: H-1/H-2/M-1/M-2/L-2/L-3); ready to execute"
last_updated: "2026-06-15T08:09:54.282Z"
last_activity: 2026-06-15 -- Phase 03 complete (PLAT-02; tracer loop end-to-end)
progress:
  total_phases: 11
  completed_phases: 3
  total_plans: 19
  completed_plans: 15
  percent: 27
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-11)

**Core value:** Autonomous discovery — point the platform at a URL with credentials and it maps the application, learns its workflows, and builds the knowledge graph by itself.
**Current focus:** Phase 04 — Explorer Agent (full autonomous exploration) — next up

## Current Position

Phase: 03 (Tracer Bullet) — ✅ COMPLETE (verified passed 4/4, 2026-06-15)
Plan: 4 of 4 complete
Status: Phase 03 complete — ready to discuss/plan Phase 04
Last activity: 2026-06-15 -- Phase 03 complete (PLAT-02; tracer loop end-to-end)

Progress: [███░░░░░░░] 27% (3 of 11 phases)

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

Last session: 2026-06-15T08:09:54.231Z
Stopped at: Phase 4 planned (4 slices, checker-passed + revised: H-1/H-2/M-1/M-2/L-2/L-3); ready to execute
Resume file: .planning/phases/04-explorer-agent/04-01-PLAN.md

ENVIRONMENT FACTS (2026-06-13):

- Host has 5.7 GB RAM; %USERPROFILE%\.wslconfig tuned to memory=3GB/processors=2/swap=4GB (16GB template value wedged the WSL VM; required reboot)
- API host-facing port is 8001 (host 8000 permanently held by another local project's auto-starting container, user's choice); container-internal port stays 8000
