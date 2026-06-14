# Requirements: Autonomous QA Engineer Platform

**Defined:** 2026-06-12
**Core Value:** Autonomous discovery — point the platform at a URL with credentials and it maps the application, learns its workflows, and builds the knowledge graph by itself.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Platform Foundation

- [x] **PLAT-01**: User can register a target application (name, URL, credentials, exploration rules) via API and UI
- [x] **PLAT-02**: Platform exposes REST API endpoints: POST /explore, /generate-bdd, /generate-scripts, /execute, /heal, /create-defect; GET /flows, /coverage, /executions, /dashboard
- [x] **PLAT-03**: User can log in to the platform with email/password; sessions persist via JWT
- [ ] **PLAT-04**: Admin can assign roles (Admin / QA Lead / QA Engineer / Developer) that gate API endpoints and dashboard views
- [x] **PLAT-05**: All agent LLM calls route through a provider-agnostic gateway that works with Anthropic or OpenAI via configuration only
- [x] **PLAT-06**: LLM gateway enforces per-call, per-run, and per-day token/cost budgets with a hard kill-switch, and logs cost per operation
- [x] **PLAT-07**: Target-app credentials are stored encrypted and never appear in logs, prompts, or generated code

### Explorer Agent

- [ ] **EXPL-01**: User can start an exploration of a registered app and watch live progress (pages found, actions taken, cost so far)
- [ ] **EXPL-02**: Explorer logs into target apps automatically (login-form detection, credential injection, Playwright storageState reuse, logout recovery)
- [ ] **EXPL-03**: Explorer discovers pages, forms, menus, buttons, links, and tables, capturing DOM metadata and a screenshot per discovered state
- [ ] **EXPL-04**: Explorer detects multi-step workflows (e.g., create customer → assign product → generate invoice) and form validation rules
- [ ] **EXPL-05**: Exploration is bounded by code-enforced budgets (max steps, depth, revisits, wall-clock, token spend) and a loop detector; it converges and stops on a stable app
- [ ] **EXPL-06**: Explorer deduplicates visited states via normalized DOM fingerprints (not URLs), distinguishing template states from instance data
- [ ] **EXPL-07**: Explorer enforces an action risk policy: destructive actions (delete, send, pay) are forbidden unless the target is flagged as a restorable sandbox
- [ ] **EXPL-08**: Page content is treated as untrusted input — observations are delimited and sanitized, and navigation is restricted to an origin allowlist
- [ ] **EXPL-09**: Every discovered element is captured as a fingerprint with prioritized locator chain (data-testid → aria-label → role → text → xpath) and locator history

### Knowledge Graph

- [ ] **KG-01**: Discovered structure persists in Neo4j as Page/Form/Workflow/Button/BusinessEntity nodes with NavigatesTo/Submits/Creates/Updates/Deletes edges
- [ ] **KG-02**: User can query and visually browse the knowledge graph (pages, flows, entities) from the UI
- [ ] **KG-03**: Re-exploring an unchanged app is idempotent (fingerprint-based MERGE, ~0 duplicate nodes); every node carries first_seen/last_verified freshness fields
- [ ] **KG-04**: Flow Learning Engine derives user journeys from the graph, categorizes business workflows, and assigns each flow a risk score
- [ ] **KG-05**: A single writer service is the only Neo4j write path; element fingerprints and locator history are queryable per element

### Test Generation

- [ ] **GEN-01**: User can generate BDD Gherkin features/scenarios (including scenario outlines with data-driven examples) from discovered flows
- [ ] **GEN-02**: Generated scenarios enter an approve/edit review queue; only approved scenarios feed automation generation
- [ ] **GEN-03**: Generated Gherkin passes a syntax lint gate, and every Then step asserts an outcome recorded in the knowledge graph (no vacuous assertions)
- [ ] **GEN-04**: User can generate Playwright automation (page objects, test specs, fixtures, utilities, test data models) in the spec folder structure (tests/ pages/ fixtures/ utils/ data/ reports/)
- [ ] **GEN-05**: Generated code uses only locators from the element repository (never freehand LLM selectors) and passes an N-run stability check before acceptance

### Execution Engine

- [ ] **EXEC-01**: User can run suites by tier — smoke, sanity, regression, full regression, and risk-based (selected from flow risk scores + failure history)
- [ ] **EXEC-02**: Suites execute locally, in Docker, and from CI/CD (GitHub Actions trigger + status reporting)
- [ ] **EXEC-03**: Executions run in parallel at browser level and flow level (RabbitMQ-distributed workers)
- [ ] **EXEC-04**: Every test run captures screenshots, video, and console/network logs per step, stored with paths recorded in PostgreSQL
- [ ] **EXEC-05**: Execution history persists with pass/fail trends, durations, and flaky-test detection (retry policy distinguishes infra flake from product failure)
- [ ] **EXEC-06**: User can watch a live execution view with per-test progress and a kill switch

### Self-Healing

- [ ] **HEAL-01**: On locator failure, the healing engine finds alternatives via DOM similarity, visual similarity, accessibility attributes, and historical locator mapping, using the priority chain (data-testid → aria-label → role → text → xpath)
- [ ] **HEAL-02**: Healing has three outcomes — auto-heal (high confidence), quarantine for review (medium), fail-as-potential-defect (low); assertions are never weakened to make a test pass
- [ ] **HEAL-03**: Every heal is recorded as an auditable before/after diff with confidence score, updates the script repository, and writes back to the knowledge graph
- [ ] **HEAL-04**: Healing success rate and false-heal rate are tracked per element and reported on dashboards

### Defect Intelligence

- [ ] **DEF-01**: Every failure is classified as Infrastructure (browser crash, network, environment), Automation (locator, test data), or Product Defect (functional, validation, performance, API) with a 0–100 confidence score
- [ ] **DEF-02**: Failures are retried before classification; classification cites evidence (error type, DOM diff, healing history, infra health)
- [ ] **DEF-03**: Classification accuracy is measured against a hand-labeled failure set before autonomous Jira filing is enabled

### Jira Integration

- [ ] **JIRA-01**: Platform creates Jira Cloud issues with summary, description, steps to reproduce, expected/actual results, severity, priority, screenshots, video, and logs
- [ ] **JIRA-02**: Jira Agent starts in draft/review mode (review queue); autonomous creation activates only above the confidence threshold and after measured >90% draft precision
- [ ] **JIRA-03**: Duplicate defects are detected via failure fingerprinting + JQL search — existing issues are updated, not duplicated; ticket creation is capped per run
- [ ] **JIRA-04**: Created issues are linked to the originating test, flow, and execution; links appear in the traceability chain

### Dashboards & Analytics

- [ ] **DASH-01**: Executive dashboard shows coverage, pass rate, defect counts, and trends
- [ ] **DASH-02**: QA dashboard shows execution history, failed tests, screenshots, and videos
- [ ] **DASH-03**: Developer dashboard shows root cause groupings, error trends, and module failure breakdowns
- [ ] **DASH-04**: Coverage engine reports % of discovered flows covered by approved scenarios and passing executions (graph-derived, honest definition)
- [ ] **DASH-05**: Traceability engine answers flow ↔ scenario ↔ script ↔ execution ↔ defect chains for any artifact
- [ ] **DASH-06**: Search across executions, failures, and logs is backed by Elasticsearch

### Infrastructure & Operations

- [x] **INFRA-01**: Entire platform runs locally via Docker Compose (PostgreSQL, Neo4j, Elasticsearch, RabbitMQ, Redis + services) with healthchecks and per-container memory limits suited to Windows 11/Docker Desktop
- [ ] **INFRA-02**: Kubernetes manifests deploy the platform, validated on Docker Desktop K8s or kind
- [ ] **INFRA-03**: GitHub Actions CI/CD builds, tests, and publishes platform images
- [ ] **INFRA-04**: Grafana + Prometheus expose platform health and domain metrics (healing success rate, classification precision, coverage, LLM cost)

### Quality Harnesses

- [ ] **QUAL-01**: A hand-labeled ground-truth graph of a demo app (SauceDemo) measures exploration coverage (>80% target)
- [ ] **QUAL-02**: A seeded-bug / benign-mutation harness measures self-healing success (>90%) and false-heal rate, and proves generated tests fail on real bugs
- [ ] **QUAL-03**: A labeled failure set measures defect classification accuracy (>85%) and calibrates the Jira confidence threshold
- [x] **QUAL-04**: Self-hosted demo target apps run in Docker with snapshot/restore so exploration and execution are repeatable

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Extended Capabilities

- **EXT-01**: Visual regression via integration (Applitools or Playwright toHaveScreenshot) — never built in-house
- **EXT-02**: Exploratory-testing reports beyond scripted flows (bug-hunt mode)
- **EXT-03**: PR-level impact analysis (which flows does this code change affect)
- **EXT-04**: MFA/SSO auth handling for target apps
- **EXT-05**: Predictive analytics (failure prediction from historical trends)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Pixel-diff visual regression engine | False-positive factory; Applitools took a decade — integrate, never build |
| Production session recording (Meticulous-style) | Requires instrumenting the target app; violates "point at any URL" premise; PII minefield |
| Manual test-case authoring UI (TestRail-style) | Contradicts autonomous generation core value; approve/edit of generated scenarios is the resolution |
| Custom ML model training | Solo dev can't collect/maintain training data; LLM APIs + deterministic similarity reach the same outcome |
| Unbounded "explore everything" crawling | State-space explosion, destructive-action risk, LLM cost blowout — bounded budgets instead |
| Autonomous test deletion | Silently deleting coverage is a trust-killer; mark-stale + human confirmation instead |
| Mobile native testing | Different automation stack (Appium); web only |
| Multi-tenancy / billing | Single-user deployment; RBAC without tenant isolation |
| Cloud K8s cluster ops (EKS/GKE/AKS) | Dev targets Docker Desktop; manifests are cloud-ready, cluster ops deferred |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PLAT-01 | Phase 1 | Complete |
| PLAT-02 | Phase 3 | Complete |
| PLAT-03 | Phase 1 | Complete |
| PLAT-04 | Phase 10 | Pending |
| PLAT-05 | Phase 2 | Complete |
| PLAT-06 | Phase 2 | Complete |
| PLAT-07 | Phase 1 | Complete |
| EXPL-01 | Phase 4 | Pending |
| EXPL-02 | Phase 4 | Pending |
| EXPL-03 | Phase 4 | Pending |
| EXPL-04 | Phase 4 | Pending |
| EXPL-05 | Phase 4 | Pending |
| EXPL-06 | Phase 4 | Pending |
| EXPL-07 | Phase 4 | Pending |
| EXPL-08 | Phase 4 | Pending |
| EXPL-09 | Phase 4 | Pending |
| KG-01 | Phase 5 | Pending |
| KG-02 | Phase 5 | Pending |
| KG-03 | Phase 5 | Pending |
| KG-04 | Phase 5 | Pending |
| KG-05 | Phase 5 | Pending |
| GEN-01 | Phase 6 | Pending |
| GEN-02 | Phase 6 | Pending |
| GEN-03 | Phase 6 | Pending |
| GEN-04 | Phase 6 | Pending |
| GEN-05 | Phase 6 | Pending |
| EXEC-01 | Phase 7 | Pending |
| EXEC-02 | Phase 7 | Pending |
| EXEC-03 | Phase 7 | Pending |
| EXEC-04 | Phase 7 | Pending |
| EXEC-05 | Phase 7 | Pending |
| EXEC-06 | Phase 7 | Pending |
| HEAL-01 | Phase 8 | Pending |
| HEAL-02 | Phase 8 | Pending |
| HEAL-03 | Phase 8 | Pending |
| HEAL-04 | Phase 8 | Pending |
| DEF-01 | Phase 9 | Pending |
| DEF-02 | Phase 9 | Pending |
| DEF-03 | Phase 9 | Pending |
| JIRA-01 | Phase 9 | Pending |
| JIRA-02 | Phase 9 | Pending |
| JIRA-03 | Phase 9 | Pending |
| JIRA-04 | Phase 9 | Pending |
| DASH-01 | Phase 10 | Pending |
| DASH-02 | Phase 10 | Pending |
| DASH-03 | Phase 10 | Pending |
| DASH-04 | Phase 10 | Pending |
| DASH-05 | Phase 10 | Pending |
| DASH-06 | Phase 10 | Pending |
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 11 | Pending |
| INFRA-03 | Phase 11 | Pending |
| INFRA-04 | Phase 11 | Pending |
| QUAL-01 | Phase 5 | Pending |
| QUAL-02 | Phase 8 | Pending |
| QUAL-03 | Phase 9 | Pending |
| QUAL-04 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 57 total (corrected from earlier count of 49)
- Mapped to phases: 57
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-12*
*Last updated: 2026-06-12 after roadmap creation (traceability populated)*
