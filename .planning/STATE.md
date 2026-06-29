---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
stopped_at: "Phase 10 COMPLETE — 6 plans executed + verified (deterministic PASS 458 tests; 26 e2e; one gated dep elasticsearch[async]; zero frontend deps). 3 Manual-Only: live-data dashboards, live-ES round-trip, 3GB memory-fit"
last_updated: "2026-06-29T10:33:26.666Z"
last_activity: 2026-06-29
progress:
  total_phases: 11
  completed_phases: 10
  total_plans: 48
  completed_plans: 48
  percent: 91
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-11)

**Core value:** Autonomous discovery — point the platform at a URL with credentials and it maps the application, learns its workflows, and builds the knowledge graph by itself.
**Current focus:** Phase 10 — dashboards-rbac-coverage-traceability

## Current Position

Phase: 10 (dashboards-rbac-coverage-traceability) — EXECUTING
Plan: 6 of 6
Status: Phase complete — ready for verification
Last activity: 2026-06-29

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
| Phase 08 P01 | 12min | 2 tasks | 9 files |
| Phase 08 P02 | 33min | 3 tasks | 8 files |
| Phase 08 P03 | 26min | 3 tasks | 11 files |
| Phase 08 P04 | 50min | 1 tasks | 1 files |
| Phase 08 P05 | ~20min | 2 tasks | 6 files |
| Phase 09 P01 | 25min | 3 tasks | 15 files |
| Phase 09 P02 | ~40min | 2 tasks | 1 files |
| Phase 09 P03 | 9min | 3 tasks | 10 files |
| Phase 09 P04 | ~35min | 3 tasks | 9 files |
| Phase 9 P05 | 40 | 3 tasks | 9 files |
| Phase 10 P01 | ~30min | 3 tasks | 12 files |
| Phase 10 P02 | ~35min | 3 tasks | 9 files |
| Phase 10 P03 | ~7min | 2 tasks | 5 files |
| Phase 10 P05 | ~13min | 3 tasks | 11 files |
| Phase 10 P04 | 21 | 3 tasks | 17 files |
| Phase 10 P06 | ~30min | 3 tasks | 12 files |

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
- [Phase ?]: 08-02: THE CRUX — heal runs IN-SPEC (worker has no live page handle); _healing.py VENDORS the byte-equivalent plan-01 scorer (drift guard); _resolve(element_key) heals on a locator miss
- [Phase ?]: 08-02: candidate enumeration is element-specific (broken tag + lower chain tiers) so a removed element yields 0 candidates -> uniqueness gate (count!=1) forces fail_as_defect, never a coincidental unique heal
- [Phase ?]: 08-02: reconcile_verdict — journal'd auto_heal -> auto_healed (overrides passed/flaky); additive String(16) verdicts, SC3 import-pure; wired into job.py in 08-03
- [Phase ?]: 08-02: page-object _chains/_element_meta render as Python literals via a pyrepr filter (not tojson null) and stay plain DATA dicts, not selector sinks (MED-1)
- [Phase ?]: 08-03: heal-as-commit (D-03, NOT git) = heal_audit row + ast-validated attr-keyed page-object rewrite + KG Element-history append via new single-writer append_element_history (MATCH-only, read-back 0-count RAISE)
- [Phase ?]: 08-03: MED-3 element_key->page-module resolved by SCAN of pages/*.py for the self.<attr> = page.locator( line (no re-open of 08-02 journal/template)
- [Phase ?]: [Phase 08]: 08-04 (QUAL-02): live mutation harness proves benign_heal_rate=4/4=1.00 (>=0.90) + false_heal_rate=0/2=0. MED-2 retune: proof band _MUTATION_HIGH=0.15 (window 0.06<band<=0.21); confidence.py untouched + byte-equivalent. BREAK_REMOVE held by the BAND (leftover count==1, conf 0.06), BREAK_DUPLICATE by the uniqueness gate (count==2). Inner runner uses python -m pytest (Windows Application Control blocks pytest.exe shim, os error 4551); stability.py untouched.
- [Phase ?]: 08-05: list status default is 'quarantine' (heal_audit outcome value) not plan's 'quarantined' (Rule-1 fix); heal_success_rate excludes reviewed_outcome='rejected' (a rejected heal is never a success)
- [Phase ?]: 08-05: apply reuses Plan-03 ast-validated ingest._apply_page_object_rewrite + single-writer KG append verbatim (T-08-20/21); reject is a reviewed_outcome flag flip; /api/heals router-level get_current_user gates every endpoint (no require_role DI exists)
- [Phase 09]: 09-01: defect class/confidence DECISION is deterministic + keyless (D-01) — pure classify() over an evidence dict; the LLM enriches Jira prose only, never the decision (NO-LLM grep gate over app/services/defects/)
- [Phase 09]: 09-01: infra_health is a PURE error-pattern signal (RESEARCH Open-Q2 b) over the error text — no live Docker probe (deferred to Phase 11); ClassifierWeights are FROZEN 60/20/-15 starting points the QUAL-03 harness tunes in Plan 02
- [Phase 09]: 09-01: error_text persistence gap closed — job.py persists the last attempt's output on TestResult with NO new imports (no-llm-in-worker gate green); gather_evidence ORM-joins error_text + heal_audit + test_artifacts on a PASSED-IN session (caller owns SessionLocal)
- [Phase 09]: 09-02 (QUAL-03/DEF-03): keyless 3-class accuracy harness (product_defect=SEED_BUG@8081, automation=un-healed BREAK_REMOVE@8086, infrastructure=NET-NEW dead-port/forced-timeout fault — the _port_open inverse, no build) over REAL-run evidence -> accuracy 10/10=1.00 (>=0.85). Per-class confidences product=80 / automation=100 / infra=80,80,80,60; autonomous-filing separation window (0,80]. The shipped jira_confidence_threshold=70 is ALREADY in-window -> NO retune; config.py + classifier.py frozen weights UNTOUCHED (the 08-04 retune precedent applies only IF the window demands it). Asserted via `_THRESHOLD=_settings.jira_confidence_threshold` (the QUAL-02 `_MUTATION_HIGH` discipline — config can't drift from the proof, T-09-05). neo4j OFF; `uv run python -m pytest` (Windows AppControl).
- [Phase ?]: 09-03: AtlassianJira builds the atlassian.Jira client lazily (only when configured) so import/construction is boot-safe without a token
- [Phase ?]: 09-03: describe() short-circuits to the deterministic fallback when no provider key is set — the gateway is never called keyless (D-01 prose-only)
- [Phase ?]: 09-03: JIRA-01/03/04 contract is keyless-CI via a hand-written FakeJira behind the JiraGateway Protocol; live Jira filing/dedup is Manual-Only
- [Phase 09]: 09-04: may_autofile = settings.jira_autonomous_enabled AND conf >= settings.jira_confidence_threshold (never a literal); flag-off OR below-threshold NEVER files — the core JIRA-02/D-04 safety gate, proven across the truth table over FakeJira
- [Phase 09]: 09-04: file_or_update returns FileResult(action, jira_key, counter) — updates are free (no cap consumption), creates consume one slot, at-cap MISS returns action='none' and the draft persists (Pitfall 5); the fp-<hash> JQL is server-built (no user text, T-09-13); artifact paths run_id-derived via the executions.py containment guard (T-09-15)
- [Phase 09]: 09-04: /api/defects (auth-gated list/detail/calibration/apply/reject, registered after heals_router) reuses pipeline.file_or_update + _severity_priority so the human-apply path is byte-identical to the autonomous-file path; run_defect_pipeline commits the draft (JIRA-04 run_id/flow_id link) BEFORE any Jira call so a cap/autonomy/gateway outcome never loses the classification
- [Phase ?]: 09-05: Defects review-queue UI shipped to 09-UI-SPEC over /api/defects (list+filters+calibration panel+detail apply/reject); token-styled confidence meter banded off the server threshold; zero new shadcn/deps; 14-test mocked-API e2e green
- [Phase 10]: 10-01 (PLAT-04): role read OFF THE ROW per request via require_role(*roles) composing on get_current_user — NOT in the JWT (create_token untouched); a role change takes effect next request, no stale-role window (D-01/A1, T-10-03/04)
- [Phase ?]: 10-01: users.role String(16) NOT NULL server_default='admin' (migration 0010, down_revision='0009') so the seeded admin is Admin with no backfill; seed_admin sets role='admin' explicitly
- [Phase ?]: 10-01: static rbac.ROLE_PERMISSIONS map (NOT a table, D-01) + can(role,cap) + endpoint->role matrix in rbac.py for Plans 02-05; RoleAssignRequest Literal 422s invalid roles; self-demote 400 lockout guard before target lookup; users_router before stubs
- [Phase ?]: [Phase 10]: 10-02: DASH-04 lifecycle coverage (discovered ∩ approved-scenario ∩ passing-execution) is a DISTINCT module from kg/coverage.py — imports nothing from it, ships its own honest definition (Pitfall 5/T-10-11); no 'failed' verdict (failed=product_failure|aborted, LOW-1); pass_rate 0..1->0..100 percent converted once in dashboards.executive (LOW-2); per-route require_role for differing role sets; exec/qa/dev aggregations reuse exec_history verbatim
- [Phase ?]: [Phase 10]: 10-03 (DASH-05): read-time cross-store traceability join — chain(db, *, flow_id/run_id/scenario_id/defect_id) resolves run_id+flow_id from any one entry id then assembles flow(READ-only mine)↔scenario↔script(convention-derived from run_id A4)↔execution↔defect(jira_key); honest gaps, graph-down→flow=null+note (never 500), ZERO graph writes guarded by a no-write-Cypher source-gate test; GET /api/traceability role-gated (admin,qa_lead,developer), exactly-one-entry-id 422, unknown id→200 honest empty (not 404)
- [Phase 10]: 10-05 (PLAT-04/DASH-01..03): role-gated sidebar nav + the three dashboards UI to 10-UI-SPEC over the Plan-02 payloads. lib/rbac.ts ROLE_NAV+canSee() mirrors the API rbac.py matrix (UX-ONLY; the API require_role is the boundary — a 403 renders <NoAccess>, never the data); the flat "Dashboards" nav item resolves to the highest-privilege dashboard the role may open; KPI meter = styled-native role=progressbar with SERVER-driven bands (gap=muted remainder vs failure=red); the two coverage metrics are SEPARATE executive tiles (Pitfall 5/T-10-26); QA artifact links are auth-gated /api/executions/{run}/artifacts/{flow}/{kind} URLs via the Phase-7 artifactUrl (3 real kinds screenshot|trace|video + trace note, never raw paths, T-10-24); recharts/table/ClassBadge reused, ZERO new frontend deps; 13-test mocked-API e2e green
- [Phase ?]: 10-04: gated elasticsearch[async]==9.4.* — the async extra (aiohttp) enables the approved AsyncElasticsearch interface (the greenlet-for-SQLAlchemy precedent), not a new package choice
- [Phase ?]: 10-04: on-write index swallow-and-log wraps client construction too so an ES outage never breaks the Postgres write (T-10-19); ES-down search bubbles to an honest 503, never a fake empty list (T-10-20)
- [Phase ?]: 10-06: final Phase-10 UI slice (DASH-04/05/06 + PLAT-04 admin) — coverage panel (two metrics SEPARATE), traceability viewer (ordered chain + honest gaps), search UI (SAFE-parsed highlight + 503-distinct-from-empty), admin role-assign (self-demote guard + confirm dialog + no optimistic update + success-only toast); URL-as-source avoids setState-in-effect; ZERO new frontend deps; 17-test mocked e2e green

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

Last session: 2026-06-29T10:33:26.631Z
Stopped at: Phase 10 COMPLETE — 6 plans executed + verified (deterministic PASS 458 tests; 26 e2e; one gated dep elasticsearch[async]; zero frontend deps). 3 Manual-Only: live-data dashboards, live-ES round-trip, 3GB memory-fit
Resume file: None

ENVIRONMENT FACTS (2026-06-13):

- Host has 5.7 GB RAM; %USERPROFILE%\.wslconfig tuned to memory=3GB/processors=2/swap=4GB (16GB template value wedged the WSL VM; required reboot)
- API host-facing port is 8001 (host 8000 permanently held by another local project's auto-starting container, user's choice); container-internal port stays 8000
