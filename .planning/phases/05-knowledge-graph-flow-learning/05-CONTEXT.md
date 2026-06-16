# Phase 5: Knowledge Graph & Flow Learning - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning (needs --research-phase — Cypher schema + MERGE reconciliation have no canonical reference)

<domain>
## Phase Boundary

Turn the Explorer's raw Neo4j writes into a PROPER knowledge graph: a single-writer service as the only write path, idempotent fingerprint-based MERGE (re-exploring an unchanged app yields ~0 duplicate nodes) with first_seen/last_verified freshness, a Flow Learning Engine that derives + risk-scores business workflows, a tabular graph-browse UI, and a ground-truth coverage measurement (QUAL-01 trust gate: >80% vs a hand-labeled SauceDemo graph). Delivers KG-01..KG-05 + QUAL-01. Extends the Phase-4 explorer (refactors its direct writes to go through the writer) and makes the Phase-3 GET /flows + /coverage stubs real. UI hint: yes (browse UI → needs a UI-SPEC).

**In scope:** the single-writer KG service (all Cypher/MERGE/freshness), the canonical node/edge schema, idempotent fingerprint-MERGE + freshness, the Element Repository (locator chain + history queryable per element), the Flow Learning Engine (path-mining + LLM categorization + deterministic risk score), real GET /flows + /coverage + graph/pages read endpoints, the tabular browse UI, and the ground-truth fixture + coverage metric.
**Out of scope (own phases):** BDD/Playwright generation from flows (Phase 6), execution/healing/defect/dashboards (7-10), a node/edge graph VISUALIZATION (deferred enhancement — tabular browse this phase), RabbitMQ-fronted async writing (Phase 7 may put a queue before the writer). The live ≥80% coverage gate + live LLM flow categorization need provider keys — Manual-Only (keys empty by design).

</domain>

<decisions>
## Implementation Decisions

### Single-writer KG service (KG-05)
- **D-01:** A SYNCHRONOUS, in-process KG writer service is the ONLY Neo4j write path. The explorer's persist node calls `kg_writer.upsert_*(...)` directly (same BackgroundTask); the writer owns ALL Cypher, fingerprint-MERGE, and freshness. No broker/queue this phase (Phase 7 may front it with a queue without changing callers).
- **D-02:** Phase 4's direct Neo4j write code is REFACTORED, not wrapped: the `persist_to_neo4j` Cypher moves INTO the writer service; the explorer node calls `writer.upsert_page/upsert_element/...` and writes NO Cypher itself. A grep/test enforces zero Cypher write statements outside the writer module (true single write path). The SC1 lesson is preserved INSIDE the writer: every write uses managed `execute_write` + a read-back guard; parameterized Cypher only.

### Flow Learning Engine (KG-04)
- **D-03:** HYBRID flow derivation — DETERMINISTIC graph path-mining traverses the KG (NavigatesTo/Submits/state-change edges) to find candidate user journeys; the LLM (via `llm_gateway.complete`, operation_type like `flow.categorize`, run_id) categorizes/names them as business workflows. Deterministic structure (testable, no keys) + LLM semantics (the categorization needs keys to demo — Manual-Only half).
- **D-04:** Risk score is a DETERMINISTIC, explainable 0-100 formula from graph signals — presence of destructive actions, count of state-changing edges (Submits/Creates/Updates/Deletes), auth-gated steps, path depth/length, form count. Reproducible, unit-testable, free, auditable (NOT LLM judgment — a score users act on must be deterministic). The exact weights are tunable (research/plan to propose; make the formula a pure, swappable function).

### Graph browse UI (KG-02)
- **D-05:** STRUCTURED TABULAR/LIST browse (NO new graph-viz library): a Pages list, a Flows list with risk-score badges, and an Element Repository view (locator chain + history), each showing relationships/edges as drill-in links. Built with the already-vendored shadcn table/card/badge — zero new deps. A node/edge graph VISUALIZATION is explicitly DEFERRED as a later enhancement (avoids a package gate + hairball rendering on a constrained host). UI-SPEC needed (the plan-phase UI gate will require one).
- **D-06:** Read API — make the Phase-3 501 stubs REAL: `GET /flows` (flows + risk scores), `GET /coverage` (% vs ground truth), plus a graph/pages read endpoint — all read-only Cypher behind the existing `Depends(get_current_user)` gate. Honest completion of those PLAT-02 endpoints.

### Ground-truth coverage (QUAL-01, the trust gate)
- **D-07:** Ground truth is a COMMITTED hand-authored fixture (YAML/JSON, e.g. `tests/fixtures/ground_truth/saucedemo.{yaml,json}`) enumerating SauceDemo's canonical pages + key flows, hand-labeled once. Version-controlled, diffable, no live deps; the coverage metric reads it as the reference.
- **D-08:** Coverage = matched ground-truth pages/flows ÷ ground-truth total (page match by fingerprint / normalized-url). The COMPUTATION logic is unit-tested DETERMINISTICALLY against a fixture KG (no keys). The actual ≥80%-on-a-real-discovered-graph GATE needs a live exploration (keys) → it's the documented Manual-Only/live item, surfaced via GET /coverage.

### Claude's Discretion / for research (--research-phase)
- **Canonical Cypher node/edge schema** (KG-01): Page/Form/Workflow/Button/BusinessEntity nodes + NavigatesTo/Submits/Creates/Updates/Deletes edges. BusinessEntity is NEW (not in Phase 4) — research what counts as a business entity on SauceDemo (products? cart items?) and the minimal-but-real modeling. Property sets per node/edge.
- **Idempotent fingerprint-MERGE + freshness reconciliation** (KG-03, the flagged unknown): MERGE keyed on the Phase-4 structural fingerprint; first_seen set ON CREATE, last_verified set every run; how stale/absent nodes are handled on re-exploration (mark stale vs leave; do NOT delete this phase). Prove ~0 duplicates on a re-run.
- **Element Repository query surface** (KG-05 half): elements + locator chain + history queryable per element — the read API + storage (extend the Phase-4 Element nodes).
- **Flow path-mining algorithm** + risk-formula weights; how journeys are bounded (avoid combinatorial explosion on a large graph).
- **Coverage matching rule** specifics (fingerprint vs normalized-url page identity; flow matching).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — KG-01..KG-05 + QUAL-01.
- `.planning/ROADMAP.md` (Phase 5 section) — the 5 success criteria are the contract (persist + browse; idempotent MERGE + freshness on re-explore; flow learning + risk scores; single-writer + Element Repository; >80% ground-truth coverage).

### Locked stack & prior decisions
- `CLAUDE.md` — neo4j 6.2 driver (AsyncGraphDatabase, parameterized Cypher); init_chat_model via the Phase-2 gateway ONLY (flow categorization); Recharts is the only viz primitive (charts, not graphs) — confirms no node-graph lib is locked (D-05 tabular choice). neo4j single-writer + idempotent MERGE pattern is the "Stack Patterns" KG note.
- `.planning/phases/04-explorer-agent/04-01..04-SUMMARY.md` — the explorer/ package: persist_to_neo4j (the Cypher to move into the writer), the structural fingerprint module (the MERGE key), Element nodes + locator chain/history, run_id threading, execute_write+read-back, graph_mode. The writer refactor builds directly on these.
- `.planning/phases/03-tracer-bullet-minimal-end-to-end-loop/03-04-SUMMARY.md` — the GET /flows + /coverage 501 stubs to make real; the run/executions model.
- `.planning/phases/02-llm-gateway/02-01-SUMMARY.md` — llm_gateway.complete(operation_type, run_id) for flow categorization.
- `.planning/phases/01-foundation-dev-environment/01-04-SUMMARY.md` + `04-UI-SPEC.md` — the locked design system (shadcn new-york/zinc) the browse UI reuses; the app shell/sidebar/table patterns.

### Memory / known issues
- `graph_mode down` leaves neo4j running (manual stop needed) — fix before this phase leans on graph_mode heavily.
- Provider keys empty in .env → live LLM flow categorization + the live ≥80% coverage gate are Manual-Only (the project-wide note in STATE.md).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `apps/api/app/services/explorer/` (Phase 4): persist_to_neo4j Cypher → moves into the new writer; the structural fingerprint module → the MERGE key; Element nodes + locator chain/history → the Element Repository; the LangGraph loop's persist node → delegates to the writer.
- `apps/api/app/core/neo4j_driver.py` — lifespan AsyncDriver (liveness_check_timeout set); the writer uses session.execute_write.
- `apps/api/app/services/llm_gateway.complete()` — flow categorization routes through it (operation_type + run_id).
- `apps/api/app/routers/stubs.py` (Phase 3) — the GET /flows + /coverage 501 stubs to replace with real read endpoints (move them to a real router or implement in place).
- `apps/api/app/services/run_service.py` — run/executions lifecycle (coverage tied to a run).
- `apps/web/` shell + targets/explore pages + the locked design system — the browse UI is new authenticated pages reusing shadcn table/card/badge.
- `infra/scripts/graph_mode.py` — KG read/write functional tests run under graph_mode (neo4j up, web down).

### Established Patterns
- Functional tests hit the live stack; graph-marked under graph_mode. Deterministic logic (writer MERGE/freshness on a fixture, risk formula, coverage metric, path-mining) unit-tested with fixtures + mocked gateway (no keys). Live flow categorization + ≥80% coverage on a real discovered graph = live_llm/manual.
- Carry forward: managed execute_write + read-back (now centralized in the writer), parameterized Cypher, single decrypt surface, fresh SessionLocal per BackgroundTask.

### Integration Points
- New kg_writer service (the single write path) + explorer refactor; new flow-learning module; new coverage module + ground-truth fixture; real GET /flows + /coverage + graph/pages read router; new web browse pages; possibly an Alembic migration if any run/coverage fields are added (Neo4j schema is NOT Alembic).

</code_context>

<specifics>
## Specific Ideas

- KG-05 "only write path" is enforced structurally: a grep/test that no Cypher write (MERGE/CREATE/SET/DELETE) exists outside the writer module. The explorer's persist node becomes a thin delegate.
- Risk score is deterministic on purpose — a number users act on must be reproducible + auditable; the LLM is used only to NAME/categorize flows, never to score risk.
- The >80% coverage gate is the trust gate (QUAL-01): the metric logic ships + is unit-tested now; the live ≥80% proof on a real SauceDemo discovery is gated on provider keys (Manual-Only), same posture as Phase 4's live exploration.
- Idempotency proof (KG-03): a deterministic test re-runs the writer over the same fixture node set and asserts ~0 new nodes + last_verified bumped — provable WITHOUT keys.

</specifics>

<deferred>
## Deferred Ideas

- Node/edge graph VISUALIZATION (react-flow/cytoscape) — deferred; tabular browse this phase. Revisit as an enhancement if the tabular view proves insufficient.
- RabbitMQ-fronted async KG writing — Phase 7 may put a queue before the writer; in-process synchronous this phase (D-01).
- Stale/deleted-node garbage collection on re-exploration — this phase marks freshness (last_verified) but does NOT delete stale nodes; GC strategy deferred.
- Richer flow categorization / cross-app flow libraries — beyond single-target journeys is out of scope.
- LLM-based risk scoring — explicitly rejected (D-04 deterministic); not revisited.

None of these block Phase 5 — discussion stayed within the KG + flow-learning scope.

</deferred>

---

*Phase: 5-Knowledge Graph & Flow Learning*
*Context gathered: 2026-06-16*
