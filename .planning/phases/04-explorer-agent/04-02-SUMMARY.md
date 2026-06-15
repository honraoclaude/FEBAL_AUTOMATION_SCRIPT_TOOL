---
phase: 04-explorer-agent
plan: 02
subsystem: api
tags: [fingerprint, sha256, structural-skeleton, convergence, saturation, langgraph, playwright, storage-state, auth, explorer]

# Dependency graph
requires:
  - phase: 04-explorer-agent (04-01)
    provides: "explorer/ package — converge node with the # TEMP URL page_key, ExploreBudget (saturation_window), fake_gateway fixture, frontier contract"
  - phase: 01-foundation-dev-environment
    provides: "get_decrypted_credentials single decrypt surface; workspaces/<run_id>/ tree"
provides:
  - "Pure tunable structural_fingerprint(tree, cfg) + FingerprintConfig + the fingerprint(tree) seam (Candidate B SimHash upgrade path); sibling folding separates template from instance"
  - "page_fingerprint live-page adapter (DOM-walk evaluate) kept OUT of the pure hashing path; the converge/persist dedup key, replacing the Slice-1 URL page_key (EXPL-06)"
  - "run_over_fixtures convergence harness driving the REAL converge+fingerprint+budget over fixtures with a scripted gateway — the deterministic two-run convergence proof (EXPL-05)"
  - "auth.py: heuristic login detection + perform_login + storageState capture/reuse + needs_relogin + maybe_relogin node guard; creds confined to get_decrypted_credentials, cached per-run OUTSIDE state (EXPL-02)"
affects: [04-03-safety-locators-workflows, 04-04-sse-live-view, 05-knowledge-graph]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-hash / live-adapter split: structural_fingerprint is import-pure (AST-gated); page_fingerprint + _page_node_tree touch the page via a string evaluate so the hash stays browser-free and unit-testable on fixtures"
    - "fingerprint(tree)->str seam so Candidate B (SimHash) drops in behind one signature (converge, the proof, and the Neo4j MERGE key all call it)"
    - "Convergence harness over the REAL machinery: run_over_fixtures imports converge/fingerprint/budget (no reimplementation) so a regression in any breaks the two-run proof"
    - "Per-run credential cache OUTSIDE the checkpointed ExplorerState (H-1/T-04-07): decrypt once, reuse for mid-run relogin, never serialized/logged/on a node"

key-files:
  created:
    - apps/api/app/services/explorer/fingerprint.py
    - apps/api/app/services/explorer/convergence.py
    - apps/api/app/services/explorer/auth.py
    - apps/api/tests/unit/test_fingerprint.py
    - apps/api/tests/unit/test_convergence.py
    - apps/api/tests/unit/test_auth_detect.py
    - apps/api/tests/fixtures/aria/__init__.py
  modified:
    - apps/api/app/services/explorer/nodes.py
    - apps/api/app/services/explorer/state.py
    - apps/api/app/services/explorer/actions.py
    - apps/api/app/services/explorer/driver.py

key-decisions:
  - "The fingerprint hashing path is import-pure (AST-asserted): structural_fingerprint consumes a plain {role/tag/attrs/children} node tree; the live page->tree extraction (page_fingerprint, _page_node_tree) is a SEPARATE adapter that calls page.evaluate with a string DOM-walk so no playwright import enters the pure module"
  - "page_key is NO LONGER the state dedup key — it now scopes only to the frontier (URL identity), while fingerprint(...) is the converge/persist dedup key (EXPL-06)"
  - "The convergence proof is a thin run_over_fixtures harness (not the live StateGraph, which needs a live page in every node, H-1) that drives the REAL converge node + fingerprint + budget over fixtures with the fake gateway — same code paths, zero stack, zero spend"
  - "Mid-run relogin reuses creds cached on a per-run module dict (auth._RUN_CREDS) populated at first login and cleared in the driver finally — never a second decrypt, never on the serialized state"

patterns-established:
  - "Structural-skeleton SHA-256 with sibling-subtree folding ON as the template-vs-instance separator (EXPL-06 Candidate A); tunables max_depth/kept_attrs/fold_siblings/strip_text"
  - "Login heuristic: password input + nearest preceding text/email input + a submit control; SauceDemo ids as a fast path falling through to the generic heuristic"
  - "storageState persisted under workspaces/<run_id>/storage_state.json (gitignored, run_id-derived path, T-04-08) and reused via browser.new_context(storage_state=path)"

requirements-completed: [EXPL-06, EXPL-05, EXPL-02]

# Metrics
duration: 15min
completed: 2026-06-15
---

# Phase 4 Plan 02: Fingerprint Dedup + Convergence + Auth Summary

**A pure tunable structural-skeleton SHA-256 fingerprint (template-vs-instance via sibling folding) replaces the Slice-1 URL dedup key, a deterministic two-run harness proves convergence-to-saturation with zero spend, and heuristic auth adds login detection + storageState reuse + mid-run relogin with creds confined to the single decrypt surface.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-06-15T13:01:20Z
- **Completed:** 2026-06-15T13:16Z (approx)
- **Tasks:** 3 (all TDD: RED fixtures/tests → GREEN module → wiring)
- **Files created/modified:** 11

## Accomplishments
- `fingerprint.py`: a PURE, AST-gated `structural_fingerprint(tree, cfg)` + `FingerprintConfig` (max_depth/kept_attrs/fold_siblings/strip_text) + the `fingerprint(tree)` seam with a documented SimHash (Candidate B) upgrade path. Sibling-subtree folding makes a 6-item and a 4-item product list hash identically (template equality) while a different layout hashes differently. Swapped into the converge/persist nodes as the dedup key, retiring the Slice-1 `# TEMP` URL `page_key`.
- `convergence.py` + `test_convergence.py`: the headline EXPL-05 proof — two runs over fixed fixture snapshots with a scripted gateway collapse to an IDENTICAL fingerprint set and both stop with `stop_reason="saturation"`, with a non-saturating world halting on `max_steps`. The harness drives the REAL converge node + fingerprint + budget (imported, not reimplemented), so it is a genuine regression guard. Zero spend, no browser, no key.
- `auth.py` (EXPL-02): `detect_login_form` heuristic, `perform_login`, `capture_storage_state`/`load_storage_state_path`, `needs_relogin`, and the `maybe_relogin` perceive-node guard. The driver's hardcoded SauceDemo login is generalized to the heuristic + storageState reuse; creds flow ONLY through `get_decrypted_credentials`, are cached per-run outside the checkpointed state, and never reach a logger or a Neo4j node.
- 88 deterministic unit tests green with zero spend (70 prior + 7 fingerprint + 4 convergence + 7 auth).

## Task Commits

Each task committed atomically (TDD RED tests + GREEN impl folded into one feat commit per task):

1. **Task 1: Structural fingerprint module + swap into converge node (EXPL-06)** - `e3cb151` (feat)
2. **Task 2: Deterministic two-run convergence proof + loop-detector fix (EXPL-05)** - `0c9a5a1` (feat)
3. **Task 3: Heuristic auth — login detect, storageState, relogin recovery (EXPL-02)** - `0aac69c` (feat)

## Files Created/Modified
- `apps/api/app/services/explorer/fingerprint.py` - Pure structural_fingerprint + FingerprintConfig + fingerprint() seam; page_fingerprint/normalize_aria_tree adapters + the _DOM_TREE_JS walk.
- `apps/api/app/services/explorer/convergence.py` - run_over_fixtures harness driving the real converge/fingerprint/budget over fixtures.
- `apps/api/app/services/explorer/auth.py` - login detection/login/storageState/relogin + the per-run cred cache.
- `apps/api/app/services/explorer/nodes.py` - perceive computes current_fingerprint + calls maybe_relogin; persist/converge dedup by fingerprint; loop-detector PRIOR-pairs fix.
- `apps/api/app/services/explorer/state.py` - added current_fingerprint to ExplorerState.
- `apps/api/app/services/explorer/actions.py` - page_key re-scoped to the frontier (no longer the fingerprint stand-in).
- `apps/api/app/services/explorer/driver.py` - heuristic login + storageState reuse on the context; clear_creds in the finally.
- `apps/api/tests/fixtures/aria/__init__.py` - product-list (6/4/alt), cart, and login fixture node trees.
- `apps/api/tests/unit/test_fingerprint.py`, `test_convergence.py`, `test_auth_detect.py` - the three pure proof suites.

## Decisions Made
See key-decisions in frontmatter. The two load-bearing ones: (1) the pure-hash / live-adapter split keeps `structural_fingerprint` browser-free and AST-gated while `page_fingerprint` does the page walk; (2) the convergence proof is a `run_over_fixtures` harness driving the REAL converge/fingerprint/budget (not the live StateGraph, which needs a live page in every node) so the deterministic two-run guarantee exercises production code with zero stack.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Loop detector self-detected every first-occurrence step as "converged"**
- **Found during:** Task 2 (the two-run convergence harness)
- **Issue:** The Slice-1 converge node appended the current `(fingerprint, chosen_index)` pair into `seen_pairs` BEFORE evaluating `is_loop`, and `is_loop` was run against the state that already contained that pair — so every step found its own pair in history and stopped with `stop_reason="converged"` after a single step. This was masked in Slice 1 because the only multi-step converge path is the `live_llm`-marked discovery test (never run green without a key); the unit graph test does not multi-step the converge node.
- **Fix:** Capture the PRIOR `seen_pairs` first, run the loop check against them, then record this step's pair. The recurrence test now means "the same (fingerprint, action) on an EARLIER step", which is the intended loop semantics.
- **Files modified:** apps/api/app/services/explorer/nodes.py (converge)
- **Verification:** The two-run convergence proof now collapses to the correct 2-fingerprint set and stops on saturation; all 88 unit tests green; budget backstop test confirms a non-saturating world halts on max_steps (not a spurious "converged").
- **Committed in:** 0c9a5a1 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The fix was required for convergence to work at all (without it the loop never explores past one step). No scope creep — it corrects Slice-1 loop-detector ordering and is covered by the new convergence proof.

## Issues Encountered
- **`tests/functional/test_usage_ledger.py` flaked on an out-of-memory error** during a `docker compose exec` into the api container (`OSError: Cannot allocate memory`), under the Windows 3GB stack cap (api bounded to 1GiB, web holding ~814MiB). This is an environment/memory artifact unrelated to this plan's files (fingerprint/convergence/auth) — out of scope per the SCOPE BOUNDARY. Logged to `.planning/phases/04-explorer-agent/deferred-items.md`. The deterministic unit suite (88 tests, zero spend) is fully green.

## Known Stubs
- `explorer/actions.py` `locator_chain: None` — the full prioritized locator chain (data-testid→aria-label→role→text→xpath) remains Slice 3 (EXPL-09), an intentional documented seam carried from Slice 1. Does not block this plan's goal.
- `fingerprint.normalize_aria_tree` accepts an already-shaped node dict; a YAML/role-tree parser for the live `aria_snapshot()` is a documented seam (the live loop uses the DOM-walk `_DOM_TREE_JS` path today). Intentional — the hashing contract and the live extraction are both exercised.

## User Setup Required
None for the deterministic proofs (zero spend, no key). The live SauceDemo exploration proof still requires a provider key per 04-01 (the gateway decide call) — unchanged by this plan.

## Next Phase Readiness
- Dedup-by-fingerprint, saturation-based convergence, and heuristic auth are in place. Slice 3 layers the risk/origin gates + full locator chains over this; Slice 4 adds the SSE live view. Phase 5's canonical KG will MERGE on the same `fingerprint` key this plan now writes.
- No code blocker. The live convergence/discovery phase-gate still needs a provider key (documented in 04-01).

## Self-Check: PASSED

- All 7 created files verified present on disk.
- All 3 task commits verified in git (e3cb151, 0c9a5a1, 0aac69c).
- 88 deterministic unit tests green with zero spend; convergence proof passes with no key and no graph_mode.

---
*Phase: 04-explorer-agent*
*Completed: 2026-06-15*
