---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
stopped_at: Completed 07-03 (evidenced+historied tier runs; /api/executions single owner; EXEC-04/05)
last_updated: "2026-06-21T23:15:38.825Z"
last_activity: 2026-06-21
progress:
  total_phases: 11
  completed_phases: 7
  total_plans: 32
  completed_plans: 32
  percent: 64
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-11)

**Core value:** Autonomous discovery — point the platform at a URL with credentials and it maps the application, learns its workflows, and builds the knowledge graph by itself.
**Current focus:** Phase 07 — execution-engine-workers

## Current Position

Phase: 07 (execution-engine-workers) — EXECUTING
Plan: 5 of 5
Status: Phase complete — ready for verification
Last activity: 2026-06-21

Progress: [██████████] 100%

## ⚠ REMEMBER for Phase 06 (BDD generation)

gherkin-official is 29.x TRANSITIVE via pytest-bdd 8.1 (hard-pins <30); a direct gherkin-official==40.* pin is INCOMPATIBLE (CLAUDE.md stack table is WRONG). Phase 3 already validates Gherkin with `from gherkin.parser import Parser` (the 29.x parser pytest-bdd uses). See memory gherkin-pytest-bdd-conflict.

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
| Phase 05 P05-01 | 12min | 3 tasks | 9 files |
| Phase 05 P05-02 | ~15min | 3 tasks | 7 files |
| Phase 05 P05-03 | 23min | 2 tasks | 21 files |
| Phase 05 P05-04 | 30min | 2 tasks | 7 files |
| Phase 06 P06-01 | 45min | 3 tasks | 16 files |
| Phase 06 P02 | ~55min | 2 tasks | 14 files |
| Phase 06 P03 | ~12min | 2 tasks | 14 files |
| Phase 07 P01 | ~1h | 3 tasks | 19 files |
| Phase 07 P02 | 45m | 2 tasks | 5 files |
| Phase 07 P05 | ~25min | 2 tasks | 4 files |
| Phase 07 P03 | ~2h | 2 tasks | 11 files |
| Phase 07 P04 | continuation | 3 tasks | 18 files |

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
- [Phase 05]: 05-01: kg/writer.py is the SINGLE Neo4j write path (KG-05) — explorer persist node delegates, holds zero Cypher; a Cypher-syntax-scoped grep gate enforces it without false-positiving docstring prose
- [Phase 05]: 05-01: idempotent fingerprint-MERGE backed by REQUIRE p.fingerprint IS UNIQUE; ON CREATE first_seen / ON MATCH last_verified + coalesce; first_seen immutable; ensure_constraints GRACEFUL (no-raise when neo4j down)
- [Phase 05]: 05-01: writer fns take optional driver kwarg (defaults to get_neo4j singleton) for host-driver test injection; KG-05 element-repository read half deferred to 05-02 (not marked complete)
- [Phase ?]: KG risk lives in kg/risk.py (pure frozen tunable weights, no LLM); new test at tests/unit/test_kg_risk.py to not clobber explorer test_risk.py
- [Phase ?]: Flow categorization degrades to a deterministic name on ANY gateway failure (incl. no-key provider auth error) so flows + risk render without provider keys
- [Phase ?]: Flow mining bounds enforced in Python over reader.flows_source (no variable-length Cypher), so the A4 path-range caveat is moot
- [Phase ?]: 05-03: KG read API real (D-06) + tabular browse UI (D-05) built to 05-UI-SPEC; coverage honest measured=false until slice 04; routers/kg.py+schemas/kg.py extensible by 05-04; element keys percent-encoded over {key:path}; zero new frontend deps
- [Phase ?]: [Phase 05]: 05-04: ground-truth coverage fixture DEPLOYED inside the app package (kg/ground_truth/saucedemo.json) because tests/ is .dockerignore'd + api has no source mount; byte-identical diffable copy under tests/fixtures, pinned in sync by a unit test (D-07)
- [Phase ?]: [Phase 05]: 05-04: PURE coverage metric (matched/total, fp-primary + normalized-URL path-only fallback so in-cluster vs public hosts match); GET /coverage real + honest measured=false when no graph; live >=80% Manual-Only [graph,live_llm] (QUAL-01)
- [Phase ?]: [Phase 06]: 06-01: GenerationError lives in gates/gherkin_lint.py and is re-imported by generation.py so generation AND the future edit/approve router share ONE linter + ONE exception (D-04)
- [Phase ?]: [Phase 06]: 06-01: structured Then->KG no-vacuous gate validates edge_type against kg/schema allow-list BEFORE building Cypher and injects the CONSTANT (never the LLM string); unknown kind / disallowed edge_type run NO query (injection-safe, T-06-01)
- [Phase ?]: [Phase 06]: 06-01: generate_scenarios is gateway-only (generate.bdd) with a deterministic no-key fallback whose single Then asserts the flow terminal page (resolvable); validate-before-persist (lint THEN no-vacuous) before any draft row write
- [Phase ?]: [Phase 06]: 06-02: review router re-runs BOTH gates on edit AND approve (422+no-save on fail, D-02/D-04); per-Then results honest server-authoritative (never fabricated green, D-03); risk+resolution best-effort/asyncio.wait_for-bounded so a down graph never hangs a mutation
- [Phase ?]: [Phase 06]: 06-02: ScenarioDetail exposes raw then_refs so edit-save re-validates the row's own refs server-side; Gherkin editor is a token-styled NATIVE textarea (zero shadcn add, zero new frontend dep)
- [Phase ?]: [Phase 06]: 06-03: freehand-selector AST gate walks Call nodes for selector sinks (page.locator/get_by_* with a Constant str first arg) + a raw CSS/XPath regex fallback; page-object modules are the single sanctioned literal home (allowlist) and each literal is asserted equal to a repo chain entry
- [Phase ?]: [Phase 06]: 06-03: codegen.generate_project renders the WHOLE tree in memory, ast.parse + selector-gates EVERY .py, writes only after all pass (no partial write); locators are TEMPLATE LOOKUPS from the Element Repository top chain entry, never LLM slots; reads list_approved only (D-01)
- [Phase ?]: [Phase 06]: 06-03: POST /generate-scripts rewired from the Phase-3 plain-spec to the approved-scenario PROJECT codegen; test_login.py.j2 + generation.generate_scripts retained for planted-spec/execute proofs (codegen-tree execution integration is Phase 7)
- [Phase ?]: 07-01: Execution worker reuses stability._run_spec_once VERBATIM for the subprocess runner; spec_path is run_id-derived, never from the AMQP body (T-07-01); prefetch_count=2 hard-bounds Chromium under the 3GB cap
- [Phase ?]: 07-02: tier-marker registration lives in conftest.py.j2 pytest_configure (no new template; rides _render_checked_py gate)
- [Phase ?]: 07-02: risk-based ranks build_flows per-flow records (real graph risk_score), never a direct risk_score() call; bounded by asyncio.wait_for(3.0s) honest-empty
- [Phase ?]: 07-02: resolve_tier validates against allow-list, returns a COPY of constant tokens (T-07-05); unknown->ValueError->422
- [Phase ?]: 07-05: CI parity is same-engine start-then-poll (D-08) — run-suite.yml POSTs /api/executions + polls GET /api/executions/{run_id}, passed->0 failed/killed->1, never pytest in CI; scoped CI_TOKEN bearer from secrets, never echoed (route-level check is 07-03)
- [Phase ?]: 07-05: determinism (SC5) = planted spec run twice via _run_spec_once with reset_target.py between runs; compare exit_code/passed/verdict only, exclude timing (result surface=={passed,exit_code,output}); keyless + neo4j off
- [Phase ?]: 07-03: worker 2x retry loop + per-step capture under run_dir(run_id)/<flow_id>/; TestArtifact.path run-relative multi-segment (kind screenshot|trace|video only, W4 (a)); pure classify_retry (passes-on-retry->flaky, all-fail->product)
- [Phase ?]: 07-03: /api/executions is the SINGLE owner (B1) — POST 202 tier round-trip + GET history/status; legacy RunStatus namespaced at /{run_id}/legacy-status so exactly one handler per (method,path) (T-07-18); I1 router gate accepts cookie OR scoped ci_token bearer (hmac.compare_digest, never logged)
- [Phase ?]: 07-03: api container image was stale (built before 07-01 added aio-pika); rebuilt via uv sync --frozen since exec_service now imports at app startup via the registered executions router (Rule 3 blocking, no new package)
- [Phase 07]: 07-04: Executions trends derived client-side from the server runs list (no backend trends route); recharts is the one sanctioned frontend dep

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

Last session: 2026-06-21T23:13:38.993Z
Stopped at: Completed 07-03 (evidenced+historied tier runs; /api/executions single owner; EXEC-04/05)
Resume file: None

ENVIRONMENT FACTS (2026-06-13):

- Host has 5.7 GB RAM; %USERPROFILE%\.wslconfig tuned to memory=3GB/processors=2/swap=4GB (16GB template value wedged the WSL VM; required reboot)
- API host-facing port is 8001 (host 8000 permanently held by another local project's auto-starting container, user's choice); container-internal port stays 8000
