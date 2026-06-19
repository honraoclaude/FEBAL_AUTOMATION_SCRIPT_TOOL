---
phase: 05
plan: 01
subsystem: knowledge-graph
tags: [neo4j, kg-writer, idempotent-merge, freshness, single-write-path, refactor]
requires:
  - explorer/nodes.py persist node (Phase 4)
  - explorer/fingerprint.py structural fingerprint (Phase 4, the MERGE key)
  - core/neo4j_driver.py lifespan singleton (Phase 3)
provides:
  - app/services/kg/writer.py (THE single Neo4j write path: upsert_*/link_*)
  - app/services/kg/schema.py (label/edge constants + uniqueness constraints + VERB_ENTITY_MAP)
  - idempotent fingerprint-MERGE + first_seen/last_verified freshness
  - lifespan-created uniqueness constraints (graceful when neo4j down)
affects:
  - explorer/nodes.py (persist node now a thin delegate, zero Cypher)
  - main.py lifespan (ensure_constraints wired)
tech-stack:
  added: []
  patterns:
    - single-write-path (grep-enforced via Cypher-syntax-scoped scan)
    - constraint-backed idempotent MERGE (ON CREATE/ON MATCH freshness split)
    - graceful constraint setup at lifespan startup (no-raise when neo4j unreachable)
    - deterministic verb->BusinessEntity map (no LLM)
key-files:
  created:
    - apps/api/app/services/kg/__init__.py
    - apps/api/app/services/kg/schema.py
    - apps/api/app/services/kg/writer.py
    - apps/api/tests/fixtures/kg/pages.json
    - apps/api/tests/unit/test_single_write_path.py
    - apps/api/tests/functional/test_kg_idempotency.py
    - apps/api/tests/functional/test_kg_schema.py
  modified:
    - apps/api/app/services/explorer/nodes.py
    - apps/api/app/main.py
decisions:
  - "Grep gate scans CYPHER-SYNTAX tokens (MERGE (, CREATE (, SET x.|=, DETACH DELETE, REMOVE x.) not bare keywords — English prose in docstrings (\"Neo4j MERGE key\", \"SET the kill-switch\") no longer false-positives"
  - "writer.py functions take an optional driver kwarg (defaults to get_neo4j() singleton) so graph tests inject a short-lived host driver while production reuses the one pool"
  - "ensure_constraints catches ALL exceptions and returns False (graceful boot) — api boots when neo4j is down; constraints created on next reachable boot or before first write"
  - "Target page (b) is upserted with fingerprint=URL-stand-in until that page is itself perceived+fingerprinted — preserves the Phase-4 documented seam"
  - "KG-05 marked NOT complete this slice — single-write-path half delivered; the element-repository queryable half is 05-02"
metrics:
  duration: ~12min
  completed: 2026-06-19
---

# Phase 5 Plan 01: Knowledge-Graph Single Write Path Summary

Lifted the explorer's inline persist Cypher into `app/services/kg/writer.py` as the sole Neo4j write path (KG-05), re-keyed the Page MERGE on the Phase-4 structural fingerprint, added `first_seen`/`last_verified` freshness backed by lifespan-created uniqueness constraints (KG-03), and refactored `explorer/nodes.py` into a zero-Cypher delegate — a grep gate enforces the single write path and a deterministic re-run proves ~0 duplicates.

## What Was Built

- **`kg/schema.py`** — one source of truth for canonical labels (`Page/Button/Form/Workflow/Element/BusinessEntity`) and edge types (`NavigatesTo/Submits/Creates/Updates/Deletes/HAS_ELEMENT/HAS_FORM/HAS_BUTTON/STEP`); five `REQUIRE ... IS UNIQUE` constraints (Page.fingerprint primary); a deterministic `VERB_ENTITY_MAP` + `map_verb_to_entity()`; and `ensure_constraints(driver)` that is graceful (logs-and-returns, never raises) when neo4j is unreachable.
- **`kg/writer.py`** — THE single write path: `upsert_page/upsert_element/upsert_button/upsert_form/upsert_workflow/upsert_business_entity` + `link_navigates_to/link_has_element/link_has_button/link_has_form/link_submits/link_creates/link_updates/link_deletes/link_step`. Page MERGEs on `$fingerprint`; `ON CREATE SET first_seen=$now` / `ON MATCH SET last_verified=$now` + a `coalesce` so a freshly-created node is fresh too; `first_seen` never touched on match. Every function uses the lifted managed `execute_write` + `RETURN count(*) AS n` read-back guard (0-count raises) and parameterized Cypher (edge types are schema code constants).
- **`explorer/nodes.py`** — `persist_to_neo4j` now computes the same params it always did and DELEGATES to `kg_writer.*`; `_build_persist_cypher`/`_write_workflow_step`/`_write_form_validation` and the `get_neo4j` import were removed. Holds zero `MERGE/CREATE/SET/DELETE` Cypher.
- **`main.py`** — lifespan calls `await ensure_constraints(get_neo4j())` after `init_neo4j()`; verified the api boots healthy with `kg_constraints_ensured count=5` against a live neo4j and (by design) would boot when neo4j is down.
- **Tests** — `test_single_write_path.py` (grep gate, default suite), `test_kg_idempotency.py` + `test_kg_schema.py` (graph-marked, no live_llm), and the `fixtures/kg/pages.json` snapshot.

## Verification Results

- `tests/unit/test_single_write_path.py` — GREEN (2 passed): zero write-Cypher outside `kg/writer.py`+`kg/schema.py`.
- `tests/functional/test_kg_idempotency.py` + `test_kg_schema.py` under graph_mode — GREEN (4 passed): re-run counts unchanged, `first_seen` immutable (frozen at now1), all `last_verified == now2`, duplicate-fingerprint CREATE raises `ConstraintError`; canonical labels + edges (`NavigatesTo/HAS_ELEMENT/HAS_BUTTON/HAS_FORM/Submits/Creates`) present.
- Default gate `uv run pytest -m "not live_llm and not e2e and not graph"` — GREEN (194 passed, 23 deselected): no explorer regression.
- API restart — boots healthy (`/health` 200), constraints created at startup.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Grep gate scoped to Cypher syntax to eliminate prose false-positives**
- **Found during:** Task 0
- **Issue:** The plan's bare-keyword scan (`MERGE`, `SET `) plus full-line-comment stripping still matched English prose in docstrings (`llm_gateway.py` "SET the kill-switch flag", `fingerprint.py` "Neo4j MERGE key"), which would make the gate fail forever regardless of real write-Cypher placement.
- **Fix:** Scoped the patterns to Cypher syntax — `MERGE (`, `CREATE (`, `SET \w+[.=]`, `DETACH DELETE`, `REMOVE \w+.` — so only genuine write statements match. After Task 2 only `explorer/nodes.py` (then cleaned) tripped it; now zero offenders.
- **Files modified:** apps/api/tests/unit/test_single_write_path.py
- **Commit:** 10f5dd2

## Known Stubs

None. The writer is fully wired; the explorer delegate is live. The element-repository READ surface (KG-05 second half) and flow mining/risk/coverage/read-API/UI are deliberately scoped to slices 02-04.

## Requirements

- **KG-01** — complete (write half: canonical Page/Button/Form/Workflow/Element/BusinessEntity nodes + NavigatesTo/Submits/Creates/Updates/Deletes/HAS_* edges writable; schema graph test green). Browse (KG-02) is slice 03.
- **KG-03** — complete (idempotent fingerprint-MERGE ~0 duplicates, first_seen/last_verified freshness, uniqueness constraints).
- **KG-05** — NOT complete this slice. Single-write-path half delivered + grep-enforced; the "element fingerprints + locator history queryable per element" half is 05-02.

## Live Migration Note

The MERGE key changed `key` -> `fingerprint`. The deterministic proofs run on a fresh graph (the graph tests `DETACH DELETE` in setup). Any pre-existing live Phase-4 graph must be cleared (`MATCH (n) DETACH DELETE n`) before the first Phase-5 live exploration, since the old nodes are keyed on `key` not `fingerprint`. No automated data migration is required (documented per RESEARCH Runtime State Inventory).

## Self-Check: PASSED

- apps/api/app/services/kg/writer.py — FOUND
- apps/api/app/services/kg/schema.py — FOUND
- apps/api/app/services/kg/__init__.py — FOUND
- apps/api/tests/unit/test_single_write_path.py — FOUND
- apps/api/tests/functional/test_kg_idempotency.py — FOUND
- apps/api/tests/functional/test_kg_schema.py — FOUND
- apps/api/tests/fixtures/kg/pages.json — FOUND
- commit 10f5dd2 (test scaffold) — FOUND
- commit 3b5e1ef (writer + schema) — FOUND
- commit 327b205 (explorer delegate + lifespan) — FOUND
