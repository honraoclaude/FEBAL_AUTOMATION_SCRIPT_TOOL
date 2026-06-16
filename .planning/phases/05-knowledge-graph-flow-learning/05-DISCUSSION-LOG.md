# Phase 5: Knowledge Graph & Flow Learning - Discussion Log

> **Audit trail only.** Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-16
**Phase:** 5-Knowledge Graph & Flow Learning
**Areas discussed:** Single-writer architecture, Flow Learning Engine, Graph browse UI, Ground-truth coverage

---

## Single-writer architecture (KG-05)

### Write path
| Option | Description | Selected |
|--------|-------------|----------|
| Synchronous in-process writer service | persist node calls kg_writer directly; writer owns Cypher/MERGE/freshness; no broker | ✓ |
| Event-driven (explorer publishes, writer consumes) | decoupled but RabbitMQ is Phase 7; in-process pub/sub now = added indirection | |

**User's choice:** Synchronous in-process writer service

### Phase-4 refactor
| Option | Description | Selected |
|--------|-------------|----------|
| Refactor: move Cypher into writer; explorer delegates | true single write path; grep/test enforces zero Cypher outside writer | ✓ |
| Wrap: keep Phase-4 writes, add writer alongside | less churn but two write surfaces; violates KG-05 | |

**User's choice:** Refactor (single write path, execute_write+read-back kept inside the writer)

---

## Flow Learning Engine (KG-04)

### Flow derivation + categorization
| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: deterministic path-mining + LLM categorization | mine journeys deterministically; LLM names them as business workflows | ✓ |
| Fully deterministic (heuristic naming) | cheap/reproducible but weak business-workflow semantics | |
| Fully LLM-driven | most semantic; expensive, less reproducible, hard to bound | |

**User's choice:** Hybrid (path-mining + LLM categorization via gateway)

### Risk score
| Option | Description | Selected |
|--------|-------------|----------|
| Deterministic formula from graph signals | explainable 0-100 from destructive actions/state-changes/auth/depth/forms; testable, free | ✓ |
| LLM judgment | holistic but non-deterministic, needs keys, hard to audit | |

**User's choice:** Deterministic formula (LLM only names flows, never scores risk)

---

## Graph browse UI (KG-02)

### Visualization approach
| Option | Description | Selected |
|--------|-------------|----------|
| Structured tabular/list browse, no new viz lib | Pages/Flows(risk)/Element Repository tables + drill-in links; shadcn only | ✓ |
| Interactive node/edge graph viz | real graph picture via react-flow/cytoscape; package gate + hairball risk | |
| Hybrid: tables + lightweight graph view | more complete; still needs a viz lib + more build | |

**User's choice:** Tabular/list browse (node-graph viz deferred)

### Read API
| Option | Description | Selected |
|--------|-------------|----------|
| Make Phase-3 /flows + /coverage stubs real + graph/pages read | honest completion of those PLAT-02 endpoints | ✓ |
| New dedicated KG read endpoints only | leaves /flows + /coverage stubbed when this phase is their purpose | |

**User's choice:** Make the 501 stubs real + add graph/pages read

---

## Ground-truth coverage (QUAL-01, trust gate)

### Ground-truth storage
| Option | Description | Selected |
|--------|-------------|----------|
| Committed hand-authored fixture (YAML/JSON) | version-controlled canonical reference; diffable; no live deps | ✓ |
| Labeled reference graph in Neo4j | queryable but hard to author/diff/version; couples to a running DB | |

**User's choice:** Committed fixture

### Coverage gate computation
| Option | Description | Selected |
|--------|-------------|----------|
| Set-overlap metric, unit-tested on fixture KG; live ≥80% = Manual-Only | metric logic proven w/o keys; live gate needs a real exploration | ✓ |
| Live-only (compute solely from a real exploration) | truer but unprovable without keys; no deterministic metric test | |

**User's choice:** Set-overlap metric unit-tested on a fixture; live ≥80% is the Manual-Only gate

---

## Claude's Discretion / for research

- Canonical Cypher node/edge schema (Page/Form/Workflow/Button/BusinessEntity + NavigatesTo/Submits/Creates/Updates/Deletes); BusinessEntity is new — what counts on SauceDemo
- Idempotent fingerprint-MERGE + freshness reconciliation (first_seen/last_verified; stale-node handling, no deletes this phase)
- Element Repository query surface
- Path-mining algorithm + risk-formula weights + journey bounding
- Coverage matching rule (page identity by fingerprint vs normalized-url; flow matching)

## Deferred Ideas

- Node/edge graph visualization → later enhancement
- RabbitMQ-fronted async KG writing → Phase 7
- Stale/deleted-node GC on re-exploration → deferred (mark freshness only this phase)
- LLM-based risk scoring → rejected (deterministic by decision)
