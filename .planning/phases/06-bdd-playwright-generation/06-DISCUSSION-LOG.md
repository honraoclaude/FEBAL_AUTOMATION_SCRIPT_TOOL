# Phase 6: BDD & Playwright Generation - Discussion Log

> **Audit trail only.** Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-20
**Phase:** 6-BDD & Playwright Generation
**Areas discussed:** Review queue model + UX, Quality gates (lint + no-vacuous), Locator sourcing + codegen, Stability + seeded-bug acceptance

---

## Review queue (GEN-02)

### Storage + status
| Option | Description | Selected |
|--------|-------------|----------|
| Postgres scenarios table with status lifecycle | rows linked to flow/run, draft→approved/rejected; codegen reads only approved | ✓ |
| Files in workspace + sidecar status | fragile to query/gate | |

**User's choice:** Postgres scenarios table

### Edit mode
| Option | Description | Selected |
|--------|-------------|----------|
| Edit-in-place, re-validated on save | edit Gherkin + approve; save re-runs gates | ✓ |
| Approve/reject only | loses the "edit" half of GEN-02 | |

**User's choice:** Edit-in-place re-validated on save

---

## Quality gates (GEN-03)

### No-vacuous-assertion mechanism
| Option | Description | Selected |
|--------|-------------|----------|
| Structured: each Then carries a KG reference, gate checks it resolves | deterministic vs Neo4j; vacuous Then rejected | ✓ |
| Heuristic text match against KG names | brittle | |
| LLM self-check | non-deterministic soft gate | |

**User's choice:** Structured Then→KG-reference resolution

### Enforcement point
| Option | Description | Selected |
|--------|-------------|----------|
| Block at generation AND on edit/approve | gherkin 29.x lint + assertion gate at both points | ✓ |
| Block at generation only | edit path could introduce vacuous/malformed | |

**User's choice:** Both generation and edit/approve

---

## Locator sourcing + codegen (GEN-04/05)

### Locator source + enforcement
| Option | Description | Selected |
|--------|-------------|----------|
| Page objects injected with repo locators + static freehand-selector gate | LLM fills non-locator slots; gate rejects raw selectors | ✓ |
| Prompt the LLM (trust, no gate) | unverifiable — the exact GEN-05 failure | |

**User's choice:** Repo-injected locators + static gate

### Codegen layout
| Option | Description | Selected |
|--------|-------------|----------|
| Full pages/specs/fixtures/utils/data/reports tree, target-scoped under workspaces/ | GEN-04 structure; outlines+Examples from KG/form data | ✓ |
| Flat specs only (inline locators) | violates GEN-04 | |

**User's choice:** Full project tree under workspaces/

---

## Stability + seeded-bug acceptance (GEN-05, trust gate)

### Stability check
| Option | Description | Selected |
|--------|-------------|----------|
| N consecutive subprocess runs, all-green, N env-default 3 | reuse Phase-3 runner; flaky rejected; harness deterministic on a planted spec | ✓ |
| Single run | drops the N-run requirement | |

**User's choice:** N consecutive runs (default 3)

### Seeded-bug build
| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated seeded-bug SauceDemo build (variant/profile + injected defect) | literal "seeded-bug build of the target"; tests must FAIL against it | ✓ |
| SauceDemo built-in problem_user | zero infra but couples to app specifics | |

**User's choice:** Dedicated seeded-bug build

---

## Claude's Discretion / for research

- The structured Then→KG-reference schema (emit + resolve + gate check) — the novel gate
- Examples-table data derivation from the KG (BusinessEntity, form fields, validation rules)
- Page-object templates + naming; approved scenario → spec mapping; pytest-bdd step-defs vs plain pytest-playwright (reconcile with Phase-3 choice + the pytest-bdd dep)
- Seeded-bug build mechanism + N-run/bug-build harness wiring; the seeded defect specifics
- Regenerate-vs-approved reconciliation (minimal this phase)

## Deferred Ideas

- Execution engine (suite tiers, RabbitMQ, artifacts, live view) → Phase 7 (reuse Phase-3 subprocess runner for stability only)
- Healing of generated tests → Phase 8
- Deep regenerate/approved reconciliation → minimal (stale-mark at most) this phase
- Scenario↔flow↔element graph visualization → out of scope
- LLM-based scenario quality/risk scoring → rejected (deterministic gates)
