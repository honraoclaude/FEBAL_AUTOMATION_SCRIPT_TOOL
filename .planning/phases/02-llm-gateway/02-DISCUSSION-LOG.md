# Phase 2: LLM Gateway - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-13
**Phase:** 2-LLM Gateway
**Areas discussed:** Budget enforcement, Kill-switch, Cost accounting & storage, Cache policy & model selection

---

## Budget Enforcement Behavior

### Breach action
| Option | Description | Selected |
|--------|-------------|----------|
| Hard abort — raise exception | Gateway raises BudgetExceeded; operation fails fast after the breach | |
| Refusal result, no exception | Returns structured 'denied' result; caller must check | |
| Pre-check only (block before spend) | Budget checked BEFORE the call; would-be-breaching call never runs | ✓ |

**User's choice:** Pre-check only (block before spend)
**Notes:** Strongest guarantee — never overspends even by one call. Captured implication: pre-check reserves estimated input + max-output tokens against remaining budget, reconciles to actual after the response.

### Budget basis
| Option | Description | Selected |
|--------|-------------|----------|
| Both cost ($) and tokens | Track tokens AND derived USD; limit on either axis | ✓ |
| Cost ($) only | Single USD axis | |
| Tokens only | Provider-neutral, no pricing needed for enforcement | |

**User's choice:** Both cost ($) and tokens

### Budget config location
| Option | Description | Selected |
|--------|-------------|----------|
| Global env defaults + per-run override | Env caps for all scopes; run can tighten | ✓ |
| Global env only | One set of limits platform-wide | |
| Per-operation type | Distinct budgets per operation kind | |

**User's choice:** Global env defaults + per-run override
**Notes:** Ties to existing Target.budget_overrides (Phase 1) feeding per-run budgets in Phase 4.

---

## Kill-Switch Mechanism & Scope

### Trip mechanism
| Option | Description | Selected |
|--------|-------------|----------|
| Both manual + auto | Admin API panic button AND auto-trip on daily-budget exhaustion | ✓ |
| Manual only | Human admin only | |
| Auto only | Budget exhaustion only, no panic button | |

**User's choice:** Both manual + auto

### Scope
| Option | Description | Selected |
|--------|-------------|----------|
| Global — halt ALL LLM traffic | Every call across every run refused while active | ✓ |
| Per-run kill | Kill a specific run by id | |

**User's choice:** Global — halt ALL LLM traffic
**Notes:** Per-run kill noted as deferred (Phase 4/7 run-control).

### State location
| Option | Description | Selected |
|--------|-------------|----------|
| Redis | Kill flag + rolling counters; shared, atomic, restart-surviving | ✓ |
| Postgres | Durable but hot-path latency/contention | |

**User's choice:** Redis (Postgres reserved for the durable cost ledger)

---

## Cost Accounting & Storage

### Pricing source
| Option | Description | Selected |
|--------|-------------|----------|
| Versioned pricing table in config | model→{input$,output$} with effective-date | ✓ |
| Env-var prices | Prices via environment | |
| Hardcoded constants | Prices inline in code | |

**User's choice:** Versioned pricing table in config
**Notes:** Effective-dating keeps historical cost rows accurate across price changes.

### Persistence
| Option | Description | Selected |
|--------|-------------|----------|
| Postgres ledger table + structured logs | Durable SQL table now + JSON logs for ES later | ✓ |
| Postgres ledger table only | Just SQL | |
| Structured logs only | JSON events, no table | |

**User's choice:** Postgres ledger table + structured logs

### Tagging / run identity
| Option | Description | Selected |
|--------|-------------|----------|
| Caller passes operation_type + run_id | Per-run budget binds to run_id; reports group by operation_type | ✓ |
| operation_type only | No run key for per-run budgets | |
| Auto-infer from call site | Brittle/magic | |

**User's choice:** Caller passes operation_type + run_id (gateway generates run_id if absent)

---

## Cache Policy & Model Selection

### Cache key
| Option | Description | Selected |
|--------|-------------|----------|
| Hash of messages + model + params | Exact match incl. temperature/max_tokens/tools | ✓ |
| Hash of prompt text + model only | Ignores params — risk of stale hits | |

**User's choice:** Hash of messages + model + params

### Cache policy
| Option | Description | Selected |
|--------|-------------|----------|
| Cache deterministic only (temp=0), TTL configurable | Skip non-deterministic; ~24h default TTL; per-call no_cache opt-out | ✓ |
| Cache everything, TTL configurable | All calls regardless of temperature | |
| Per-call opt-in only | No caching unless asked | |

**User's choice:** Cache deterministic only (temp=0), TTL configurable

### Model selection
| Option | Description | Selected |
|--------|-------------|----------|
| Default model + per-operation override | Global default env, per-call model string to init_chat_model | ✓ |
| Single global model | One model everywhere | |

**User's choice:** Default model + per-operation override

---

## Claude's Discretion

- Gateway interface/function signature and module location (likely `app/services/llm_gateway.py`)
- Token-estimation method for the pre-check (provider tokenizer vs heuristic)
- `tenacity` retry/backoff specifics for 429/529
- Whether LangSmith tracing is wired now (env opt-in) or deferred

## Deferred Ideas

- Per-run kill / "stop this exploration" control → Phase 4/7 run-control
- Per-operation-type budget config → deferred until those operations exist (operation_type tagging lays groundwork)
- Elasticsearch cost/usage search → Phase 9/10 (logs emitted now)
- Prometheus cost gauges / Grafana dashboards → Phase 11
