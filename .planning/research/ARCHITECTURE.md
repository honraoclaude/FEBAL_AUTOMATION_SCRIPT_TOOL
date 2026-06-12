# Architecture Research

**Domain:** AI-driven autonomous web-application testing platform (explorer agents, knowledge graph, BDD + Playwright generation, self-healing, defect intelligence, Jira integration, dashboards)
**Researched:** 2026-06-11
**Confidence:** MEDIUM-HIGH overall (HIGH on browser-agent perception, agent orchestration, and self-healing patterns — verified against official docs and established tools; MEDIUM on full-platform decomposition — synthesized from commercial platforms, OSS frameworks, and research literature, since no single open canonical reference exists)

## Standard Architecture

### System Overview

Autonomous testing platforms converge on a **two-plane architecture**: an *agentic plane* (LLM-in-the-loop: exploration, learning, generation, healing, triage — slow, expensive, occasional) and a *deterministic plane* (generated Playwright code executed by workers — fast, cheap, repeatable). The knowledge graph is the contract between them. The LLM never runs inside routine test execution; it only re-enters when something breaks (healing, triage).

```
┌────────────────────────────────────────────────────────────────────────┐
│ PRESENTATION                                                            │
│  Next.js: Executive / QA / Developer dashboards · RBAC UI · live runs  │
└───────────────────────────────┬────────────────────────────────────────┘
                                │ REST + SSE/WebSocket
┌───────────────────────────────┴────────────────────────────────────────┐
│ API LAYER (FastAPI)                                                     │
│  /explore /generate-bdd /generate-scripts /execute /heal               │
│  /create-defect /flows /coverage /executions /dashboard                │
│  AuthN/AuthZ (RBAC) · job submission · progress streaming · reporting  │
└──────┬──────────────────────────────────────────────┬──────────────────┘
       │ enqueue jobs / start graph runs              │ read models
┌──────┴───────────────────────────────┐   ┌──────────┴──────────────────┐
│ AGENTIC PLANE (LangGraph supervisor) │   │ ANALYTICS / REPORTING       │
│  ┌──────────┐ ┌──────────┐           │   │  coverage · traceability    │
│  │ Explorer │ │   Flow   │ subgraphs │   │  trends · risk scoring      │
│  │  Agent   │ │ Learning │           │   └─────────────────────────────┘
│  └────┬─────┘ └────┬─────┘           │
│  ┌────┴─────┐ ┌────┴─────┐ ┌───────┐ │   ┌─────────────────────────────┐
│  │ BDD Gen  │ │ PW Code  │ │Healing│ │   │ DETERMINISTIC PLANE         │
│  └──────────┘ │   Gen    │ │ Agent │ │   │  RabbitMQ queues →          │
│  ┌──────────┐ └──────────┘ └───────┘ │   │  Playwright execution       │
│  │ Defect   │ ┌──────────┐           │   │  workers (containers,       │
│  │ Triage   │ │  Jira    │           │   │  scale on queue depth)      │
│  └──────────┘ │  Agent   │           │   └─────────────────────────────┘
│               └──────────┘           │
│  LLM Gateway (Anthropic/OpenAI       │
│  adapter, caching, token metering)   │
└──────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────────┐
│ DATA LAYER                                                              │
│  PostgreSQL        Neo4j            Elasticsearch    Redis             │
│  (system of        (app knowledge   (logs, failure   (cache, locks,    │
│  record: runs,     graph: pages,    search, error    dedup, pub/sub    │
│  results, users,   elements, flows, clustering)      progress, LLM     │
│  traceability,     transitions)                      response cache)   │
│  element repo,                      Object store / volume              │
│  LangGraph         RabbitMQ         (screenshots, videos, traces,      │
│  checkpoints)      (job queues)     generated test repos)              │
└────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────────┐
│ OBSERVABILITY: Prometheus metrics → Grafana · structured logs → ES     │
└────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| API layer (FastAPI) | Auth/RBAC, job submission, progress streaming, read models for dashboards. Never drives browsers directly. | FastAPI + Pydantic; long operations return a job ID immediately; SSE/WS for live progress via Redis pub/sub |
| Agent orchestrator | Routes work between agents, manages retries/loops, persists state for resumability | LangGraph supervisor graph; each agent is a subgraph; PostgresSaver checkpointer so crashed runs resume |
| Explorer Agent | Drives a browser to map the app: pages, forms, menus, actions; captures element fingerprints + screenshots; emits graph events | LangGraph subgraph + Playwright; **accessibility-snapshot-first perception** (see Pattern 1); BFS/DFS frontier with visited-state dedup (Redis) |
| Knowledge Graph Engine | Single source of truth for app structure: Page/Element/Form/Flow/Entity nodes, NAVIGATES_TO/SUBMITS/CREATES/... edges | Neo4j via async driver; a dedicated KG-writer service/module owns all writes (agents emit events, never write Cypher directly) |
| Flow Learning Engine | Mines user journeys from the graph, categorizes business workflows, assigns risk scores, maintains the digital twin | Graph algorithms (path mining over Neo4j) + LLM classification of flow semantics |
| BDD Generation Engine | Flows → Features/Scenarios/Scenario Outlines with example tables | LLM generation grounded in KG flow data; output validated by a Gherkin parser before persisting |
| Playwright Generation Engine | Page objects, specs, fixtures, test data from KG elements + flows | Template/codegen + LLM for logic; generated repo written to a per-app test workspace; locators come from the Element Repository, not freehand LLM output |
| Element Repository | Versioned locator sets + fingerprints per element (data-testid, aria, role, text, xpath, DOM context, visual hash) | PostgreSQL tables keyed by KG element ID; this is the substrate self-healing depends on |
| Execution Engine | Builds suite plans (smoke/sanity/regression/risk-based), shards work, dispatches to workers, aggregates results | API/orchestrator produces a test plan → messages on RabbitMQ; results consumed back into PostgreSQL |
| Playwright Workers | Stateless containers that consume execution jobs, run generated specs, upload artifacts, report results | Node-based Playwright runner in Docker; scaled on queue depth (KEDA pattern on K8s) |
| Self-Healing Engine | On locator failure: fingerprint similarity (DOM weighted-LCS, a11y attrs, visual), pick best candidate above score threshold, re-validate, update Element Repository, regenerate page object | Healenium-style weighted scoring with a score-cap threshold; healing events audited in PostgreSQL |
| Defect Triage Engine | Classify failures (infrastructure / automation / product defect) with 0–100 confidence; cluster duplicates | LLM classification over failure context (error, trace, screenshot diff, history from ES); threshold gates Jira creation |
| Jira Agent | Create/update defects with steps, evidence, severity; link to tests | Jira Cloud REST v3 (ADF body) via outbox pattern + dedup fingerprint to prevent duplicate tickets |
| Analytics/Dashboard Engine | Coverage, pass rates, trends, root-cause views per role | SQL aggregates over PostgreSQL + ES queries; cached in Redis; rendered by Next.js |
| LLM Gateway | Provider-agnostic adapter (Anthropic/OpenAI), prompt templating, response caching, token/cost metering | Thin internal abstraction (or LangChain `init_chat_model`); Redis-cached responses for identical perception inputs |

### Where queues and cache fit

**RabbitMQ (work distribution, durability):**
- `exploration.jobs` — explore-session requests (one per target app crawl)
- `execution.jobs` — sharded test-run units consumed by Playwright workers
- `healing.jobs` — locator-failure events needing healing
- `triage.jobs` — failed-test bundles for defect classification
- `jira.outbox` — defect-creation commands (idempotent, retry-safe)

Queue depth is the scaling signal for workers. Use quorum queues + manual acks + dead-letter queues for poison messages.

**Redis (speed, coordination, ephemera):**
- LLM response cache (same snapshot+prompt → cached answer; large cost saver during exploration)
- Visited-state dedup set during crawling (URL+DOM-hash)
- Distributed locks (one healing operation per element at a time; one crawl per app)
- Pub/sub for live progress events → API SSE → dashboard
- Dashboard read-model cache, session/rate-limit data

Rule of thumb: **RabbitMQ for "must not be lost" work, Redis for "fast and replaceable" state.** Don't use Redis as the job queue when RabbitMQ is already in the stack.

## Recommended Project Structure

Monorepo — solo developer, tightly coupled domain models, single deploy cadence.

```
/
├── apps/
│   ├── web/                      # Next.js dashboards (TS)
│   │   ├── app/(dashboards)/     # executive / qa / developer routes
│   │   └── lib/api/              # typed API client
│   └── api/                      # FastAPI service (Python)
│       ├── app/routers/          # explore, execute, flows, coverage, ...
│       ├── app/auth/             # RBAC
│       ├── app/services/         # business logic, job submission
│       └── app/models/           # SQLAlchemy + Pydantic schemas
├── agents/                       # LangGraph agentic plane (Python pkg)
│   ├── supervisor/               # top-level graph, routing, checkpoints
│   ├── explorer/                 # perception, action selection, frontier
│   ├── flow_learning/
│   ├── bdd_gen/
│   ├── code_gen/
│   ├── healing/
│   ├── triage/
│   ├── jira/
│   └── llm/                      # provider-agnostic gateway + prompts
├── workers/
│   └── executor/                 # Playwright runner image (Node/TS)
├── kg/                           # knowledge-graph schema + writer
│   ├── schema.cypher             # constraints, indexes
│   └── writer/                   # event → Cypher; only KG write path
├── shared/                       # cross-service contracts
│   └── events/                   # queue message schemas (Pydantic/JSON Schema)
├── workspaces/                   # generated per-app test repos (gitignored
│   └── {app}/                    # or its own git repo per app)
│       ├── features/             # .feature files
│       ├── pages/                # page objects
│       ├── tests/                # specs
│       ├── fixtures/  data/
│       └── artifacts/            # screenshots, videos, traces per run
├── infra/
│   ├── docker-compose.yml        # full local stack
│   ├── k8s/                      # manifests (Docker Desktop/kind validated)
│   └── grafana/  prometheus/
└── .github/workflows/
```

### Structure Rationale

- **`agents/` separate from `apps/api/`:** the agentic plane runs as its own long-lived process(es) consuming jobs — keeps the API stateless and lets agent workers restart/scale independently.
- **`kg/writer/` as the only Neo4j write path:** prevents nine agents inventing nine graph dialects; the graph schema stays coherent.
- **`shared/events/`:** queue messages are the inter-service API; version them like one.
- **`workspaces/`:** generated test code is *data produced by the platform*, not platform source — keep it out of the platform's own packaging; treating each app workspace as a git repo gives healing a natural audit trail (heal = commit).
- **`workers/executor/` in Node/TS:** generated tests use Playwright Test runner natively (sharding, retries, traces, HTML reports come free) — don't reimplement the runner in Python.

## Architectural Patterns

### Pattern 1: Snapshot-First Hybrid Perception (browser-driving agents)

**What:** The Explorer (and healer) perceives pages through Playwright's **accessibility snapshot / ARIA tree** — a structured semantic representation (roles, names, states, unique element refs) — as the primary input to the LLM. Screenshots/vision are a *fallback* for canvas-heavy pages, visual validation, and ambiguous cases.

**When to use:** Default for all perception. Vision fallback triggers: snapshot is empty/tiny relative to viewport, canvas/WebGL detected, or the LLM reports it cannot find a target.

**Trade-offs:** Snapshot-based perception is dramatically cheaper (~200–400 tokens per Playwright MCP-style snapshot vs thousands for raw DOM or image tokens), more deterministic, and benchmarks show DOM/snapshot-driven stacks beat vision-driven stacks by 12–17 points on common-task reliability. Vision wins only on obfuscated markup and canvas UIs. This is the same split as the ecosystem: Playwright MCP and browser-use are tree/DOM-first; Skyvern is vision-first with a Planner–Actor–Validator loop.

**Example:**
```python
async def perceive(page) -> Perception:
    snapshot = await page.locator("body").aria_snapshot()  # role tree w/ refs
    if is_degenerate(snapshot):                  # canvas app, empty tree
        return Perception(mode="vision", image=await page.screenshot())
    return Perception(mode="snapshot", tree=snapshot)
# LLM acts on element refs from the snapshot — never invents selectors
```

### Pattern 2: Supervisor Graph with Agent Subgraphs and Checkpointing

**What:** One LangGraph supervisor routes between specialist agents implemented as subgraphs (explorer, flow, bdd, codegen, healing, triage, jira, analytics). State is checkpointed to PostgreSQL at every step.

**When to use:** Always for the agentic plane. Checkpointing is non-negotiable: exploration sessions run for many minutes to hours; a crash mid-crawl must resume from the last checkpoint, not restart.

**Trade-offs:** Supervisor pattern adds a routing hop, but yields auditability (every transition is recorded), human-in-the-loop interrupts (e.g., approve Jira creation early on), and time-travel debugging. Avoid making the supervisor do real work — it routes; subgraphs work.

**Example:**
```python
graph = StateGraph(PlatformState)
graph.add_node("explorer", explorer_subgraph)
graph.add_node("flow_learning", flow_subgraph)
graph.add_node("supervisor", route)   # decides next agent or END
app = graph.compile(checkpointer=PostgresSaver(pool))  # resume on crash
```

### Pattern 3: Two-Plane Split — LLM Generates, Workers Execute

**What:** LLMs produce *artifacts* (graph entries, Gherkin, Playwright code, healed locators). Routine execution runs the generated code with zero LLM calls. The LLM re-enters only on failure (healing, triage).

**When to use:** Core invariant of the whole platform.

**Trade-offs:** Generated code can go stale (that's what healing is for), but execution is fast, cheap, deterministic, and CI-friendly. The alternative — agent-executes-every-test — is how demos work and how budgets die; commercial platforms (mabl, Testim, Functionize class) all compile learning into replayable artifacts.

### Pattern 4: Element Repository with Multi-Signal Fingerprints

**What:** During exploration, capture for every element a *fingerprint*: ordered locator candidates (data-testid → aria-label → role → text → CSS → XPath), DOM context (tag, attributes, ancestor path), accessibility attributes, and a visual crop/hash. Healing is then a similarity search (Healenium-style weighted scoring, e.g. weighted longest-common-subsequence over attributes with a score threshold ~0.5) against the *current* page, followed by re-validation and a versioned repository update.

**When to use:** Fingerprint capture must be built into the Explorer from day one even though healing ships later — retrofitting fingerprints means re-crawling everything.

**Trade-offs:** More storage and crawl time per element; but it is the entire basis of >90% healing success and of locator-priority generation.

### Pattern 5: Queue-Depth-Scaled Worker Pool

**What:** Execution requests are sharded into job messages; stateless Playwright worker containers consume them; worker count scales on queue depth (KEDA on K8s; fixed pool in Compose). Each job gets a fresh browser context; artifacts upload to object storage; results post back to the API/DB.

**When to use:** All execution, including local dev (run 1–2 workers under Compose so the architecture is identical to K8s).

**Trade-offs:** Slightly more plumbing than `npx playwright test` in-process, but gives browser/flow-level parallelism, isolation, retry semantics, and a clean path from laptop → CI → cluster. Two-level parallelism: shard across worker pods (horizontal), Playwright workers within a pod (vertical, CPU-bound — ~1 browser per core).

## Data Flow

### End-to-End Pipeline

```
[POST /explore {url, creds}]
    ↓ enqueue exploration.jobs
[Explorer Agent] ──Playwright──> target app
    │  perceive (a11y snapshot ±vision) → LLM picks next action → act → observe
    │  emits: PageDiscovered, ElementFingerprinted, ActionObserved, FormMapped
    ↓ events
[KG Writer] → Neo4j (pages, elements, edges)   [screenshots → object store]
    ↓                                          [fingerprints → PostgreSQL]
[Flow Learning Agent] reads Neo4j → mines journeys → risk scores → Flow nodes
    ↓
[BDD Gen Agent] flows → .feature files → workspace + PostgreSQL (validated by parser)
    ↓
[Code Gen Agent] flows + Element Repository → page objects/specs/fixtures → workspace
    ↓
[POST /execute {suite}] → test plan → shards → execution.jobs (RabbitMQ)
    ↓
[Playwright Workers] run specs → results → PostgreSQL · logs → ES · artifacts → store
    │
    ├─ locator failure ──→ healing.jobs → [Healing Agent]
    │       fingerprint similarity → candidate → re-validate → update repo
    │       → regenerate page object → optional re-run
    └─ test failure ─────→ triage.jobs → [Defect Triage Agent]
            classify infra/automation/product + confidence (ES history aids dedup)
            ├─ ≥ threshold + product defect → jira.outbox → [Jira Agent] → Jira Cloud
            └─ automation → route to healing · infra → retry/flag
    ↓
[Analytics] aggregates PostgreSQL + ES → Redis-cached read models
    ↓
[Next.js dashboards] ← REST/SSE ← FastAPI    [Prometheus → Grafana for platform health]
```

### Key Data Flows

1. **Exploration → KG:** Explorer emits structured events; KG Writer is the sole Neo4j write path. Neo4j stores *structure* (the app model); PostgreSQL stores *records* (fingerprints, runs, users, traceability). Never use Neo4j as the system of record for execution history.
2. **Generation reads KG, writes workspace:** Gherkin and code generators are read-only consumers of Neo4j; their outputs live in the per-app workspace + PostgreSQL metadata, giving traceability edges (flow ↔ scenario ↔ spec).
3. **Execution loop is LLM-free:** plan → queue → worker → results. LLM re-enters only via `healing.jobs` / `triage.jobs`.
4. **Progress streaming:** agents/workers publish progress to Redis pub/sub → FastAPI SSE → UI; no polling of PostgreSQL.
5. **Traceability spine:** requirement/flow → scenario → spec → execution → defect, kept as foreign keys in PostgreSQL with mirror edges in Neo4j for graph queries (coverage = graph traversal).

## Suggested Build Order

Dependencies dictate a clear spine. Each step is testable against demo apps (SauceDemo first — simplest; OrangeHRM/OpenCart later).

| Step | Build | Depends on | Notes |
|------|-------|-----------|-------|
| 1 | Foundation: Docker Compose (Postgres, Neo4j, Redis, RabbitMQ, ES), FastAPI skeleton + auth/RBAC, Next.js shell, **LLM gateway** | — | Everything touches the gateway; build the provider abstraction before any agent |
| 2 | **Explorer Agent + KG Engine** (perception, action loop, KG writer, element fingerprints, screenshots) | 1 | The core value and the riskiest part — do it early. **Fingerprint capture is designed here even though healing is step 7** |
| 3 | Flow Learning Engine | 2 | Pure consumer of the KG |
| 4 | BDD Generation | 3 | Flows → Gherkin; validate with parser; measure against known demo-app workflows |
| 5 | Playwright Code Generation + workspace layout | 2, 3 | Can overlap with 4; both read flows + element repo |
| 6 | Execution Engine + Playwright workers + artifacts + results persistence | 5 | First end-to-end value: explore → generate → run |
| 7 | Self-Healing Engine | 2 (fingerprints), 6 (failure events) | Validate by deliberately mutating a self-hosted demo app's DOM |
| 8 | Defect Triage + Jira Agent | 6 | Needs real failure data; Jira via outbox + dedup |
| 9 | Dashboards + Analytics + Traceability/Coverage | 6–8 | Needs data to display; build read models last |
| 10 | Hardening: K8s manifests, KEDA-style scaling, GitHub Actions, Grafana/Prometheus dashboards | all | Compose-first throughout; K8s is a packaging exercise if workers were stateless from step 6 |

**Critical early decisions (expensive to retrofit):** element fingerprint schema (step 2), queue message contracts (`shared/events/`, step 1–2), artifact storage conventions (step 2), KG schema with versioning (elements change across crawls — model `ElementVersion` from the start).

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Solo dev / single app under test (now) | Full stack under Docker Compose; 1 agent process, 1–2 execution workers; fixed concurrency. The architecture above runs fine at this scale — the point is correct boundaries, not throughput |
| Several apps, frequent regression runs | Scale execution workers on queue depth (KEDA on Docker Desktop K8s/kind); shard suites; ES index lifecycle for logs; LLM cache hit rate becomes a cost lever |
| Team/CI-heavy use | Split agent workers by queue (exploration vs healing vs triage); Neo4j read replicas only if graph queries dominate; move artifacts to real object storage (MinIO/S3) |

### Scaling Priorities

1. **First bottleneck: LLM cost/latency during exploration.** One crawl = hundreds of perception→decision calls. Mitigate with snapshot-first perception (smallest tokens), Redis response caching, visited-state dedup, and cheap-model routing for trivial decisions.
2. **Second bottleneck: browser worker CPU/RAM.** Headless Chromium ≈ 0.5–1 CPU and 0.5–1 GB per context; scale horizontally via queue, not by cranking per-pod worker counts.

## Anti-Patterns

### Anti-Pattern 1: LLM in the Execution Loop

**What people do:** Have the agent "run" every regression test by driving the browser with the LLM each time.
**Why it's wrong:** Non-deterministic results, 100–1000x cost per run, minutes instead of seconds, impossible CI gating.
**Do this instead:** Two-plane split (Pattern 3). Generate Playwright code once; execute deterministically; LLM only on failure.

### Anti-Pattern 2: Vision-First Perception by Default

**What people do:** Screenshot → multimodal LLM for every step because "it sees what users see."
**Why it's wrong:** Slower, far more tokens, and measurably less reliable than tree/DOM-based perception for standard web apps (DOM-available tasks favor structured perception by double digits).
**Do this instead:** Accessibility-snapshot-first with vision fallback (Pattern 1).

### Anti-Pattern 3: Neo4j as the Everything-Store

**What people do:** Put executions, users, results, and artifacts metadata in the knowledge graph because "it's all connected."
**Why it's wrong:** Graph DBs are poor at high-volume append-only records and relational reporting; dashboards become slow Cypher; backups and migrations get painful.
**Do this instead:** Neo4j = app structure model. PostgreSQL = system of record. Mirror only the traceability edges you query as graphs.

### Anti-Pattern 4: Synchronous Long Operations over HTTP

**What people do:** `POST /explore` blocks until the crawl finishes.
**Why it's wrong:** Crawls run minutes–hours; timeouts, no resumability, no progress.
**Do this instead:** Every long operation returns a job ID; work flows through RabbitMQ; progress streams via Redis pub/sub → SSE; LangGraph checkpoints make jobs resumable.

### Anti-Pattern 5: Silent, Unvalidated Healing

**What people do:** Best similarity match silently replaces the locator and the test "passes."
**Why it's wrong:** A wrong heal converts a real product defect into a green test — the worst possible failure mode for a QA platform.
**Do this instead:** Enforce a score threshold, re-validate the healed locator against the live page, record every heal as an auditable versioned change (workspace commit + DB row), and surface heals in the QA dashboard for review.

### Anti-Pattern 6: Freehand LLM Selectors in Generated Code

**What people do:** Let the codegen LLM write whatever CSS/XPath it imagines.
**Why it's wrong:** Hallucinated selectors; no link back to the KG, so healing and traceability break.
**Do this instead:** Codegen may only reference Element Repository entries; locator strings are emitted from stored fingerprints in priority order (data-testid → aria → role → text → xpath).

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Jira Cloud | REST v3, API token; outbox queue + idempotency fingerprint (app+flow+error signature) | Descriptions use ADF (Atlassian Document Format), not markdown; attach screenshots/video via separate attachments endpoint; respect rate limits with backoff |
| LLM providers (Anthropic/OpenAI) | Single internal gateway; per-call model selection; Redis response cache; token metering to Prometheus | Keep prompts in `agents/llm/prompts/` versioned; structured outputs validated with Pydantic before use |
| Target web apps | Playwright only, via Explorer/workers; credentials encrypted at rest, injected per session | Use storage-state reuse for login to avoid re-authenticating every page visit during crawls |
| GitHub Actions | CI runs platform tests + can trigger `/execute` for regression suites | Workers' sharding model maps directly onto CI matrix jobs |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Next.js ↔ FastAPI | REST + SSE/WebSocket | Single typed client in `apps/web/lib/api`; RBAC enforced server-side per dashboard |
| FastAPI ↔ agentic plane | RabbitMQ jobs + LangGraph run triggers; status via PostgreSQL/Redis | API never imports agent code paths that drive browsers |
| Agents ↔ Neo4j | Only through KG Writer (events → Cypher) | Preserves one schema dialect; enables KG versioning |
| Agents/Workers ↔ LLM | Only through LLM gateway | Provider-agnostic constraint lives here and nowhere else |
| Execution Engine ↔ Workers | RabbitMQ `execution.jobs` / results messages | Message schemas in `shared/events/`; workers are language-independent (Node) because the contract is the queue |
| Healing ↔ Workspace | Versioned writes (commit per heal) + Element Repository update | Audit trail requirement |

## Sources

- [Playwright MCP — official docs](https://playwright.dev/mcp/introduction) and [Playwright getting started with MCP](https://playwright.dev/docs/getting-started-mcp) — accessibility-snapshot-based agent architecture (HIGH confidence)
- [Playwright and Playwright MCP: A Field Guide for Agentic Browser Automation](https://medium.com/@adnanmasood/playwright-and-playwright-mcp-a-field-guide-for-agentic-browser-automation-f11b9daa3627) — snapshot token economics, ref-based action model (MEDIUM)
- [Browser Tools for AI Agents: framework wars (browser-use, Stagehand, Skyvern)](https://dev.to/stevengonsalvez/browser-tools-for-ai-agents-part-2-the-framework-wars-browser-use-stagehand-skyvern-4gn) and [Browser Agent Frameworks Compared](https://bytetunnels.com/posts/browser-agent-frameworks-compared-browser-use-vs-stagehand-vs-skyvern/) — DOM/tree vs vision reliability comparison, Skyvern Planner–Actor–Validator (MEDIUM)
- [Skyvern](https://www.skyvern.com/) — vision-first agent architecture (MEDIUM)
- [LangGraph Multi-Agent Supervisor reference](https://reference.langchain.com/python/langgraph-supervisor) — supervisor pattern, subgraphs (HIGH)
- [LangGraph in Practice: orchestrating multi-agent systems at scale](https://bix-tech.com/langgraph-in-practice-orchestrating-multiagent-systems-and-distributed-ai-flows-at-scale/) and [LangGraph deep dive: stateful multi-agent systems](https://www.mager.co/blog/2026-03-12-langgraph-deep-dive/) — checkpointing/resume-on-crash for long workflows (MEDIUM)
- [Healenium-web (official repo)](https://github.com/healenium/healenium-web) and [Healenium architecture walkthrough](https://www.automatetheplanet.com/healenium-self-healing-tests/) — proxy interception, weighted LCS similarity scoring, score-cap threshold (HIGH for the pattern)
- [Scaling Playwright tests on Kubernetes with Testkube](https://testkube.io/blog/scaling-playwright-tests-testkube) and [Building a custom Playwright hub on Kubernetes](https://medium.com/@vinaykarumuri15/building-a-custom-playwright-hub-scalable-browser-automation-in-kubernetes-3bbda4666d26) — queue-held browser allocation, KEDA scaling on queue depth (MEDIUM)
- [Playwright parallelism — official docs](https://playwright.dev/docs/test-parallel) — workers vs sharding (HIGH)
- [Crawljax](https://github.com/crawljax/crawljax) — state-flow-graph model of crawled web apps; lineage for the knowledge-graph approach (HIGH for the pattern)
- [NaviQAte: functionality-guided web application navigation](https://arxiv.org/pdf/2409.10741) — LLM-guided exploration research (MEDIUM)
- [Agentic QA architecture: reasoning loops, self-healing DOM](https://testquality.com/agentic-qa-architecture-autonomous-testing-2026/) — plan–act–verify orchestration layer above execution engines (LOW-MEDIUM, single vendor source)

---
*Architecture research for: autonomous AI web-app testing platform*
*Researched: 2026-06-11*
