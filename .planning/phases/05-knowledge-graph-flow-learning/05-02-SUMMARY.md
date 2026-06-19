---
phase: 05
plan: 02
subsystem: knowledge-graph
tags: [neo4j, flow-mining, risk-score, llm-categorize, element-repository, read-only, pure-fn]
requires:
  - kg/writer.py upsert_*/link_* single write path (05-01)
  - kg/schema.py labels/edges + VERB_ENTITY_MAP (05-01)
  - explorer/risk.py is_destructive deny-list (Phase 4)
  - llm_gateway.complete + BudgetExceeded/KillSwitchActive (02-01)
  - explorer/locators.py chain_json/history_json seam (Phase 4)
provides:
  - app/services/kg/risk.py (PURE clamped 0-100 risk_score + frozen RiskWeights + risk_tier)
  - app/services/kg/flows.py (bounded mine_flows + extract_signals + categorize_flow + build_flows)
  - app/services/kg/reader.py (read-only Cypher: pages, element repository, flows_source, summary)
  - deterministic no-key flow names so flows + risk render WITHOUT provider keys
affects:
  - none (new read/derive layer; explorer/writer untouched)
tech-stack:
  added: []
  patterns:
    - pure-tunable-frozen-weights risk formula (D-04, no LLM)
    - bounded simple-path mining (MAX_PATH_LENGTH + dedup-by-node-set + MAX_FLOWS cap)
    - gateway-only LLM categorization with untrusted-fence + deterministic no-key fallback
    - read-only execute_read with a LIMIT DoS guard on every query (no write-Cypher)
    - in-Python path bound (no variable-length Cypher -> A4 path-range caveat moot)
key-files:
  created:
    - apps/api/app/services/kg/risk.py
    - apps/api/app/services/kg/flows.py
    - apps/api/app/services/kg/reader.py
    - apps/api/tests/unit/test_kg_risk.py
    - apps/api/tests/unit/test_flow_mining.py
    - apps/api/tests/unit/test_flow_categorize.py
    - apps/api/tests/functional/test_element_repo.py
  modified: []
decisions:
  - "The new KG risk test lives at tests/unit/test_kg_risk.py (NOT test_risk.py — that name is already the explorer ACTION deny-list/origin test; RESEARCH:568 calls kg/risk 'distinct from explorer/risk'). Avoids clobbering an existing passing suite."
  - "Entry pages = nodes with no inbound NavigatesTo OR Submits (both are traversal edges mining walks) — a page reached only via Submits is NOT an entry, matching the journey intent."
  - "categorize_flow catches BudgetExceeded/KillSwitchActive AND a broad Exception: with empty keys the gateway raises a provider AUTH TypeError, not BudgetExceeded; categorization is a semantic nicety so ANY gateway failure degrades to the deterministic name (headline no-key guarantee)."
  - "flows_source reads nodes+edges and mining runs in Python (no *1..N variable-length Cypher), so RESEARCH A4's parameterized-path-range caveat never applies — the bound is a Python code constant."
  - "auth_gated is a deterministic graph-derived proxy (page has an inbound NavigatesTo) — no LLM, no creds; good enough for the risk signal."
metrics:
  duration: ~15min
  completed: 2026-06-19
---

# Phase 5 Plan 02: KG Read + Derive Layer (Flow Mining, Risk, Categorization, Element Repository) Summary

Built the read + derive layer over the Slice-1 graph: a PURE deterministic 0-100 risk formula (`kg/risk.py`), bounded deterministic flow path-mining + signal extraction + gateway-routed LLM categorization with a deterministic no-key fallback (`kg/flows.py`), and read-only Cypher including the per-element Element Repository (`kg/reader.py`). All deterministic logic is unit-tested without provider keys; the Element Repository is proven under graph_mode. No write-Cypher leaked outside `kg/writer.py` (single-write-path grep still green).

## What Was Built

- **`kg/risk.py`** — a `@dataclass(frozen=True) RiskWeights` (destructive_action=40, per_state_change=8, auth_gated_step=6, per_form=5, depth=3 — RESEARCH A1 tunable starting points) + `DEFAULT_WEIGHTS`; a PURE `risk_score(signals, w=DEFAULT_WEIGHTS) -> int` clamped to 0-100 (binary destructive term + per-edge/step/form/length terms); `risk_tier(score)` returning high(>=67)/medium(>=34)/low. Stdlib-only (dataclasses) — imports NO neo4j/llm_gateway/SessionLocal (asserted by test).
- **`kg/flows.py`** — `MAX_PATH_LENGTH=8`, `MAX_FLOWS=200`; `mine_flows(graph)` a pure bounded simple-path enumeration over an in-memory adjacency (seeds from entry pages, rejects repeated nodes, dedups by frozenset of node fingerprints, caps at MAX_FLOWS with a `bounded` flag); `extract_signals(path, graph)` producing the dict `risk_score` consumes (reuses `explorer.risk.is_destructive` for `has_destructive`); `categorize_flow(steps, run_id, start, end)` routing through `llm_gateway.complete(operation_type="flow.categorize")` with an UNTRUSTED-fenced data-only prompt, a fresh `SessionLocal`, and a deterministic `"Flow: {start} → {end}"` fallback; `build_flows` composing mine→signals→score→categorize; `mine_flows_from_neo4j` deferring to the reader.
- **`kg/reader.py`** — `list_pages`, `page_detail`, `element_repository`, `element_detail`, `graph_summary`, `flows_source` — all `execute_read` + a `LIMIT` DoS guard (V5/T-05-07), parameterized, zero write-Cypher. `element_repository`/`element_detail` deserialize `chain_json`/`history_json` into structured locator chain + history per element (KG-05). `flows_source` shapes the in-memory graph the pure miner consumes.
- **Tests** — `test_kg_risk.py` (15 cases: clamp at 0/100, 33/34 + 66/67 tier boundaries, swappable weights, no-stack purity, frozen weights); `test_flow_mining.py` (entry-seeding, dedup-by-node-set, MAX_PATH_LENGTH, MAX_FLOWS bounded flag, simple-paths-only, signal shape); `test_flow_categorize.py` (gateway op_type+run_id, untrusted fence, 3 fallback paths incl. the no-key provider error); `test_element_repo.py` (graph: chain + history per element, element_detail, list_pages, summary).

## Verification Results

- `tests/unit/test_kg_risk.py` — GREEN (15 passed): pure formula, clamps, tiers, swappable frozen weights, no-stack purity.
- `tests/unit/test_flow_mining.py` + `tests/unit/test_flow_categorize.py` — GREEN (10 passed): bounded mining + categorization fallbacks.
- `tests/functional/test_element_repo.py` under graph_mode — GREEN (3 passed): seeded element's chain + history returned per element; element_detail + list_pages + graph_summary correct.
- `tests/functional/test_kg_idempotency.py` + `test_kg_schema.py` under graph_mode — GREEN (4 passed): no Slice-1 regression.
- `tests/unit/test_single_write_path.py` — GREEN (2 passed): reader + flows added ZERO write-Cypher.
- Full default gate `-m "not live_llm and not e2e and not graph"` — GREEN (220 passed, 26 deselected; was 194 in 05-01, +26 new).
- Integration smoke (temporary, then removed): `flows_source` → `mine_flows` → `build_flows` over the fixture graph against the live neo4j produced 4 flows with deterministic names + risk scores with NO keys — this smoke is what surfaced the no-key provider-error bug below.
- graph_mode restored: web up, neo4j stopped (Pitfall 5).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] New KG risk test relocated to tests/unit/test_kg_risk.py**
- **Found during:** Task 1
- **Issue:** The plan's `files_modified` named `apps/api/tests/unit/test_risk.py`, but that file already exists as the Phase-4 explorer ACTION deny-list/origin test (a passing suite). Writing the new KG risk test there would clobber it.
- **Fix:** Created the new KG-04 risk test at `tests/unit/test_kg_risk.py` instead (RESEARCH:568 explicitly calls kg/risk "distinct from explorer/risk"). The explorer `test_risk.py` is untouched.
- **Files modified:** apps/api/tests/unit/test_kg_risk.py (new)
- **Commit:** 62a32c3

**2. [Rule 1 - Bug] categorize_flow now falls back on the no-key provider auth error**
- **Found during:** Task 3 (build_flows integration smoke)
- **Issue:** The plan/RESEARCH specified the fallback on `BudgetExceeded`/`KillSwitchActive`. The smoke against the live graph revealed that with EMPTY provider keys the gateway's `init_chat_model` raises a provider AUTH `TypeError` (not a budget/kill error), so `categorize_flow` propagated it and broke `build_flows` — defeating the headline guarantee that flows + risk render WITHOUT keys.
- **Fix:** Added a broad `except Exception` after the budget/kill catch that logs and returns the deterministic `"Flow: {start} → {end}"` name. Categorization is a semantic nicety, not a correctness requirement, so ANY gateway failure degrades gracefully. Added a regression test (`test_no_key_provider_error_returns_deterministic_fallback`).
- **Files modified:** apps/api/app/services/kg/flows.py, apps/api/tests/unit/test_flow_categorize.py
- **Commit:** a2dc16c

**3. [Rule 1 - Design] Entry-page seed includes "no inbound Submits" too**
- **Found during:** Task 2
- **Issue:** Seeding entries on "no inbound NavigatesTo" alone treated a page reachable only via a `Submits` edge (e.g. a checkout result) as an entry, fragmenting journeys.
- **Fix:** Entry = no inbound NavigatesTo OR Submits (both are traversal edges mining walks). Matches the journey intent and the linear-graph test expectation.
- **Files modified:** apps/api/app/services/kg/flows.py
- **Commit:** ea81a5d

## Known Stubs

None. The risk formula, miner, signal extraction, categorization (with no-key fallback), and the Element Repository read are all fully wired and tested. The READ API + browse UI (Slice 3) and the coverage metric/QUAL-01 (Slice 4) are deliberately out of scope for this slice. Live (keyed) semantic flow naming is the documented Manual-Only half (deterministic names cover the no-key path).

## Requirements

- **KG-04** — complete. Bounded deterministic path-mining derives journeys (MAX_PATH_LENGTH + dedup-by-node-set + MAX_FLOWS cap with bounded flag); a PURE deterministic 0-100 risk score is assigned per flow (frozen tunable weights, no LLM); the LLM only NAMES flows via the budgeted gateway (flow.categorize) with a deterministic fallback that works without keys. (User-visible rendering = the Slice-3 read API/UI.)
- **KG-05** — complete (element half; the single-write-path half landed in 05-01). Element fingerprints + locator chain + history are queryable per element via `reader.element_repository`/`element_detail`; the single-write-path grep gate is still green (reader/flows add no write-Cypher).

## Threat Surface

No new network endpoints, auth paths, or schema changes at trust boundaries beyond the plan's threat register. T-05-05 (untrusted-step fencing), T-05-06 (budgeted gateway + temp=0/max_tokens=128 + no-key fallback), T-05-07 (MAX_PATH_LENGTH/simple-paths/dedup/MAX_FLOWS + LIMIT on every read), T-05-08 (parameterized read Cypher; path bound is a Python code constant) all mitigated as planned.

## Self-Check: PASSED

- apps/api/app/services/kg/risk.py — FOUND
- apps/api/app/services/kg/flows.py — FOUND
- apps/api/app/services/kg/reader.py — FOUND
- apps/api/tests/unit/test_kg_risk.py — FOUND
- apps/api/tests/unit/test_flow_mining.py — FOUND
- apps/api/tests/unit/test_flow_categorize.py — FOUND
- apps/api/tests/functional/test_element_repo.py — FOUND
- commit 62a32c3 (RED kg risk) — FOUND
- commit 914a318 (kg risk impl) — FOUND
- commit 24e1b25 (RED flows) — FOUND
- commit ea81a5d (flows impl) — FOUND
- commit a2dc16c (no-key fallback fix) — FOUND
- commit 4c4e313 (reader + element-repo test) — FOUND
