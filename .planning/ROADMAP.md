# Roadmap: Autonomous QA Engineer Platform

## Overview

The journey runs along the data-flow spine the platform itself embodies: stand up a minimal foundation (auth, target-app registry, two services — not eight), put cost controls in place before any agent can spend money, then punch a thin tracer bullet through the entire pipeline (explore → graph → scenario → script → execution → result) against SauceDemo so compounding error rates are visible early. With the loop alive, each stage widens to spec depth in dependency order: the Explorer Agent (the core value), the Knowledge Graph and flow learning, quality-gated BDD/Playwright generation, the queue-fed execution plane, audited self-healing, confidence-gated defect intelligence with draft-mode Jira, then dashboards/RBAC/coverage over the accumulated data, and finally K8s/CI-CD/observability hardening. Every phase exits with something demonstrable end-to-end against a named target app, and trust features (budgets, draft modes, audit trails, ground-truth harnesses) are launch requirements of their phases, not polish.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation & Dev Environment** - Docker Compose core (Postgres + Redis), JWT auth, encrypted target-app registry, Next.js shell, snapshot-restorable SauceDemo target (completed 2026-06-13)
- [x] **Phase 2: LLM Gateway** - Provider-agnostic `init_chat_model` gateway with budgets, kill-switch, caching, and cost-per-operation logging
 (completed 2026-06-13)
- [x] **Phase 3: Tracer Bullet — Minimal End-to-End Loop** - Thin slice: explore SauceDemo → minimal graph → one scenario → one spec → one execution → result row; full REST API contract in place
 (completed 2026-06-14)
- [x] **Phase 4: Explorer Agent** - Full autonomous exploration: snapshot-first perception, budgets/loop detection, auth handling, risk policy, sanitized observations, element fingerprints
 (completed 2026-06-15)
- [x] **Phase 5: Knowledge Graph & Flow Learning** - Neo4j single-writer KG with idempotent MERGE and freshness, Element Repository, flow mining with risk scores, ground-truth coverage measurement
 (completed 2026-06-19)
- [ ] **Phase 6: BDD & Playwright Generation** - Quality-gated Gherkin and Playwright generation from the graph with approve/edit review and N-run stability acceptance
- [ ] **Phase 7: Execution Engine & Workers** - Suite tiers, RabbitMQ-distributed parallel Playwright workers, per-step artifacts, execution history, live run view with kill switch
- [ ] **Phase 8: Self-Healing Engine** - Three-outcome healing with audit diffs, graph write-back, and a mutation harness measuring true heal success and false-heal rate
- [ ] **Phase 9: Defect Intelligence & Jira Agent** - 3-way failure classification with calibrated confidence, draft-mode Jira with dedup and evidence, autonomous filing gated on measured precision
- [ ] **Phase 10: Dashboards, RBAC & Coverage/Traceability** - Executive/QA/developer dashboards, role enforcement, graph-derived coverage, full traceability chain, Elasticsearch-backed search
- [ ] **Phase 11: Hardening & Ops** - K8s manifests on Docker Desktop/kind, GitHub Actions CI/CD for platform images, Prometheus + Grafana domain metrics

## Phase Details

### Phase 1: Foundation & Dev Environment

**Goal**: A user can stand up the platform skeleton locally with one command, log in, and securely register a target application to explore
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: PLAT-01, PLAT-03, PLAT-07, INFRA-01, QUAL-04
**Success Criteria** (what must be TRUE):

  1. `docker compose up` brings up PostgreSQL, Redis, the FastAPI backend, and the Next.js web shell with passing healthchecks and per-container memory limits that hold on Windows 11/Docker Desktop (other services exist as inactive compose profiles)
  2. User can log in to the platform with email/password and stays authenticated across requests via JWT
  3. User can register a target application (name, URL, credentials, exploration rules) through both the API and the UI, and see it listed
  4. Target-app credentials are encrypted at rest and never appear in logs or API responses
  5. A self-hosted SauceDemo demo target runs in Docker and can be reset to a clean snapshot on demand

**Plans**: 8 plans
**UI hint**: yes

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Monorepo scaffold + Compose core (Postgres/Redis, dormant profiles, memory limits)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — FastAPI skeleton: settings, log redaction, async Alembic, /health, api container

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Auth slice: JWT cookie login/refresh/logout, seeded admin, functional tests

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-04-PLAN.md — Web shell: Next 16 login UI, proxy.ts, compose web, Playwright e2e (walking skeleton)

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 01-05-PLAN.md — Encrypted target registry API: Fernet write-only credentials, leak tests

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 01-06-PLAN.md — Target registry UI: table + dialog per UI-SPEC, Playwright e2e

**Wave 7** *(blocked on Wave 6 completion)*

- [x] 01-07-PLAN.md — Self-hosted SauceDemo target + generic reset-target contract

**Wave 8** *(blocked on Wave 7 completion)*

- [x] 01-08-PLAN.md — verify_stack evidence, dev docs, clean-state phase gate + human sign-off

### Phase 2: LLM Gateway

**Goal**: Every future LLM call flows through one provider-agnostic, budget-enforced gateway — no agent can spend money outside it
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: PLAT-05, PLAT-06
**Success Criteria** (what must be TRUE):

  1. The same gateway call runs against Anthropic and OpenAI with only a configuration change (verified parity run on both providers), using `init_chat_model` — no custom adapter layer
  2. Per-call, per-run, and per-day token/cost budgets stop execution when exceeded, and a hard kill-switch halts all LLM traffic immediately
  3. Every LLM operation logs tokens and cost, queryable per operation, with Redis response caching reducing repeat-call spend

**Plans**: 3 plans

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Provider-agnostic gateway call + effective-dated pricing + llm_usage ledger/usage-event (PLAT-05); package-legitimacy gate + Wave-0 mocked test scaffold

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — Budgets (pre-check/reconcile) + kill-switch (admin endpoint + daily auto-trip) over a shared Redis client (PLAT-06)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-03-PLAN.md — Custom Redis response cache (temp==0, $0 hit) + gated two-provider live parity test (PLAT-05/PLAT-06)

### Phase 3: Tracer Bullet — Minimal End-to-End Loop

**Goal**: One thin slice of the entire pipeline runs end-to-end against SauceDemo, proving the loop before any engine is built deep
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: PLAT-02
**Success Criteria** (what must be TRUE):

  1. POST /explore against registered SauceDemo produces real (even if minimal) Page/NavigatesTo nodes in Neo4j
  2. POST /generate-bdd and /generate-scripts produce one Gherkin scenario and one runnable Playwright spec from the explored graph
  3. POST /execute runs that spec and a result row lands in PostgreSQL, retrievable via GET /executions
  4. All spec'd REST endpoints (POST /explore, /generate-bdd, /generate-scripts, /execute, /heal, /create-defect; GET /flows, /coverage, /executions, /dashboard) exist with documented contracts — real where the slice covers them, honest stubs elsewhere — and queue message schemas live in `shared/events/`

**Plans**: 4 plans

Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Foundation: package gate + trimmed neo4j + lifespan driver + graph_mode helper + Wave-0 test scaffold

**Wave 2** *(blocked on Wave 1)*

- [x] 03-02-PLAN.md — Slice A: runs/executions model + shared/events + deterministic explore → Neo4j Page/NavigatesTo + GET /executions

**Wave 3** *(blocked on Wave 2)*

- [x] 03-03-PLAN.md — Slice B: generate-bdd + generate-scripts via the gateway → gherkin-validated .feature + Jinja2 runnable spec

**Wave 4** *(blocked on Wave 3)*

- [x] 03-04-PLAN.md — Slice C: /execute subprocess runner → result row + 5 honest 501 stubs (full 10-endpoint surface) + traceability tests

### Phase 4: Explorer Agent

**Goal**: User points the platform at a registered app and it autonomously maps pages, workflows, and elements — converging, staying safe, and staying on budget
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: EXPL-01, EXPL-02, EXPL-03, EXPL-04, EXPL-05, EXPL-06, EXPL-07, EXPL-08, EXPL-09
**Success Criteria** (what must be TRUE):

  1. User starts an exploration and watches a live progress view (pages found, actions taken, cost so far) streamed as it happens
  2. Explorer logs into the target app automatically (login-form detection, credential injection, storageState reuse) and recovers when logged out mid-run
  3. Exploring SauceDemo discovers its pages, forms, menus, buttons, links, and tables with a screenshot per state, and converges and stops within code-enforced budgets (steps, depth, revisits, wall-clock, tokens) on two consecutive runs — duplicate states collapsed by normalized DOM fingerprint, not URL
  4. Multi-step workflows and form validation rules are detected and recorded from the exploration
  5. Destructive actions are refused on targets not flagged as restorable sandboxes, navigation stays inside the origin allowlist with page content treated as delimited untrusted input, and every discovered element carries a prioritized locator chain (data-testid → aria-label → role → text → xpath) with history

**Plans**: 4 plans
**UI hint**: yes

Plans:
**Wave 1**

- [x] 04-01-PLAN.md — Slice 1: package gate + LangGraph StateGraph core loop (aria_snapshot perceive → gateway decide → act → Neo4j persist) + AsyncPostgresSaver checkpointer + budgets/loop (EXPL-03, EXPL-05 budgets)

**Wave 2** *(blocked on Wave 1)*

- [x] 04-02-PLAN.md — Slice 2: structural-skeleton fingerprint dedup + deterministic two-run convergence + auth (login detection, storageState reuse, relogin) (EXPL-06, EXPL-05 convergence, EXPL-02)

**Wave 3** *(blocked on Wave 2)*

- [x] 04-03-PLAN.md — Slice 3: deterministic risk classifier + origin allowlist + untrusted-content delimiting + locator chains/history + workflow/form-validation detection (EXPL-07, EXPL-08, EXPL-09, EXPL-04)

**Wave 4** *(blocked on Wave 3)*

- [x] 04-04-PLAN.md — Slice 4: ExploreProgressEvent + Redis pub/sub + sse-starlette SSE endpoint + Next.js live exploration view (UI-SPEC, zero new shadcn) (EXPL-01)

### Phase 5: Knowledge Graph & Flow Learning

**Goal**: Discovered structure becomes a queryable, idempotent, fresh knowledge graph that derives risk-scored business flows — measured against ground truth
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: KG-01, KG-02, KG-03, KG-04, KG-05, QUAL-01
**Success Criteria** (what must be TRUE):

  1. Exploration results persist in Neo4j as Page/Form/Workflow/Button/BusinessEntity nodes with NavigatesTo/Submits/Creates/Updates/Deletes edges, and the user can query and visually browse the graph from the UI
  2. Re-exploring an unchanged SauceDemo produces ~0 duplicate nodes (fingerprint-based MERGE) and updates first_seen/last_verified freshness fields on every node
  3. The Flow Learning Engine derives user journeys from the graph, categorizes them as business workflows, and assigns each flow a risk score visible to the user
  4. The KG writer service is the only Neo4j write path, and element fingerprints with locator history are queryable per element from the Element Repository
  5. Exploration coverage measured against the hand-labeled SauceDemo ground-truth graph exceeds 80%

**Plans**: 4 plans
**UI hint**: yes

Plans:
**Wave 1**

- [x] 05-01-PLAN.md — Single-writer + canonical schema + idempotent fingerprint-MERGE/freshness + explorer refactor + grep enforcement (KG-01/03/05 core)

**Wave 2** *(blocked on Wave 1)*

- [x] 05-02-PLAN.md — Element Repository read + bounded path-mining + pure risk formula + gateway flow categorization with deterministic no-key fallback (KG-04, KG-05 half)

**Wave 3** *(blocked on Wave 2)*

- [x] 05-03-PLAN.md — Real GET /flows + /coverage + /graph/pages/elements read API + tabular browse UI (Pages/Flows-risk/Element Repository) + sidebar nav (KG-02)

**Wave 4** *(blocked on Wave 3)*

- [x] 05-04-PLAN.md — Committed ground-truth fixture + deterministic coverage metric + real GET /coverage + Manual-Only ≥80% gate (QUAL-01)

### Phase 6: BDD & Playwright Generation

**Goal**: User turns discovered flows into reviewed, quality-gated Gherkin scenarios and stable Playwright automation they own
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: GEN-01, GEN-02, GEN-03, GEN-04, GEN-05
**Success Criteria** (what must be TRUE):

  1. User generates BDD features/scenarios (including scenario outlines with data-driven examples) from discovered SauceDemo flows
  2. Every generated Gherkin file passes the syntax lint gate and every Then step asserts an outcome recorded in the knowledge graph — no vacuous assertions
  3. Generated scenarios land in an approve/edit review queue in the UI, and only approved scenarios feed automation generation
  4. User generates Playwright page objects, specs, fixtures, utilities, and test data models in the spec folder structure (tests/ pages/ fixtures/ utils/ data/ reports/), with every locator sourced from the Element Repository — never freehand LLM selectors
  5. Generated tests pass an N-consecutive-run stability check before acceptance, and a seeded-bug build of the target makes them fail (they detect real breakage)

**Plans**: 4 plans
**UI hint**: yes

Plans:
**Wave 1**

- [x] 06-01-PLAN.md — Scenario generation + gates + model: scenarios table/migration 0006, structured Then→KG no-vacuous gate + gherkin lint, KG→Examples outlines, gateway+no-key fallback (GEN-01, GEN-03)

**Wave 2** *(blocked on Wave 1)*

- [ ] 06-02-PLAN.md — Review queue: auth-gated router (list/get/edit/approve/reject, both gates re-run on edit/approve) + review-queue UI to 06-UI-SPEC, only approved feed codegen (GEN-02)

**Wave 3** *(blocked on Wave 2)*

- [ ] 06-03-PLAN.md — Element-Repo codegen: Jinja2 project tree (pages/steps/features/fixtures/utils/data/reports), pytest-bdd bound to .feature, repo-sourced locators + freehand-selector AST gate (GEN-04, GEN-05 locator half)

**Wave 4** *(blocked on Wave 3)*

- [ ] 06-04-PLAN.md — Stability + seeded-bug: N-run stability (Phase-3 subprocess runner) + SEED_BUG build-arg/saucedemo-bug service + breakage-detection, planted-spec deterministic proof, OOM sequencing (GEN-05 stability half)

### Phase 7: Execution Engine & Workers

**Goal**: User runs tiered regression suites at scale — parallel, observable live, fully evidenced, and reproducible — locally, in Docker, and from CI
**Mode:** mvp
**Depends on**: Phase 6
**Requirements**: EXEC-01, EXEC-02, EXEC-03, EXEC-04, EXEC-05, EXEC-06
**Success Criteria** (what must be TRUE):

  1. User runs suites by tier — smoke, sanity, regression, full, and risk-based (selected from flow risk scores plus failure history)
  2. The same suite executes locally, in Docker, and from a GitHub Actions trigger with status reported back
  3. Tests run in parallel at browser and flow level via RabbitMQ-distributed stateless workers, with no LLM call anywhere in the execution loop
  4. Every run captures per-step screenshots, video, and console/network logs stored on the filesystem with paths in PostgreSQL, and execution history shows pass/fail trends, durations, and flaky-test detection (retries distinguish infra flake from product failure)
  5. User watches a live execution view with per-test progress and can kill a run mid-flight; two consecutive runs against a reset target produce identical results

**Plans**: TBD
**UI hint**: yes

### Phase 8: Self-Healing Engine

**Goal**: UI changes stop breaking the suite — locator failures heal automatically with full auditability, and healing provably never masks real defects
**Mode:** mvp
**Depends on**: Phase 7
**Requirements**: HEAL-01, HEAL-02, HEAL-03, HEAL-04, QUAL-02
**Success Criteria** (what must be TRUE):

  1. On locator failure, the engine finds alternatives via DOM similarity, visual similarity, accessibility attributes, and historical locator mapping, applying the priority chain (data-testid → aria-label → role → text → xpath) and re-validating against the live page
  2. Every healing attempt resolves to exactly one of three outcomes — auto-heal (high confidence), quarantine for review (medium), fail-as-potential-defect (low) — and assertions are never weakened to make a test pass
  3. Every heal is recorded as an auditable before/after diff with confidence score, updates the script repository (heal-as-commit), and writes back to the knowledge graph
  4. The benign-vs-breaking mutation harness measures >90% heal success on benign UI changes AND a false-heal rate near zero on breaking changes (seeded bugs still fail)
  5. Healing success rate and false-heal rate are tracked per element and exposed for reporting

**Plans**: TBD

### Phase 9: Defect Intelligence & Jira Agent

**Goal**: Failures triage themselves — classified with calibrated confidence and evidence, and high-confidence product defects become deduplicated, fully-evidenced Jira issues
**Mode:** mvp
**Depends on**: Phase 8
**Requirements**: DEF-01, DEF-02, DEF-03, JIRA-01, JIRA-02, JIRA-03, JIRA-04, QUAL-03
**Success Criteria** (what must be TRUE):

  1. Every failure is retried before classification, then labeled Infrastructure / Automation / Product Defect with a 0-100 confidence score citing evidence (error type, DOM diff, healing history, infra health)
  2. Classification accuracy exceeds 85% against the hand-labeled failure set, and that measurement calibrates the Jira confidence threshold before any autonomous filing
  3. The Jira Agent creates Jira Cloud issues with summary, description, steps to reproduce, expected/actual results, severity, priority, screenshots, video, and logs — starting in a draft/review queue, with autonomous creation activating only above the threshold and after measured >90% draft precision
  4. Duplicate failures update the existing Jira issue (failure fingerprinting + JQL search) instead of creating new ones, and ticket creation is capped per run
  5. Every created issue links to the originating test, flow, and execution, visible in the traceability chain

**Plans**: TBD
**UI hint**: yes

### Phase 10: Dashboards, RBAC & Coverage/Traceability

**Goal**: Every role sees the truth of the system — coverage, quality trends, root causes, and the full artifact chain — gated by their permissions
**Mode:** mvp
**Depends on**: Phase 9
**Requirements**: PLAT-04, DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06
**Success Criteria** (what must be TRUE):

  1. Executive dashboard shows coverage, pass rate, defect counts, and trends; QA dashboard shows execution history, failed tests, screenshots, and videos; developer dashboard shows root-cause groupings, error trends, and module failure breakdowns
  2. Admin assigns roles (Admin / QA Lead / QA Engineer / Developer) and each role's API access and dashboard views are enforced accordingly
  3. Coverage engine reports the percentage of discovered flows covered by approved scenarios and passing executions — graph-derived, with the honest definition displayed
  4. Traceability engine answers the flow ↔ scenario ↔ script ↔ execution ↔ defect chain for any artifact the user picks
  5. User searches across executions, failures, and logs with results served by Elasticsearch

**Plans**: TBD
**UI hint**: yes

### Phase 11: Hardening & Ops

**Goal**: The platform ships and operates like a product — deployable to Kubernetes, built and published by CI, and observable down to its domain metrics
**Mode:** mvp
**Depends on**: Phase 10
**Requirements**: INFRA-02, INFRA-03, INFRA-04
**Success Criteria** (what must be TRUE):

  1. Kubernetes manifests deploy the full platform on Docker Desktop K8s or kind with realistic resource limits, and an end-to-end run (explore → execute → dashboard) succeeds on that deployment
  2. GitHub Actions CI/CD builds, tests, and publishes platform images on push
  3. Grafana dashboards backed by Prometheus show platform health plus domain metrics: healing success rate, classification precision, coverage, and LLM cost (app-level exporters — no Enterprise-only Neo4j endpoint)

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Dev Environment | 8/8 | Complete   | 2026-06-13 |
| 2. LLM Gateway | 3/3 | Complete   | 2026-06-13 |
| 3. Tracer Bullet — Minimal End-to-End Loop | 4/4 | Complete   | 2026-06-14 |
| 4. Explorer Agent | 4/4 | Complete   | 2026-06-15 |
| 5. Knowledge Graph & Flow Learning | 4/4 | Complete   | 2026-06-20 |
| 6. BDD & Playwright Generation | 1/4 | In Progress|  |
| 7. Execution Engine & Workers | 0/TBD | Not started | - |
| 8. Self-Healing Engine | 0/TBD | Not started | - |
| 9. Defect Intelligence & Jira Agent | 0/TBD | Not started | - |
| 10. Dashboards, RBAC & Coverage/Traceability | 0/TBD | Not started | - |
| 11. Hardening & Ops | 0/TBD | Not started | - |
