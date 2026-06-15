# Phase 4: Explorer Agent - Discussion Log

> **Audit trail only.** Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-15
**Phase:** 4-Explorer Agent
**Areas discussed:** Perception strategy, Action risk policy + untrusted content, Convergence & budgets, Live progress UX

---

## Perception strategy

### How it perceives
| Option | Description | Selected |
|--------|-------------|----------|
| Snapshot-first: compacted DOM/a11y tree | pruned structured snapshot to LLM; screenshots as evidence only | ✓ |
| Vision: screenshots to multimodal LLM | handles visual UIs; pricier/slower/noisier | |
| Hybrid: snapshot + screenshot | most robust + most expensive | |

**User's choice:** Snapshot-first (screenshots captured per state but NOT sent to LLM)

### LLM role in navigation
| Option | Description | Selected |
|--------|-------------|----------|
| LLM picks from heuristic-enumerated constrained menu | no freehand selectors; bounded tokens; deterministic budget/loop | ✓ |
| LLM fully drives (free-form) | autonomous but loop/spend risk | |
| Mostly heuristic, LLM only for ambiguity | cheapest; weak at workflow discovery | |

**User's choice:** LLM picks from constrained menu

---

## Action risk policy + untrusted content

### Destructive-action gate
| Option | Description | Selected |
|--------|-------------|----------|
| Deterministic deny-list + safe-verb default, code-enforced | before action; sandbox flag lifts; auditable/testable | ✓ |
| LLM classifies risk | non-deterministic safety; injectable | |
| Allowlist only | safest but too restrictive for workflow discovery | |

**User's choice:** Deterministic deny-list, code-enforced (sandbox-gated)

### Untrusted page content
| Option | Description | Selected |
|--------|-------------|----------|
| Delimit+label page text + code-enforced origin allowlist | prompt-injection + off-origin defense, both deterministic | ✓ |
| Origin allowlist only | leaves snapshot LLM open to embedded instructions | |

**User's choice:** Delimit+label + code-enforced origin allowlist

---

## Convergence & budgets

### Stop criterion
| Option | Description | Selected |
|--------|-------------|----------|
| Saturation OR any budget cap, whichever first | saturation → two-run convergence; budgets = hard backstop | ✓ |
| Budget caps only | always burns full budget; weaker convergence | |

**User's choice:** Saturation OR budget cap

### Budget layering
| Option | Description | Selected |
|--------|-------------|----------|
| Explorer caps (steps/depth/revisits/wall-clock) + gateway owns token/USD | no duplicate ledgers; run_id binds per-run token budget | ✓ |
| Explorer re-implements token/cost budget too | duplicates gateway; drift risk | |

**User's choice:** Explorer exploration caps + gateway owns token/USD

---

## Live progress UX

### Progress flow
| Option | Description | Selected |
|--------|-------------|----------|
| Explorer → Redis pub/sub → SSE → EventSource | real-time; same seam Phase-7 workers publish into | ✓ |
| Poll GET /executions/{run_id} | simplest; not real-time, no per-step feed | |

**User's choice:** Redis pub/sub → SSE (sse-starlette)

### Live view content
| Option | Description | Selected |
|--------|-------------|----------|
| Counters + live action feed + current page/screenshot | matches EXPL-01 + feels live | ✓ |
| Counters + status only | lighter; less insight | |

**User's choice:** Counters + action feed + current page/screenshot thumbnail

---

## Claude's Discretion / for research

- Fingerprint normalization algorithm (THE experimental unknown — EXPL-06)
- LangGraph raw StateGraph node structure + langgraph-checkpoint-postgres wiring
- Element locator-chain extraction + history (EXPL-09)
- Auth: login-form detection, storageState reuse, logout recovery (EXPL-02)
- Screenshot storage under workspaces/<run_id>/ (MinIO is Phase 7)
- Multi-step workflow + form-validation detection (EXPL-04)

## Deferred Ideas

- Real single-writer KG + idempotent MERGE + freshness + flow mining + risk scores → Phase 5
- Vision/multimodal perception → deferred (evidence-only screenshots this phase)
- MinIO artifact store → Phase 7
- RabbitMQ distributed/parallel exploration → Phase 7
- Per-operation-type LLM budgets → still deferred
