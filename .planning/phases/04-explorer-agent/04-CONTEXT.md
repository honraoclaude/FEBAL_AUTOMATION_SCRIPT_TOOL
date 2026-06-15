# Phase 4: Explorer Agent - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning (needs --research-phase — most novel component)

<domain>
## Phase Boundary

Replace Phase 3's deterministic tracer crawl with a REAL autonomous Explorer: point the platform at a registered app and it maps pages, workflows, and elements on its own — converging, staying safe, and staying on budget — with a live progress view. Extends the existing `apps/api/app/services/explorer.py` / `routers/explore.py` / `core/neo4j_driver.py` seam, finally introduces LangGraph (deferred from Phase 3), and adds an SSE live view (UI hint: yes). Delivers EXPL-01..EXPL-09.

**In scope:** snapshot-first LLM-driven exploration loop (LangGraph raw StateGraph + Postgres checkpointing), auth handling (login-form detection, credential injection, storageState reuse, logout recovery), page/form/menu/button/link/table discovery with a screenshot per state, normalized-DOM-fingerprint state dedup (not URL), multi-step workflow + form-validation detection, code-enforced budgets + loop detection + convergence, action risk policy (deny-list, sandbox-gated), untrusted-content delimiting + origin allowlist, per-element prioritized locator chain + history, and the SSE live progress UI.
**Out of scope (own phases):** the real single-writer Knowledge Graph with idempotent fingerprint MERGE + freshness + flow mining + risk scores (Phase 5 — this phase writes richer nodes/edges but the canonical KG service is Phase 5), BDD/Playwright generation (Phase 6), distributed execution + MinIO artifact store (Phase 7 — screenshots live under workspaces/ for now), healing (Phase 8). The Phase-2 LLM gateway already owns token/$ budgets + kill-switch — do NOT re-implement spend tracking.

</domain>

<decisions>
## Implementation Decisions

### Perception (the core agent loop)
- **D-01:** Snapshot-first perception — feed the LLM a COMPACTED DOM/accessibility-tree snapshot (roles, labels, interactable elements), NOT raw HTML and NOT pixels. Matches CLAUDE.md "snapshot-first". A screenshot is still captured per discovered state as evidence (EXPL-03) but is NOT sent to the LLM (no vision model this phase).
- **D-02:** The LLM CHOOSES the next action from a heuristic-enumerated CONSTRAINED MENU — code enumerates the candidate interactable elements/actions from the snapshot; the LLM picks among them (and flags multi-step workflows). No freehand LLM selectors. This bounds tokens and keeps the budget/loop logic deterministic around the LLM.

### Action risk policy & untrusted content (safety)
- **D-03:** Destructive actions are refused by a CODE-ENFORCED deny-list + safe-verb default, evaluated BEFORE the action runs — NOT LLM judgment. Deny signals: delete/remove/send/pay/submit-order/checkout/logout/etc. in element label/role/confirm-text; allow safe navigation/read/form-fill by default. The target's `sandbox` flag (already on the Target model, Phase 1) lifts the deny for restorable targets (EXPL-07). Deterministic = auditable + testable.
- **D-04:** Page-derived text is wrapped in clear delimiters and labeled "untrusted observation" in the LLM prompt (never as instructions) — prompt-injection defense (EXPL-08). Navigation is restricted to the target's origin allowlist (already on the Target model) BY CODE, refusing off-origin links — not left to LLM discretion.

### Convergence & budgets (termination)
- **D-05:** The Explorer STOPS on saturation (no NEW fingerprinted states discovered for N consecutive steps) OR any code-enforced budget cap, whichever first. Saturation is what makes two consecutive runs converge to ~the same graph (EXPL-05); budgets are the hard backstop guaranteeing halt.
- **D-06:** Budget layering — the Explorer code enforces EXPLORATION caps (max steps, max depth, revisits-per-fingerprint, wall-clock) plus a loop detector. Token/USD spend stays enforced by the Phase-2 gateway pre-check; the Explorer passes the run_id so the per-run token budget binds. NO duplicate spend tracking in the Explorer.

### Live progress UX (EXPL-01)
- **D-07:** Event flow: the in-process explorer (BackgroundTask, now LangGraph-driven) PUBLISHES step events to Redis pub/sub; a GET SSE endpoint (sse-starlette) subscribes and streams to the browser's EventSource. Decouples worker from connection and is the SAME seam Phase 7's RabbitMQ workers will publish into. Redis is already the lifespan client; sse-starlette must be added (in CLAUDE.md stack, not yet installed).
- **D-08:** The live view shows: header counters (pages found, actions taken, cost so far, elapsed vs budget); a scrolling per-step action feed (navigated to X, clicked Y, found form Z); and the current page title/URL + latest screenshot thumbnail. (UI-SPEC needed — frontend phase; the plan-phase UI gate will require one.)

### Claude's Discretion / for research (--research-phase)
- **Fingerprint normalization algorithm** (THE flagged experimental unknown): how to normalize the DOM into a stable state fingerprint that collapses duplicate states and distinguishes template states from instance data (EXPL-06). Research must propose + the plan must make it tunable/testable.
- **LangGraph StateGraph structure**: nodes (navigate → perceive/snapshot → enumerate-actions → LLM-decide → act → persist-to-Neo4j → check-convergence/budget → loop), state schema, and langgraph-checkpoint-postgres wiring for resumable/cancellable runs (CLAUDE.md: raw StateGraph, NOT the prebuilt create_agent).
- **Element locator chain** (EXPL-09): extraction + priority order data-testid → aria-label → role → text → xpath, plus per-element locator history. Research the extraction approach.
- **Auth handling** (EXPL-02): login-form detection, credential injection via the single decrypt surface (target_service.get_decrypted_credentials), Playwright storageState capture/reuse, logout detection + re-login recovery mid-run.
- **Screenshot storage**: under the gitignored workspaces/<run_id>/ tree for now (MinIO is Phase 7); record paths on the graph/run.
- **Workflow + form-validation detection** (EXPL-04): how multi-step sequences and validation rules are recognized and recorded from the exploration.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — EXPL-01..EXPL-09 (the nine requirements this phase delivers).
- `.planning/ROADMAP.md` (Phase 4 section) — the 5 success criteria are the contract (live view; auto-login + logout recovery; SauceDemo discovery + convergence on two runs with fingerprint dedup; workflow + validation detection; risk refusal + origin allowlist + untrusted input + locator chains).

### Locked stack & prior decisions
- `CLAUDE.md` — langgraph 1.2.x (raw StateGraph for the Explorer, NOT prebuilt create_agent), langgraph-checkpoint-postgres 3.1.x (resumable runs in the Postgres you already run), langchain-core/init_chat_model via the Phase-2 gateway ONLY, playwright 1.60 async, sse-starlette 3.4.x (live view), neo4j 6.2 driver, langsmith optional. The "Stack Patterns by Variant" note: "Raw StateGraph ... explicit nodes (navigate → extract → classify → persist-to-Neo4j → decide-next)" — this phase's loop.
- `.planning/phases/02-llm-gateway/02-01-SUMMARY.md` + `02-02-SUMMARY.md` — llm_gateway.complete(operation_type, run_id, ...) is the ONLY LLM path; budgets/kill-switch/caching already enforced; pass run_id so per-run token budget binds (D-06).
- `.planning/phases/03-tracer-bullet-minimal-end-to-end-loop/03-02-SUMMARY.md` — the explorer.py/explore.py/neo4j_driver seam this phase extends; run/executions model + status machine + run_id threading + poll; graph_mode (web down, neo4j up) is how explore runs under the 3GB cap; the SC1 lesson: Neo4j writes MUST use managed execute_write + a read-back guard (a no-op write must fail, never report passed).
- `.planning/phases/01-foundation-dev-environment/01-05-SUMMARY.md` — Target model carries `sandbox` flag + `origin_allowlist` + `budget_overrides`; get_decrypted_credentials is the single decrypt surface (auth uses it).

### Memory / known issues
- See memory `gherkin-pytest-bdd-conflict` (Phase 6 relevance, not this phase).
- `graph_mode down` currently leaves neo4j running (manual stop needed) — minor infra bug to fix before this phase leans on graph_mode heavily.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `apps/api/app/services/explorer.py` — the tracer crawl to EVOLVE into the LangGraph agent (keep run_id threading, fresh SessionLocal in the BackgroundTask, managed execute_write + read-back guard for Neo4j writes).
- `apps/api/app/services/llm_gateway.complete()` — the only LLM path; pass operation_type (e.g. explore.perceive / explore.decide) + run_id.
- `apps/api/app/core/neo4j_driver.py` — lifespan AsyncDriver (liveness_check_timeout already set for graph_mode restarts); use session.execute_write for all writes.
- `apps/api/app/services/run_service.py` — run/executions status machine + get_status_by_run_id; reuse for explore run lifecycle + the SSE-backing status.
- `apps/api/app/core/redis_client.py` — lifespan redis client; the pub/sub backbone for SSE progress (D-07).
- `apps/api/app/models/target.py` — sandbox flag + origin_allowlist + budget_overrides feed D-03/D-04/D-06.
- `infra/scripts/graph_mode.py` — explore runs under graph_mode (neo4j up, web down); functional/e2e tests use it.
- `apps/web/` — Next.js shell + targets UI; the live exploration view is a new authenticated page (UI-SPEC needed).

### Established Patterns
- Functional tests hit the live stack; graph-marked tests run under graph_mode. The live LLM exploration is real spend → a live_llm/manual proof; deterministic logic (risk classifier, fingerprint, budget/loop, convergence, SSE event shapes) is unit-tested with a mocked gateway + fixture snapshots (no spend).
- Secrets via env; provider keys already in .env contract. New deps (langgraph, langgraph-checkpoint-postgres, sse-starlette) need a package-legitimacy gate at plan time.

### Integration Points
- explorer.py (LangGraph agent), new perception/risk/fingerprint/locator modules, run_service (lifecycle + events), neo4j writes (richer nodes/edges), redis pub/sub + a new SSE router, a new web live-exploration page, Alembic migration for langgraph-checkpoint-postgres tables + any explore run fields.

</code_context>

<specifics>
## Specific Ideas

- This is the project's MOST NOVEL phase — plan with `--research-phase`. The fingerprint normalization is the single biggest unknown (flagged for experimentation); budget/loop/convergence and the risk classifier are deterministic and testable; perception/decide is the LLM-in-the-loop part.
- Safety is deterministic by deliberate choice: the destructive-action gate and origin allowlist are CODE, enforced before the action — never LLM judgment (a non-deterministic, prompt-injectable safety gate is unacceptable).
- Carry the SC1 lesson from Phase 3: every Neo4j write uses managed execute_write + a read-back; a write that persists nothing must FAIL the run, never log success.
- Phase is large (9 reqs). Consider whether research recommends a SPEC or a phase split; MVP vertical slices should still each be demonstrable (e.g. slice: perceive+decide+act loop with budgets/convergence on SauceDemo; slice: auth + fingerprint dedup; slice: risk policy + untrusted/origin guards + locator chains; slice: SSE live view + UI).

</specifics>

<deferred>
## Deferred Ideas

- Real single-writer Knowledge Graph (idempotent fingerprint MERGE, freshness first_seen/last_verified, flow mining, risk scores) → Phase 5. This phase writes the nodes/edges; the canonical KG service + dedup-by-MERGE is Phase 5.
- Vision/multimodal perception (screenshots to the LLM) → deferred; revisit only if a target needs canvas/visual-only UIs. Screenshots are evidence only this phase.
- MinIO artifact store for screenshots/video/traces → Phase 7; workspaces/<run_id>/ for now.
- Distributed/parallel exploration via RabbitMQ workers → Phase 7; in-process BackgroundTasks + LangGraph this phase.
- Per-operation-type LLM budgets → still deferred (Phase-2 deferred item); the gateway's per-run token budget + Explorer step/depth caps suffice.

None of these block Phase 4 — discussion stayed within the autonomous-explorer scope.

</deferred>

---

*Phase: 4-Explorer Agent*
*Context gathered: 2026-06-15*
