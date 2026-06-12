# Project Research Summary

**Project:** Autonomous QA Engineer Platform
**Domain:** AI-driven autonomous web-application testing (agentic exploration, knowledge graph, BDD + Playwright generation, self-healing, defect intelligence, Jira integration, dashboards)
**Researched:** 2026-06-12
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a runtime-first autonomous testing platform: point it at a URL with credentials and it explores the app, builds a queryable Neo4j knowledge graph, and generates owned Gherkin + Playwright artifacts. The 2026 market splits into AI-assisted authoring tools (Testim, mabl classic, Healenium) and genuinely autonomous platforms (QA.tech, Autonoma, Functionize agents); this project sits in the second camp with first-camp capabilities (self-healing, suites, dashboards) as table stakes. No surveyed competitor combines runtime exploration, an exposed knowledge graph, owned test code, and confidence-gated autonomous Jira filing, self-hosted — the combination is the product, and each piece is individually hard.

Experts build these systems as a **two-plane architecture**: an agentic plane (LangGraph-orchestrated LLM agents that explore, learn, generate, heal, and triage — slow, expensive, occasional) and a deterministic plane (generated Playwright code run by stateless queue-fed workers — fast, cheap, repeatable). The knowledge graph is the contract between planes, and the LLM never runs inside routine test execution. The stack is fully decided and version-pinned (Python 3.13 / FastAPI / LangGraph 1.x / Playwright 1.60 / Next.js 16; `init_chat_model` for provider-agnostic LLM access — no LiteLLM, no custom adapter). Three architectural invariants are expensive to retrofit and must exist from the first exploration run: element fingerprints with locator history, deterministic state abstraction (fingerprint-based dedup, not URL-based), and graph freshness fields (`first_seen`/`last_verified`).

The dominant risks are trust-killers and budget-killers, all well-documented in 2026 practitioner literature: explorer agents looping forever and burning token budget, self-healing that silently masks real defects, false-positive Jira floods (~100:1 noise ratios measured before tuning), vacuous AI-generated tests that pass against broken apps, and — for a solo developer — eight stateful services drowning the project before anything works end-to-end. Mitigation is structural, not prompt-level: hard budgets and risk policies enforced in code, draft-mode Jira with dedup before any auto-create, audit trails on every heal, ground-truth harnesses (labeled SauceDemo graph, seeded-bug app builds), staggered service activation, and a vertical-slice tracer bullet through the whole pipeline before any engine is built to spec-completeness.

## Key Findings

### Recommended Stack

All user-constrained technologies are confirmed viable; research pinned exact versions (verified live against PyPI/npm) and resolved the open library questions. Full details in `STACK.md`.

**Core technologies:**
- **Python 3.13 + FastAPI 0.136 + SQLAlchemy 2.0 async/asyncpg + Alembic** — API and system of record (PostgreSQL 17)
- **LangGraph 1.2 + langchain `init_chat_model` + langgraph-checkpoint-postgres** — agent orchestration with resumable, crash-safe runs; `init_chat_model("anthropic:..." | "openai:...")` IS the provider-agnostic layer — do not add LiteLLM or a custom adapter
- **Playwright 1.60 + pytest 9 + pytest-bdd 8 + pytest-playwright + Jinja2 + gherkin-official** — one pytest runner covers BDD execution, parallelism, and artifact capture; Jinja templates guarantee valid generated code structure
- **neo4j 6.2 (async driver, raw Cypher — no OGM), elasticsearch 9.4 (server major must match), redis 8.0, aio-pika 9.6 (not Celery)** — data/queue layer
- **atlassian-python-api 4.x** for Jira Cloud REST v3 (the pycontribs `jira` package broke in the 2025 v3 migration); ADF bodies generated directly — no Python ADF library exists
- **PyJWT + argon2-cffi** for backend-owned auth/RBAC (no NextAuth); **MinIO** for artifacts (never blobs in Postgres/ES)
- **Next.js 16 + React 19 + TS 5.9 + Tailwind 4 + shadcn/ui + Recharts + TanStack Query/Table + Zustand + Zod** — dashboards; SSE (sse-starlette) for live progress, not WebSockets

### Expected Features

**Must have (table stakes — every credible competitor has all of these):**
- Self-healing locators with multi-attribute fingerprints — generated tests rot in days without it
- Per-step artifacts (screenshots, video, console/network logs) — Playwright provides natively
- Auth handling for exploration/execution (credential vault, login detection, storageState reuse) — blocks everything; week-one work
- Parallel execution, suite tiers (smoke/sanity/regression/full), execution history + trends
- Jira integration with evidence; CI/CD trigger + reporting; flaky-test handling; cross-browser

**Should have (differentiators — the product's identity):**
- Autonomous runtime exploration → flow discovery (the Core Value; depth is the differentiator, not link crawling)
- Exposed queryable Neo4j knowledge graph — no competitor ships this; strongest and riskiest differentiator
- Generated Gherkin + owned Playwright code (combines QA Wolf's code ownership with autonomy)
- 3-way failure classification with 0–100 confidence + confidence-gated Jira auto-filing
- Graph-derived flow coverage + full traceability chain; risk-based suite selection; role-based dashboards; self-hosted deployment

**Defer (v2+) / anti-features (do NOT build):**
- Pixel-diff visual regression (false-positive factory — integrate later, never build)
- Production session recording, manual test-case authoring UI, custom ML models, mobile native
- Ungated autonomous Jira filing and silent test deletion/healing — documented trust-killers (39% false-positive rates measured in real evaluations)

### Architecture Approach

Two-plane monorepo: `apps/api` (FastAPI, stateless, returns job IDs), `agents/` (LangGraph supervisor + subgraphs, separate long-lived processes), `workers/executor` (Node/TS Playwright Test runner — don't reimplement the runner in Python), `kg/writer` (the ONLY Neo4j write path), `shared/events/` (versioned queue message schemas), `workspaces/{app}` (generated test repos as data, git-versioned so every heal is a commit). RabbitMQ carries must-not-be-lost work (exploration/execution/healing/triage/jira-outbox queues); Redis carries fast replaceable state (LLM response cache, visited-state dedup, locks, pub/sub progress → SSE).

**Major components:**
1. **Explorer Agent** — accessibility-snapshot-first perception (vision only as fallback; ~10–50x cheaper and measurably more reliable), code-managed frontier/budgets, emits events
2. **KG Engine + Element Repository** — Neo4j stores app structure; PostgreSQL stores fingerprints/runs/users; never use Neo4j as the everything-store
3. **Generation engines (Flow/BDD/Playwright)** — read-only KG consumers; codegen may only reference Element Repository entries, never freehand LLM selectors
4. **Execution Engine + Workers** — queue-depth-scaled stateless containers; LLM-free execution loop
5. **Self-Healing + Defect Triage + Jira Agent** — LLM re-enters only on failure; outbox + dedup fingerprints for Jira
6. **LLM Gateway** — sole provider touchpoint: caching, token metering, budgets, model tiering

### Critical Pitfalls

Top 5 of 12 (full list with verification criteria in `PITFALLS.md`):

1. **Explorer loops / unbounded state space** — deterministic state abstraction (normalized DOM fingerprints), hard code-enforced budgets (steps, depth, revisits, wall-clock), loop detector, code-managed frontier. Exit test: converges and stops on SauceDemo twice consecutively.
2. **Self-healing masks real defects** — three-outcome healing (auto-heal / quarantine / fail-as-defect), never weaken assertions, audit every heal as a reviewable diff. Measure false-heal rate against a benign-vs-breaking mutation harness, not just "test passed after heal."
3. **False-positive Jira floods** — ship Jira Agent in draft/review mode first; auto-create only after measured >90% draft precision; mandatory dedup fingerprinting + JQL search; retry-before-classify; per-run ticket cap.
4. **LLM cost blowup (O(n²) context growth)** — budgets/metering/kill-switch live in the LLM gateway built BEFORE the Explorer; snapshot perception, prompt caching, model tiering, cost-per-run logged from day one.
5. **Full-scope v1 never reaching a working loop** — the 14 components form a pipeline of compounding error rates that cannot be tuned stage-by-stage in isolation; build a thin end-to-end tracer bullet early, widen stages afterward; every phase exits with an end-to-end demo against a named target app.

Also critical for this environment: destructive actions during exploration (code-level action risk policy + self-hosted snapshot/restore targets), prompt injection from page content (delimited untrusted observations + origin allowlist), and Windows 11/WSL2 resource exhaustion (`.wslconfig` caps, per-container memory limits, compose profiles, `vm.max_map_count` for ES).

## Implications for Roadmap

Based on research, suggested phase structure (vertical-slice-first; each infra service activates in the first phase that consumes it):

### Phase 1: Foundation & Dev Environment
**Rationale:** Everything depends on a stable dev environment, but only a minimal one — "all 8 services healthy" is an explicit non-goal (Pitfalls 8, 9).
**Delivers:** Docker Compose with profiles (Postgres + Redis only active), `.wslconfig` + per-container memory limits, FastAPI skeleton with JWT auth, Next.js shell, repo structure (`agents/`, `kg/`, `shared/events/`, `workspaces/`), self-hosted SauceDemo target with snapshot/restore.
**Addresses:** Auth/API contract groundwork.
**Avoids:** Pitfall 8 (infra over-engineering), Pitfall 9 (WSL2 resource exhaustion).

### Phase 2: LLM Gateway
**Rationale:** Every agent consumes it; budgets and metering must exist before any agent can burn money (Pitfall 5).
**Delivers:** `init_chat_model`-based gateway with per-call/per-run/per-day budgets and hard kill-switch, Redis response caching, prompt-cache-friendly prompt structure, model tiering, cost-per-operation logging, verified parity run on both Anthropic and OpenAI.
**Uses:** langchain 1.x, langchain-anthropic, langchain-openai, tenacity, Redis.
**Avoids:** Pitfall 5 (cost blowup).

### Phase 3: Tracer Bullet — Minimal End-to-End Loop
**Rationale:** The pipeline's compounding error rates can't be tuned without real output flowing through every stage (Pitfall 10). Neo4j enters here.
**Delivers:** Thin slice: explore SauceDemo → minimal graph → one generated scenario → one Playwright spec → one execution → result row in Postgres. Stub quality per stage is acceptable; the loop running is the milestone.
**Implements:** Skeleton of every pipeline stage; queue message contracts in `shared/events/`.
**Avoids:** Pitfall 10 (full-scope no-loop).

### Phase 4: Explorer Agent (full)
**Rationale:** The Core Value and highest-risk component; everything downstream inherits its quality. Fingerprint capture designed here even though healing ships later — retrofitting means re-crawling everything.
**Delivers:** Snapshot-first perception with vision fallback, LangGraph StateGraph with Postgres checkpointing, deterministic state abstraction + frontier + budgets + loop detection, action risk policy (safe/confirm/forbidden), observation sanitization + origin allowlist, auth handling (login detection, storageState, logout recovery), element fingerprints with locator priority chain, instance-vs-template state classification.
**Avoids:** Pitfalls 1 (loops), 2 (destructive actions), 11 (prompt injection), 12 (data pollution — partial).

### Phase 5: Knowledge Graph Engine + Flow Learning
**Rationale:** Single source of truth feeding all generation; freshness semantics and idempotent MERGE must be in the schema from day one (Pitfall 7).
**Delivers:** KG writer as sole Neo4j write path, schema with constraints/indexes and `first_seen`/`last_verified`, fingerprint-based MERGE (re-run idempotency: ~0 new nodes on unchanged app), Element Repository in Postgres, flow mining + risk scoring, hand-labeled SauceDemo ground-truth graph.
**Implements:** KG Engine, Flow Learning Engine, Element Repository.
**Avoids:** Pitfall 7 (graph staleness/ghost nodes).

### Phase 6: BDD + Playwright Generation
**Rationale:** Pure consumers of the graph; quality gates are part of generation, not a later phase (Pitfall 6).
**Delivers:** Jinja-templated generation (LLM fills semantic slots only), Gherkin parser + lint gate, assertion-quality gate (every Then asserts a KG-recorded outcome), locators emitted only from Element Repository, N-run stability acceptance check, seeded-bug mutation check as the phase's success criterion, human approve/edit workflow for scenarios.
**Uses:** Jinja2, gherkin-official, pytest-bdd workspace layout.
**Avoids:** Pitfall 6 (flaky/vacuous tests).

### Phase 7: Execution Engine + Workers
**Rationale:** First full production-grade value loop; RabbitMQ and MinIO enter here because this is the phase that needs them.
**Delivers:** Suite planning (smoke/sanity/regression/full), aio-pika job dispatch with quorum queues/DLQs/manual acks, Node Playwright Test worker containers, artifact upload to MinIO, results to Postgres, Redis pub/sub → SSE live progress, target reset hooks (two consecutive runs → identical results).
**Implements:** Deterministic plane; queue-depth-scaled worker pattern.
**Avoids:** Pitfall 12 (pollution — execution side), anti-pattern "LLM in the execution loop."

### Phase 8: Self-Healing Engine
**Rationale:** Needs fingerprints (Phase 4/5) and real failure events (Phase 7). Design the quarantine/audit model before the healing algorithm.
**Delivers:** Three-outcome healing with similarity scoring + threshold, re-validation against live page, heal-as-commit audit trail, graph write-back, heal-rate-per-element tracking, benign-vs-breaking mutation harness measuring true heal success AND false-heal rate.
**Avoids:** Pitfall 3 (healing masks defects).

### Phase 9: Defect Intelligence + Jira Agent
**Rationale:** Classification needs accumulated real failure data from Phase 7+ to calibrate confidence; Jira automation is gated on classification quality. Elasticsearch enters here (failure search/clustering).
**Delivers:** 3-way classification with confidence scoring, hand-labeled failure set for calibration, draft-mode review queue first, dedup fingerprinting + JQL update-instead-of-create, per-run ticket cap, rate-limit/429 resilience, ADF body generation, outbox pattern; auto-create enabled only after >90% measured draft precision.
**Avoids:** Pitfall 4 (Jira floods).

### Phase 10: Dashboards, Analytics, RBAC, Coverage/Traceability
**Rationale:** Needs populated data from phases 7–9; single operator dashboard first, role split after (solo user today).
**Delivers:** Operator dashboard (live run view with kill switch, heal/triage review queues, cost panel), then executive/QA/developer views with RBAC, freshness and confidence bands on every metric, graph-derived coverage + traceability chain, risk-based suite selection.

### Phase 11: Hardening & Ops
**Rationale:** K8s is a packaging exercise if workers were stateless from Phase 7; observability matters once there's something worth monitoring.
**Delivers:** K8s manifests validated on Docker Desktop/kind with realistic resource limits, GitHub Actions CI/CD, Prometheus exporters + Grafana dashboards (domain metrics: healing success, classification precision, coverage), ES index lifecycle, incremental re-exploration/reconciliation.

### Phase Ordering Rationale

- **Dependency spine:** Explorer → KG → Flow Learning → Generation → Execution → Healing/Triage → Jira → Dashboards is dictated by data flow; FEATURES.md, ARCHITECTURE.md, and PITFALLS.md independently converge on this order.
- **Vertical slice before horizontal depth:** the Phase-3 tracer bullet de-risks the compounding-error-rate pipeline before any single engine is built deep.
- **Trust features are survival, not polish:** draft-mode Jira, heal audit trails, and ground-truth harnesses are launch requirements of their phases because the skeptic literature is unanimous that autonomous tools die on false-positive discipline.
- **Staggered infra activation** (Postgres/Redis → Neo4j → RabbitMQ/MinIO → ES → Prometheus/Grafana → K8s) keeps a solo developer on a Windows/WSL2 machine productive.

### Research Flags

Phases likely needing deeper research during planning (`/gsd:plan-phase --research-phase`):
- **Phase 4 (Explorer Agent):** perception prompt design, state-abstraction fingerprint algorithm, action risk heuristics — most novel component, sparse canonical references
- **Phase 5 (Knowledge Graph):** concrete Cypher schema design, reconciliation/merge strategy — synthesized from research papers, no single reference implementation
- **Phase 8 (Self-Healing):** similarity scoring weights and thresholds — Healenium pattern is verified but tuning specifics need experimentation
- **Phase 9 (Defect Intelligence):** confidence calibration methodology; ADF generation specifics — no Python ADF library exists, hand-rolled

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** Docker Compose, FastAPI, JWT — extensively documented
- **Phase 2 (LLM Gateway):** `init_chat_model` and budgets are well-documented LangChain patterns
- **Phase 7 (Execution Engine):** aio-pika + Playwright workers are established patterns with official docs
- **Phase 10–11 (Dashboards/Hardening):** shadcn/Recharts dashboards and K8s packaging are commodity work

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified live against PyPI/npm on research date; patterns verified against official docs/release notes |
| Features | MEDIUM | Vendor docs + multiple independent 2026 comparisons agree on landscape; vendor accuracy claims and the 39% false-positive figure are single-source/promotional |
| Architecture | MEDIUM-HIGH | HIGH on agent perception, orchestration, and healing patterns (official docs, OSS); MEDIUM on full-platform decomposition (synthesized — no canonical open reference exists) |
| Pitfalls | MEDIUM-HIGH | Web-verified across independent sources (issue trackers, arXiv, practitioner reports); some thresholds (e.g., draft-precision gate at 90%) are judgment calls |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Spec success metrics (>80% coverage, >85% classification, >90% healing) are unfalsifiable without ground truth:** build labeling harnesses (hand-labeled SauceDemo graph in Phase 5, seeded-bug app builds in Phases 6/8, labeled failure set in Phase 9) — they appear in no component list but gate every metric.
- **LLM confidence calibration:** raw LLM confidence scores are uncalibrated; the Jira threshold needs validation against labeled outcomes accumulated during Phases 7–9. Handle via mandatory draft mode.
- **ADF (Atlassian Document Format) generation:** no mature Python builder library exists; plan a small in-house text→ADF helper in Phase 9.
- **Neo4j Prometheus metrics are Enterprise-only:** emit app-level graph metrics from services via prometheus-client instead (decided in STACK.md, confirm in Phase 11).
- **Infra Docker image minor tags:** MEDIUM confidence — pin exact digests when writing Compose files in Phase 1.
- **MFA/SSO auth on target apps:** known hard case for exploration auth; demo targets don't exercise it — flag as explicit limitation or Phase 4 stretch scope.

## Sources

### Primary (HIGH confidence)
- PyPI JSON API / npm registry — all versions queried live 2026-06-12 (langgraph 1.2.4, playwright 1.60.0, neo4j 6.2.0, fastapi 0.136.3, next 16.2.9, etc.)
- LangGraph v1 release notes + GA announcement — v1 stability, `create_react_agent` deprecation, `init_chat_model` pattern
- Neo4j Python Driver 6.x breaking changes + Prometheus metrics docs (Enterprise-only endpoint)
- Next.js 16 release + upgrade guide; Playwright official docs (MCP, parallelism)
- Healenium repos — weighted-LCS similarity, locator-history architecture (open source, verifiable)
- Atlassian Jira Cloud REST v3 + rate-limiting docs

### Secondary (MEDIUM confidence)
- Vendor docs and 2026 comparisons: mabl, Functionize, Testim, testRigor, QA Wolf, QA.tech, Autonoma — feature landscape (multiple sources agree)
- arXiv reviews of AI testing tools; browser-agent security papers (TOCTOU, social engineering); LangGraph multi-agent practice articles; Playwright-on-K8s scaling guides
- browser-use issue tracker (endless-loop cost burns); WSL2/Docker memory behavior reports; Jira auto-ticket flood experiments

### Tertiary (LOW confidence)
- 39% false-positive rate for one evaluated AI tester (single practitioner report — directionally corroborated by arXiv reviews; treat the number as illustrative)
- Single-vendor "agentic QA architecture" posts — used only where corroborated

---
*Research completed: 2026-06-12*
*Ready for roadmap: yes*
