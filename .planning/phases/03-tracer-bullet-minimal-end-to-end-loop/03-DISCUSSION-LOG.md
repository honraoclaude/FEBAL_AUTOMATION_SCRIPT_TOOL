# Phase 3: Tracer Bullet — Minimal End-to-End Loop - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-13
**Phase:** 3-Tracer Bullet — Minimal End-to-End Loop
**Areas discussed:** Neo4j on a constrained host, Long-running job model, Tracer Explorer minimalism

---

## Neo4j on a 5.7 GB host (the carried blocker)

### Hosting approach
| Option | Description | Selected |
|--------|-------------|----------|
| Local trimmed Neo4j + stop web during explore | neo4j:2025 small heap + mem_limit ~1g; stop web (1.5g) during exploration; keeps all-local constraint | ✓ |
| Neo4j Aura free tier (remote managed) | Zero local RAM, cloud dependency, bends all-local constraint | |
| Raise WSL cap during graph work | Risky — engine wedged at 16g; 5.7g total starves Windows | |

**User's choice:** Local trimmed Neo4j + stop web during explore

### Operational mechanism
| Option | Description | Selected |
|--------|-------------|----------|
| Scripted helper | One repeatable command stops web, ensures neo4j healthy, restores web; neo4j behind 'graph' profile | ✓ |
| Documented manual steps | Dev-docs commands; easy to forget a step and OOM | |

**User's choice:** Scripted helper

### Heap/pagecache sizing
| Option | Description | Selected |
|--------|-------------|----------|
| Minimal: heap 512m, pagecache 256m, mem_limit 1g | Ample for the tiny tracer graph; headroom under cap | ✓ |
| Conservative: heap 1g, pagecache 512m, mem_limit 2g | Too risky — ~3.9g even with web stopped | |

**User's choice:** Minimal sizing

---

## Long-running job model (/explore, /execute) — no RabbitMQ until Phase 7

### Execution model
| Option | Description | Selected |
|--------|-------------|----------|
| Async-style: 202 + run_id, BackgroundTasks, poll via GET | Mirrors eventual queue contract; Phase 7 swaps to RabbitMQ with no API change | ✓ |
| Synchronous: POST blocks until done | Simplest but blocks request; forces API change in Phase 7 | |

**User's choice:** Async-style (202 + run_id + BackgroundTasks + poll)

### Event-layer scope
| Option | Description | Selected |
|--------|-------------|----------|
| Define schemas only (Pydantic in shared/events/) | Message contracts now; broker/aio-pika later | ✓ |
| Define schemas + thin queue abstraction | In-process publish/consume interface now; over-design risk | |

**User's choice:** Define schemas only

---

## Tracer Explorer minimalism (full Explorer is Phase 4)

### Exploration approach
| Option | Description | Selected |
|--------|-------------|----------|
| Deterministic Playwright crawl, no LLM in explore | login + landing Page node + one NavigatesTo edge; LLM exercised by generate steps | ✓ |
| Minimal LLM-driven explore step | One gateway perception call; adds non-determinism + Phase-4 scope creep | |

**User's choice:** Deterministic Playwright crawl

### LangGraph timing
| Option | Description | Selected |
|--------|-------------|----------|
| Defer LangGraph to Phase 4 | Deterministic crawl has no loop to orchestrate | ✓ |
| Introduce minimal StateGraph now | Overhead the tracer doesn't exercise | |

**User's choice:** Defer to Phase 4

---

## Claude's Discretion

- Stub contract for the 5 unbuilt endpoints (heal, create-defect, flows, coverage, dashboard): 501 Not Implemented + documented OpenAPI contracts (complete + honest surface, no fabricated results).
- Generated-artifact storage layout under workspaces/<run_id>/ and how /execute locates the spec.
- Minimal Neo4j Cypher write seam (direct driver, not the Phase-5 single-writer).
- How a single run_id threads explore → generate → execute → result.

## Deferred Ideas

- Intelligent Explorer / perception / budgets / risk / fingerprints → Phase 4
- LangGraph + checkpoint-postgres → Phase 4
- Real KG single-writer + idempotent MERGE + flow mining → Phase 5
- RabbitMQ + aio-pika workers + suite tiers + artifacts → Phase 7
- Review queue + N-run stability / healing / defect+Jira / dashboards → Phases 6/8/9/10
- Neo4j memory re-tuning / more RAM / managed Neo4j → revisit Phase 5
