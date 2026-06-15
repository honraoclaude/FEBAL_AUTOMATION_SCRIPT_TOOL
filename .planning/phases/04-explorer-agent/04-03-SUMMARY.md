---
phase: 04-explorer-agent
plan: 03
subsystem: api
tags: [risk-classifier, deny-list, origin-allowlist, prompt-injection, untrusted-delimiting, locator-chain, healing-history, workflow-detection, form-validation, neo4j, explorer, defense-in-depth]

# Dependency graph
requires:
  - phase: 04-explorer-agent (04-01)
    provides: "explorer/ package — act node (gate insertion point), decide node (untrusted prompt), enumerate/actions menu with the documented locator stub, persist_to_neo4j (parameterized Cypher + read-back), ExplorerState"
  - phase: 04-explorer-agent (04-02)
    provides: "structural fingerprint as the converge/persist dedup key; per-run cred cache"
  - phase: 01-foundation-dev-environment
    provides: "Target.sandbox (lifts the deny) + Target.origin_allowlist (origin gate) fields"
provides:
  - "risk.py: pure DENY_VERBS frozenset + is_destructive(action, *, sandbox) (sandbox lifts the deny, D-03) + is_off_origin(url, allowlist) (D-04) — code-enforced, never LLM judgment"
  - "act-node safety gate: is_destructive + is_off_origin run AFTER the LLM index pick and BEFORE the click/goto (defense in depth, Pitfall 5); refusals record a feed line and clear pending_action so navigate() cannot follow a refused url (EXPL-07/08)"
  - "untrusted-observation delimiting verified in the decide prompt (system says data-only/index-only; page text fenced in <<<UNTRUSTED_OBSERVATION>>>...<<<END>>>)"
  - "locators.py: pure build_locator_chain (data-testid[+data-test]->aria-label->role->text->xpath) + merge_locator_history (append-only) + async extract_locator_chain; menu locator_chain field filled (retires the Slice-1 stub); Element nodes persist chain_json/history_json via parameterized Cypher + read-back (EXPL-09)"
  - "pure parse_workflow_flag + extract_validation_rules; (:Workflow)-[:STEP {order}]->(:Page) chain + (:Page)-[:HAS_FORM]->(:Form {validation_rules}) writes; gated HTML5 validation probe in the act node (only when the risk gate ALLOWED the submit) (EXPL-04)"
affects: [04-04-sse-live-view, 05-knowledge-graph, 08-self-healing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deterministic code-enforced safety gate AFTER the LLM decision and BEFORE the act (defense in depth): an injected LLM that picks a destructive/off-origin action is refused by a static deny-list/allowlist — never 'ask the LLM if this is safe' (D-03/D-04, Pitfall 5)"
    - "Pure-logic / live-read split repeated for locators: build_locator_chain + merge_locator_history are import-pure and table-tested on fixture dicts; extract_locator_chain only does the async attribute reads then delegates"
    - "Per-step scratch fields (workflow_flag, validation_submit_result) ALWAYS reset to None by their producing node so a prior step's value never re-persists across the LangGraph state merge"
    - "Workflow/Form writes reuse the managed execute_write + read-back + parameterized-Cypher invariant (JSON params for chain/history/validation — never f-string page-derived text, T-04-14/T-04-15)"

key-files:
  created:
    - apps/api/app/services/explorer/risk.py
    - apps/api/app/services/explorer/locators.py
    - apps/api/tests/unit/test_risk.py
    - apps/api/tests/unit/test_safety.py
    - apps/api/tests/unit/test_locators.py
    - apps/api/tests/unit/test_workflow_detect.py
  modified:
    - apps/api/app/services/explorer/nodes.py
    - apps/api/app/services/explorer/actions.py
    - apps/api/app/services/explorer/state.py
    - apps/api/app/services/explorer/driver.py

key-decisions:
  - "The risk + origin gate lives in the act node (AFTER decide, BEFORE the click/goto), not in decide — this is the defense-in-depth seam: even a fully prompt-injected LLM cannot trigger a destructive/off-origin action because the deny-list/allowlist is static code (Pitfall 5). Refusals clear pending_action so the deferred goto in navigate() is also cancelled."
  - "sandbox + origin_allowlist were added to ExplorerState (JSON-safe bool/list) and seeded from the Target row in the driver — the gate reads them off state, not the db, keeping the act node browser/db-light and checkpoint-safe."
  - "Locator history is an append-only per-element dict on JSON-safe state (element_history keyed by element key); a re-observed element APPENDS a step-stamped chain snapshot. The Element node stores chain_json + history_json as JSON params. Documented minimal-but-real seam — Phase 5 owns the canonical Element Repository."
  - "The workflow note is METADATA the LLM may append after its index ('2 step 3 of checkout'); parse_index already stops at the first non-digit so the index parse is unaffected. The action is ALWAYS the index, never a selector (D-02 preserved)."
  - "The form-validation probe is HTML5-native (el.checkValidity()/validationMessage via page.evaluate), reachable ONLY in the act click path AFTER the destructive gate passed — so a non-sandbox destructive form is never probed (gated by is_destructive, by construction of the gate ordering)."

patterns-established:
  - "DENY_VERBS frozenset substring match on label+confirm_text (multi-word phrases like 'submit order' as substrings); default-allow safe verbs; sandbox short-circuits to allow"
  - "is_off_origin reduces both the candidate URL and allowlist entries to scheme://host[:port] (case-insensitive), fail-closed on a relative/garbage URL and on an empty allowlist"
  - "Locator chain in healing-priority order with xpath always appended last as the guaranteed fallback; data-testid tier checks BOTH data-testid and data-test (SauceDemo)"

requirements-completed: [EXPL-07, EXPL-08, EXPL-09, EXPL-04]

# Metrics
duration: 10min
completed: 2026-06-15
---

# Phase 4 Plan 03: Safety, Locators, Workflows Summary

**A pure code-enforced safety layer (deny-list risk classifier + origin allowlist, sandbox-lifted) runs in the act node AFTER the LLM index pick and BEFORE any click/goto so an injected page cannot trigger a destructive or off-origin action; untrusted page text is fenced as data-only in the decide prompt; every element carries the full prioritized locator chain (data-testid->aria-label->role->text->xpath) + append-only history persisted as Neo4j Element nodes; and multi-step workflows + form-validation rules are detected and written as Workflow/STEP chains + Form.validation_rules — all deterministic logic table-tested with zero spend.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-15T13:38:47Z
- **Completed:** 2026-06-15T13:48Z (approx)
- **Tasks:** 3 (all TDD: tests + pure modules + wiring per task)
- **Files created/modified:** 10

## Accomplishments
- `risk.py` (EXPL-07/08): the `DENY_VERBS` frozenset (RESEARCH canonical list) + pure `is_destructive(action, *, sandbox)` (sandbox lifts the deny, D-03) + `is_off_origin(url, allowlist)` (origin membership, D-04). No browser, no LLM, no db — a tiny pure guard like `run_service._validate_status`.
- The **act node** now runs both gates BEFORE the click/goto (defense in depth, Pitfall 5). A destructive pick on a non-sandbox target or an off-origin url is REFUSED — a `"Refused … — destructive action blocked"` / `"… — outside allowed origins"` feed line is recorded and `pending_action` is cleared so `navigate()` cannot follow the refused url next loop. `sandbox` + `origin_allowlist` were added to `ExplorerState` and seeded from the Target row in the driver.
- Untrusted-observation delimiting verified end-to-end in `decide`: the system prompt declares the OBSERVATION block data-only/index-only and the snapshot is fenced in `<<<UNTRUSTED_OBSERVATION>>> … <<<END_UNTRUSTED_OBSERVATION>>>`. `test_safety.py` proves an injected `"IGNORE PREVIOUS INSTRUCTIONS …"` sits inside the fence AND that a destructive/off-origin pick is still refused by the gate.
- `locators.py` (EXPL-09): pure `build_locator_chain` (data-testid[+data-test]→aria-label→role+name→text→xpath, xpath always last) + pure append-only `merge_locator_history` + async `extract_locator_chain`. The Slice-1 `locator_chain: None` stub in `actions.py` is retired (now filled per element). `persist_to_neo4j` writes the Element's `chain_json` + `history_json` via parameterized Cypher + read-back; `element_history` accumulates on JSON-safe state.
- Workflow + form-validation detection (EXPL-04): pure `parse_workflow_flag` (`"step N of flow X"` → `{flow, order}`) + pure `extract_validation_rules` (`{field, message}`). `decide` carries an optional workflow note (still index-only action). `persist` writes `(:Workflow)-[:STEP {order}]->(:Page)` + `(:Page)-[:HAS_FORM]->(:Form {validation_rules})` via parameterized Cypher + read-back. The act node runs a HTML5-native validation probe ONLY in the click path after the destructive gate passed — never on a refused destructive form.
- **138 deterministic unit tests green, zero spend** (88 prior + 34 risk/safety + 8 locators + 8 workflow). Ruff clean on all changed files.

## Task Commits

1. **Task 1: Deterministic risk classifier + origin allowlist + untrusted delimiting** — `ae02a66` (feat)
2. **Task 2: Prioritized locator-chain extraction + history, persisted as Neo4j Element** — `f306387` (feat)
3. **Task 3: Multi-step workflow + form-validation detection** — `656f3b5` (feat)

## Files Created/Modified
- `apps/api/app/services/explorer/risk.py` — pure `DENY_VERBS` + `is_destructive` + `is_off_origin`.
- `apps/api/app/services/explorer/locators.py` — pure `build_locator_chain` + `merge_locator_history` + async `extract_locator_chain` + xpath JS.
- `apps/api/app/services/explorer/nodes.py` — act-node risk/origin gate + refusal feed lines; `parse_workflow_flag`/`extract_validation_rules`; `_write_workflow_step`/`_write_form_validation`; gated `_probe_form_validation`; Element chain/history persistence; per-step scratch resets.
- `apps/api/app/services/explorer/actions.py` — menu `locator_chain` field filled via `extract_locator_chain` (stub retired).
- `apps/api/app/services/explorer/state.py` — `sandbox`, `origin_allowlist`, `element_history`, `workflow_flag`, `workflow_chain`, `validation_submit_result` added (all JSON-safe).
- `apps/api/app/services/explorer/driver.py` — seeds `sandbox`/`origin_allowlist` from the Target row + the new scratch fields in the initial state.
- `apps/api/tests/unit/test_risk.py`, `test_safety.py`, `test_locators.py`, `test_workflow_detect.py` — the four pure proof suites.

## Decisions Made
See key-decisions in frontmatter. The load-bearing one: the safety gate lives in the **act node AFTER decide**, so the deny-list/allowlist sits between the LLM decision and execution — an injected LLM cannot bypass static code (Pitfall 5 defense in depth). The gate reads `sandbox`/`origin_allowlist` off JSON-safe state (seeded once from the Target row), keeping the act node checkpoint-safe.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Moved get_handles into the click-only branch of the act node**
- **Found during:** Task 1 (the sandbox-pass safety test)
- **Issue:** The act node resolved `get_handles(run_id).page` before branching on url-vs-click, so a url-bearing action with no registered handle (the pure unit test for "sandbox lifts the deny, gate passes a url action to navigate()") raised `RuntimeError: no browser handles registered`. The page is only needed for the click path.
- **Fix:** Moved `page = get_handles(...)` inside the `if not target_url:` (click) branch; the url-bearing path returns without touching the registry (it defers the goto to `navigate()`).
- **Files modified:** apps/api/app/services/explorer/nodes.py (act)
- **Verification:** `test_safety.py::test_sandbox_target_allows_destructive_through_the_gate` passes; the live url path still defers to `navigate()` unchanged.
- **Committed in:** ae02a66 (Task 1 commit)

**2. [Rule 3 - Blocking] Hoisted `import re` to the module import block + dropped unused test imports**
- **Found during:** post-Task-3 ruff lint
- **Issue:** `import re` was placed mid-file next to the workflow regexes (E402-adjacent / ruff F401 placement), and `test_safety.py` carried an unused `import pytest` + an unused `from … import nodes`.
- **Fix:** Moved `import re` to the top stdlib import block; removed the two unused imports from `test_safety.py`.
- **Files modified:** apps/api/app/services/explorer/nodes.py, apps/api/tests/unit/test_safety.py
- **Verification:** `ruff check` → "All checks passed!"; affected tests re-run green.
- **Committed in:** 656f3b5 (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (both blocking — a test-blocking handle resolution + lint cleanliness). No scope creep — the gate, locators, workflow/validation are exactly as planned.

## Issues Encountered
- None blocking. The container-OOM `test_usage_ledger` flake noted in 04-02 (Windows 3GB cap) was NOT triggered — this plan adds only pure modules + state/node wiring and the full deterministic unit suite (138 tests) ran green in ~14s with zero spend, no docker exec.

## Known Stubs
- The Neo4j Element/Workflow/Form writes are a documented **minimal-but-real seam** (RESEARCH:357-363): they MERGE on run-tagged keys and pass the read-back guard, but the canonical Element Repository, flow categorization, risk scoring, and idempotent fingerprint-keyed dedup are Phase 5 (KG-03/04/05). Intentional — does not block this plan's goal (the chains + rules are written and structurally correct).
- The live form-validation probe (`_probe_form_validation`) and the workflow/Element/Form Neo4j writes are exercised structurally by the pure unit tests; the end-to-end live landing under `graph + live_llm` still requires a provider key (carried from 04-01) — see Next Phase Readiness.

## Threat Flags
None — no new network endpoints, auth paths, or trust-boundary surface beyond the plan's `<threat_model>` (T-04-11..15 are all mitigated by this plan: deny-list gate, origin gate, untrusted delimiting + defense in depth, parameterized Cypher, read-back guard).

## User Setup Required
None for the deterministic proofs (zero spend, no key). The live SauceDemo exploration proof (>=2 fingerprints + Element/Workflow nodes landing under `graph + live_llm`) still requires a provider key per 04-01 — unchanged by this plan.

## Next Phase Readiness
- The Explorer is now trustworthy (code-enforced safety, injection-resistant) and produces structured discovery output (locator chains + history, workflow chains, form-validation rules) that Phase 5's canonical KG and Phase 8's self-healing consume directly. The `(:Page)-[:HAS_ELEMENT]->(:Element {chain_json, history_json})` + `(:Workflow)-[:STEP]->(:Page)` + `(:Form {validation_rules})` writes MERGE on the same run-tagged keys Phase 5 will normalize.
- Slice 4 (04-04) layers the SSE live view over this — the refusal feed lines + workflow/validation feed entries are already emitted into `events` for the stream.
- No code blocker. The live phase-gate proof needs a provider key (documented in 04-01).

## Self-Check: PASSED

- All 6 created files verified present on disk.
- All 3 task commits verified in git (ae02a66, f306387, 656f3b5).
- 138 deterministic unit tests green with zero spend; ruff clean; risk.py is pure (no playwright/llm/db); no LLM-judged safety / init_chat_model usage in the explorer.

---
*Phase: 04-explorer-agent*
*Completed: 2026-06-15*
