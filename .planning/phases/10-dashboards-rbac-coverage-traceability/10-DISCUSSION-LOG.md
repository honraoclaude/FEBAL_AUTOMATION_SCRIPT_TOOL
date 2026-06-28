# Phase 10: Dashboards, RBAC & Coverage/Traceability - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-28
**Phase:** 10-dashboards-rbac-coverage-traceability
**Areas discussed:** RBAC model & enforcement, Coverage definition (DASH-04), Traceability architecture (DASH-05), Elasticsearch search (DASH-06)

---

## RBAC model & enforcement (PLAT-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Role enum on User + require_role DI + view gating | role enum column; ADMIN_EMAIL seed=Admin; admin role-assign API; JWT role claim; require_role(*roles) Depends; frontend gates off /me; static role→permission map | ✓ |
| Separate permissions table | roles+permissions+join tables (granular grants); heavier for 4 fixed roles + single operator | |

**User's choice:** Role enum on User + require_role DI + view gating
**Notes:** Simplest thing for 4 fixed roles + one operator; matches the existing get_current_user seam; CLAUDE.md says no extra library needed for 4 static roles.

---

## Coverage definition (DASH-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Flow covered = approved scenario AND passing execution | graph-derived covered/discovered %; definition shown in UI; Phase-5 ground-truth stays separate | ✓ |
| Scenario-only coverage | covered = has approved scenario (ignores pass/fail); overstates; contradicts "passing executions" | |

**User's choice:** Flow covered = approved scenario AND passing execution
**Notes:** Honest definition (a flow with an approved-but-failing test is NOT covered); displayed in the UI; distinct from the Phase-5 ground-truth exploration-completeness number.

---

## Traceability architecture (DASH-05)

| Option | Description | Selected |
|--------|-------------|----------|
| Cross-store join service (read-time) | assemble flow↔scenario↔script↔execution↔defect on read from Neo4j + Postgres (Phase-9 FK links) keyed by any artifact; no new graph writes | ✓ |
| Graph-native (write all into Neo4j) | write scenario/exec/defect nodes+edges; one Cypher traversal; couples relational data into the KG + write path per exec/defect | |

**User's choice:** Cross-store join service (read-time)
**Notes:** Keeps the KG as discovered-structure only (single-writer discipline preserved); the Phase-9 FK links make the join cheap; keyless + fixture-testable.

---

## Elasticsearch search (DASH-06)

| Option | Description | Selected |
|--------|-------------|----------|
| On-write dual-index + a backfill reindexer | index executions/failures/logs on write + a backfill command; ES client gated dep; graceful-degrade when ES down | ✓ |
| Batch/periodic reindex only | periodic job reindexes; no on-write; results lag until next batch | |

**User's choice:** On-write dual-index + a backfill reindexer
**Notes:** Fresh search right after a run; backfill seeds existing data; graceful-degrade exactly like neo4j (honest "search unavailable"); elasticsearch 9.4 is a gated new dep (client major must match ES server 9.x).

---

## Claude's Discretion

- The dashboard aggregation queries (Exec/QA/Dev), computed on-read (TanStack Query) unless research shows a materialization need; root-cause groupings = Phase-9 classification+fingerprint; module breakdown = by flow/page.
- The require_role endpoint→role matrix across existing routers; admin role-assign API + minimal admin UI vs API-only.
- The ES index mappings + on-write hook points + backfill command + search ranking/highlighting.
- The traceability response shape + viewer interaction.
- Migration 0010 (role column at least).
- The UI-SPEC: 3 role-scoped dashboards + coverage panel (honest definition) + traceability viewer + search UI + role-gated nav; recharts (installed), zero new frontend deps preferred.

## Deferred Ideas

- K8s + CI/CD + Prometheus/Grafana ops stack → Phase 11.
- Granular permissions table / custom roles → rejected for v1.
- Graph-native traceability → rejected for v1.
- Bi-directional Jira status sync → out of v1.
- Real-time dashboard push (SSE/websocket tiles) → not required (polling suffices).
