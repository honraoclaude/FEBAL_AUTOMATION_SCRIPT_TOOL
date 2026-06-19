---
phase: 05
plan: 04
subsystem: knowledge-graph
tags: [coverage, ground-truth, qual-01, trust-gate, pure-metric, manual-only, no-keys, deployable-fixture]
requires:
  - kg/reader.py list_pages (fingerprint + url per discovered page) (05-02)
  - routers/kg.py + schemas/kg.py with the honest measured=false CoverageResponse shape (05-03)
  - explorer/budget.py purity discipline (no-I/O pure metric analog) (04)
  - tests/fixtures/kg/pages.json fixture-KG snapshot pattern (05-01)
provides:
  - app/services/kg/coverage.py (PURE matched/total metric — normalize_url + compute_coverage + load_ground_truth)
  - app/services/kg/ground_truth/saucedemo.json (DEPLOYABLE hand-labeled SauceDemo ground truth — 7 pages + 2 flows)
  - tests/fixtures/ground_truth/saucedemo.json (the diffable D-07 committed copy, byte-identical)
  - the REAL GET /coverage (computes coverage over the discovered graph; honest measured=false when empty)
  - tests/unit/test_coverage.py (deterministic known-% proof, no keys)
  - tests/functional/test_coverage_live.py (QUAL-01 live >=80% gate, Manual-Only, skips without keys)
affects:
  - app/routers/kg.py (GET /coverage body swapped from the honest stub to the real metric)
  - app/schemas/kg.py (CoverageResponse docstring reflects the real metric)
tech-stack:
  added: []
  patterns:
    - PURE coverage metric (no I/O in compute_coverage; only load_ground_truth reads the fixture) — stdlib json, NO YAML dep (D-07)
    - fingerprint-PRIMARY, normalized-URL FALLBACK page matching; normalize_url is path-only so cross-host URLs coincide (RESEARCH Pitfall 4 / Open Q2)
    - DEPLOYABLE in-package ground-truth copy (tests/ is .dockerignore'd) + a byte-identical diffable tests/fixtures copy, pinned in sync by a unit test
    - honest coverage (D-08 / T-05-14) — measured=false + zeros when no discovered graph; never a fabricated percent
    - live >=80% gate is [functional, graph, live_llm] Manual-Only (keys + a real exploration), same posture as Phase 4's live exploration
key-files:
  created:
    - apps/api/app/services/kg/coverage.py
    - apps/api/app/services/kg/ground_truth/saucedemo.json
    - apps/api/tests/fixtures/ground_truth/saucedemo.json
    - apps/api/tests/unit/test_coverage.py
    - apps/api/tests/functional/test_coverage_live.py
  modified:
    - apps/api/app/routers/kg.py
    - apps/api/app/schemas/kg.py
decisions:
  - "The runtime ground-truth fixture is DEPLOYED inside the app package (app/services/kg/ground_truth/saucedemo.json) because tests/ is .dockerignore'd and the api container has no source mount — the plan's tests/fixtures/ path alone is not deployable. A byte-identical diffable copy stays under tests/fixtures (D-07 'committed, diffable'); a unit test pins them in sync so the reviewed file can't drift from what the image serves."
  - "normalize_url is PATH-ONLY (strip scheme+host, drop query/fragment, collapse trailing slash) so http://saucedemo:80/cart.html (in-cluster) and https://www.saucedemo.com/cart.html (public, fixture) both reduce to /cart.html and match (Open Q2)."
  - "Flow coverage = a GT flow counts as covered only when EVERY page in its sequence matched (the journey is reachable on the discovered graph)."
  - "GET /coverage gathers the discovered side from kg/reader.list_pages (fingerprint + url) — no new reader query, read-only, no write-Cypher (single-write-path gate stays green)."
metrics:
  duration: ~30min
  completed: 2026-06-19
---

# Phase 5 Plan 04: Ground-Truth Coverage Metric + Real GET /coverage (QUAL-01) Summary

Shipped the QUAL-01 trust gate: a committed, hand-authored JSON ground-truth fixture of SauceDemo's 7 canonical pages + 2 key flows, a PURE deterministic coverage metric (matched ÷ total, fingerprint-primary / normalized-URL-path-only fallback) unit-tested to a KNOWN percentage with no provider key, the real `GET /coverage` wired over the discovered graph (honest `measured=false` when empty — never a fabricated percent), and the live ≥80% proof documented as a Manual-Only `[graph, live_llm]` test that skips without keys.

## What Was Built

- **`app/services/kg/coverage.py`** — the PURE metric: `normalize_url` (strip scheme+host → path-only canonical form), `compute_coverage(ground_truth, discovered)` (fingerprint-primary / normalized-URL-fallback matching, returns `screens_total/screens_covered/coverage_percent/flows_total/flows_covered/flows_percent/matched`, rounded 1dp, 0.0 when total is 0), and `load_ground_truth` (stdlib-`json`, NO YAML dep). `compute_coverage` does zero I/O — no neo4j, no LLM, no keys.
- **`app/services/kg/ground_truth/saucedemo.json`** — the DEPLOYABLE hand-labeled ground truth (7 pages: Login, Inventory, Item Detail, Cart, Checkout: Info/Overview/Complete; 2 flows: Login, Add to Cart & Checkout). Ships inside the api image.
- **`tests/fixtures/ground_truth/saucedemo.json`** — the diffable D-07 "committed, diffable" copy, byte-identical to the deployable one.
- **`routers/kg.py` (modified)** — `GET /coverage` now loads the ground truth, gathers discovered pages (fingerprint+url) via `kg/reader.list_pages`, and computes the real metric. Empty graph → `measured=false`, zeros, `coverage_percent=0.0` (the honest "not yet measured" shape). Pages exist → `measured=true` with the computed percentage. Read-only, auth-gated, no write-Cypher.
- **`schemas/kg.py` (modified)** — `CoverageResponse` docstring updated to reflect the real metric + the honesty flag (T-05-14). The response MODEL was already final in 05-03 (no field changes needed).
- **`tests/unit/test_coverage.py`** — the no-key deterministic proof: known % (6/7 → 85.7), fingerprint-primary match, cross-host URL-fallback match, empty-graph 0.0, flow coverage (full-journey counting), 100% case, and the ground-truth copies-in-sync pin.
- **`tests/functional/test_coverage_live.py`** — the QUAL-01 trust gate, `[functional, graph, live_llm]`, skipped without a provider key: a real SauceDemo exploration must yield `coverage_percent >= 80.0` via the live `GET /coverage`. Documented as Manual-Only (keys + a real exploration); the deterministic unit test is the no-key proof of the metric logic.

## Verification Results

- `tests/unit/test_coverage.py` — GREEN (9 passed): known-% (85.7), fp-primary, cross-host url-fallback, empty-graph 0.0, flow coverage, 100% case, normalize_url cases, copies-in-sync. No keys, no stack.
- `tests/unit/test_single_write_path.py` — GREEN (2 passed): the new coverage module + the router change add ZERO write-Cypher.
- `tests/functional/test_kg_endpoints.py -m graph` (under graph_mode, seeded 2-page graph) — GREEN (5 passed): `/coverage` now returns `measured=true` with the real computed percentage on a seeded graph; flows risk + sort; pages + graph summary; elements chain+history; stub-removed non-501.
- `tests/functional/test_kg_endpoints.py -m "not graph"` — GREEN (8 passed): 401 unauth on every KG endpoint (coverage import did not break the auth gate).
- `tests/functional/test_coverage_live.py` — SKIPPED (no provider key) — the Manual-Only QUAL-01 gate, as designed.
- `ruff check` on all changed files — clean.
- graph_mode restored: web up, neo4j stopped (Pitfall 5); default 5-service stack running.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The runtime ground-truth fixture was unreachable inside the api image**
- **Found during:** Task 2 (graph endpoint test — `GET /coverage` returned 500)
- **Issue:** The plan placed the ground-truth fixture only at `tests/fixtures/ground_truth/saucedemo.json`, and `coverage.py` defaulted to reading it there. But `apps/api/.dockerignore` excludes `tests/`, and the api container has no source mount for `apps/api` (only the web container mounts source) — so the file never existed in the image. The live handler raised `FileNotFoundError: /app/tests/fixtures/ground_truth/saucedemo.json`.
- **Fix:** Added a DEPLOYABLE copy inside the app package at `app/services/kg/ground_truth/saucedemo.json` (ships in the image), pointed `coverage.load_ground_truth` at it, kept the diffable `tests/fixtures` copy (D-07's "committed, diffable" intent), and added `test_ground_truth_copies_in_sync` to pin the two byte-identical so the reviewed file can't drift from what the image serves. Rebuilt the api image so the new package dir is present.
- **Files modified:** apps/api/app/services/kg/coverage.py, apps/api/app/services/kg/ground_truth/saucedemo.json, apps/api/tests/unit/test_coverage.py, apps/api/tests/fixtures/ground_truth/saucedemo.json
- **Commit:** 7e5880a

## Known Stubs

- None. `GET /coverage` now computes the real metric. The 05-03 honest `measured=false` placeholder is replaced; the honest empty-graph branch is the correct behavior (T-05-14), not a stub.

## Requirements

- **QUAL-01** — complete. A committed hand-labeled SauceDemo ground-truth fixture (7 pages + 2 flows) + a pure deterministic coverage metric (matched ÷ total, fp-primary / normalized-URL fallback) unit-tested to a known % with no keys; `GET /coverage` surfaces the real metric honestly (`measured=false`, never fabricated, when no graph); the live ≥80%-on-a-real-discovered-graph proof is the documented Manual-Only `test_coverage_live.py` (keys + a real exploration), same posture as Phase 4's live exploration. The metric + the gate are delivered; the live ≥80% number is the Manual-Only confirmation.

## Threat Surface

No new surface beyond the plan's threat register. T-05-13 (ground truth is a committed, diffable, version-controlled JSON file — now in TWO synced committed locations, both reviewable in git, no runtime/network-sourced ground truth), T-05-14 (honest `measured=false` when no graph; never a fabricated percent; the metric is pure + deterministically unit-tested to a known value), T-05-15 (the live ≥80% gate is an explicit Manual-Only test requiring keys + a real exploration; the metric logic is proven deterministically without keys so the claim is auditable), T-05-SC (no packages installed — JSON via stdlib) all mitigated as planned.

## Self-Check: PASSED

- apps/api/app/services/kg/coverage.py — FOUND
- apps/api/app/services/kg/ground_truth/saucedemo.json — FOUND
- apps/api/tests/fixtures/ground_truth/saucedemo.json — FOUND
- apps/api/tests/unit/test_coverage.py — FOUND
- apps/api/tests/functional/test_coverage_live.py — FOUND
- apps/api/app/routers/kg.py (real GET /coverage) — FOUND
- commit a01c2e0 (Task 1 — fixture + metric + unit test) — FOUND
- commit 7e5880a (Task 2 — real /coverage + Manual-Only live gate) — FOUND
