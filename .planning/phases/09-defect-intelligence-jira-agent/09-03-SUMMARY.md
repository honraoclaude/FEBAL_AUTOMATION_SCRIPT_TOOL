---
phase: 09-defect-intelligence-jira-agent
plan: 03
subsystem: api
tags: [jira, atlassian-python-api, adf, anyio, protocol, llm-gateway, no-key-fallback]

# Dependency graph
requires:
  - phase: 09-defect-intelligence-jira-agent (09-01)
    provides: "error_text persistence + jira_* settings (jira_url/email/api_token/project_key) + the deterministic classifier the description prose summarizes"
  - phase: 02-llm-gateway
    provides: "llm_gateway.complete(operation_type, run_id) metered path + deterministic no-key fallback + never-log-secret discipline"
provides:
  - "JiraGateway runtime_checkable Protocol (create_issue/add_attachment/search_jql/add_comment/create_issue_link) — the contract Plan 04's pipeline + router consume"
  - "AtlassianJira impl over atlassian-python-api 4.x (cloud=True, api_version=3), EVERY call offloaded via anyio.to_thread.run_sync; token boot-safe optional + never logged"
  - "FakeJira in-memory double — keyless-CI contract testing of create/attach/JQL-dedup/comment/link with no real Jira or token"
  - "Pure build_adf(...) -> ADF v3 description doc DICT (Cloud-v3-safe; never a string)"
  - "describe(...) -> (prose, enriched) LLM description-prose enrichment with a deterministic no-key fallback (D-01: prose-only, never class/confidence)"
affects: [09-04 (defect pipeline + /api/defects router), 10 (traceability rendering)]

# Tech tracking
tech-stack:
  added: ["atlassian-python-api==4.0.* (gated, human-verified) + transitives (beautifulsoup4, deprecated, jmespath, oauthlib, requests-oauthlib, soupsieve, wrapt)"]
  patterns:
    - "JiraGateway Protocol + FakeJira double (program-to-the-contract; keyless CI; live filing Manual-Only)"
    - "sync external client offloaded via anyio.to_thread.run_sync from async FastAPI (T-09-09)"
    - "ADF v3 description = a pure-built doc DICT, never a string (Cloud v3; T-09-10)"
    - "LLM prose-only enrichment with deterministic no-key fallback + enriched flag (D-01)"

key-files:
  created:
    - apps/api/app/services/jira/__init__.py
    - apps/api/app/services/jira/client.py
    - apps/api/app/services/jira/fake.py
    - apps/api/app/services/jira/adf.py
    - apps/api/app/services/jira/description.py
    - apps/api/tests/unit/test_jira_create.py
    - apps/api/tests/unit/test_adf.py
    - apps/api/tests/unit/test_jira_description.py
  modified:
    - apps/api/pyproject.toml
    - apps/api/uv.lock

key-decisions:
  - "AtlassianJira builds the underlying atlassian.Jira lazily (first call, only when configured) so importing/constructing it is boot-safe without a token"
  - "describe() short-circuits to the deterministic fallback when no provider key is set — the gateway is never even called keyless (provider-key check mirrors llm_gateway._estimate_input_tokens)"
  - "FakeJira mints FAKE-{n} and tags new issues statusCategory='To Do' so the `statusCategory != Done` dedup query finds them, mirroring live behaviour"

patterns-established:
  - "Pattern: JiraGateway Protocol + hand-written FakeJira double = keyless-CI contract, no recorded-HTTP lib (responses/vcrpy avoided)"
  - "Pattern: every sync Jira call wrapped in anyio.to_thread.run_sync; the gateway exposes async methods"
  - "Pattern: D-01 LLM boundary — description.py is the ONLY jira/ gateway consumer; client/adf/fake stay LLM-free (test-enforced)"

requirements-completed: [JIRA-01]

# Metrics
duration: 9min
completed: 2026-06-28
---

# Phase 9 Plan 03: Jira Agent Seam Summary

**JiraGateway Protocol + AtlassianJira (atlassian-python-api 4.x, every call via anyio.to_thread) + FakeJira double + pure ADF v3 doc-dict builder + LLM description-prose enrichment with a deterministic no-key fallback — all of JIRA-01 keyless-CI-testable without a real Jira instance or token.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-06-28T00:18:04Z
- **Completed:** 2026-06-28T00:27:54Z
- **Tasks:** 3 (Task 1 was a human-verified gated install, pre-approved)
- **Files modified:** 10 (8 created, 2 modified)

## Accomplishments
- Gated install of the ONE new dependency this phase — `atlassian-python-api==4.0.7` (human-verified) — with `anyio` confirmed transitive and NOT added.
- `JiraGateway` runtime_checkable Protocol with the five async methods, satisfied by BOTH `AtlassianJira` (real, sync-offloaded) and `FakeJira` (in-memory).
- `AtlassianJira` constructs `atlassian.Jira(cloud=True, api_version="3")` lazily, wraps EVERY library call in `anyio.to_thread.run_sync` (T-09-09), and never logs the token/password (T-09-08).
- `FakeJira` makes the whole create/attach/JQL-dedup/comment/link contract keyless-testable: dedup matches `labels = "fp-<hash>" AND statusCategory != Done`, excludes Done issues, and a second identical failure updates-not-duplicates.
- Pure `build_adf(...)` returns an ADF v3 description doc DICT (never a string — T-09-10), with the prose, the Steps-to-Reproduce orderedList, and Expected/Actual/Severity/Priority paragraphs.
- `describe(...)` routes the description prose through `llm_gateway.complete(operation_type="defect.describe", run_id)` and degrades to a deterministic evidence-summary fallback (with `enriched=False`) when keyless or refused.

## Task Commits

1. **Task 1: Gated install — atlassian-python-api 4.0.*** - `1260e5c` (chore) — human-verified before install
2. **Task 2: JiraGateway Protocol + AtlassianJira + FakeJira + contract test** - `78d61dc` (feat)
3. **Task 3 (TDD): pure ADF v3 builder + description prose enrichment**
   - RED: `e8d9e39` (test) — failing tests for adf.py + description.py
   - GREEN: `7d55240` (feat) — implementations; deterministic suite green

## Files Created/Modified
- `apps/api/app/services/jira/__init__.py` - Package seam; exports the Protocol, both impls, JiraNotConfiguredError, build_adf
- `apps/api/app/services/jira/client.py` - `JiraGateway` Protocol + `AtlassianJira` (anyio.to_thread, lazy client, token never logged, `JiraNotConfiguredError`)
- `apps/api/app/services/jira/fake.py` - `FakeJira` in-memory double; fp-<hash> dedup match + `statusCategory != Done` exclude; records calls
- `apps/api/app/services/jira/adf.py` - Pure `build_adf(...)` returning the ADF v3 description doc dict
- `apps/api/app/services/jira/description.py` - `describe(...) -> (prose, enriched)`; gateway-routed prose with deterministic no-key fallback
- `apps/api/tests/unit/test_jira_create.py` - Keyless JIRA-01/03/04 contract via FakeJira + token-never-logged acceptance
- `apps/api/tests/unit/test_adf.py` - ADF v3 doc-dict shape assertions
- `apps/api/tests/unit/test_jira_description.py` - No-key fallback + enriched-flag + D-01 boundary assertions
- `apps/api/pyproject.toml`, `apps/api/uv.lock` - the single gated dependency

## Decisions Made
- **Lazy client construction in AtlassianJira:** the underlying `atlassian.Jira` is built only on first call AND only when configured, so importing the module + constructing the object is boot-safe without a token (and `isinstance(AtlassianJira(), JiraGateway)` holds keyless).
- **Keyless short-circuit in describe():** when no provider key is set, `describe()` returns the deterministic fallback WITHOUT touching the gateway (a test asserts the gateway is not called) — mirrors the gateway's own `settings.anthropic_api_key` check.
- **Token-safety made a test, not a hope:** a static acceptance scans `client.py` and fails if any `log.*` line references `token`/`password` (T-09-08).

## Deviations from Plan

None - plan executed exactly as written. (The unused `pytest` import flagged by ruff in the RED test file was cleaned up within the same Task 3 GREEN commit, not a behavioural deviation.)

## Issues Encountered
- The package `__init__.py` initially imported `adf` (a Task 3 module) which broke Task 2 collection. Resolved by importing only Task-2 symbols in `__init__.py` for the Task 2 commit, then adding `build_adf` to the exports in Task 3 — which also preserves a clean TDD RED (adf.py genuinely absent when the RED tests ran).

## TDD Gate Compliance
Task 3 followed RED -> GREEN: `e8d9e39` (test, failing) precedes `7d55240` (feat, passing). No REFACTOR commit was needed. The RED run failed on `ModuleNotFoundError`/`ImportError` (adf.py + description as desc absent) — no test passed unexpectedly before implementation.

## User Setup Required
**Live Jira filing/dedup is Manual-Only** (no Jira instance in dev). The contract is fully proven via `FakeJira`; to exercise the live path later, set `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` (per the plan's `user_setup`). The description LLM enrichment additionally needs a provider key; without one it uses the deterministic fallback and the UI shows the honest "written without an LLM" caption.

## Next Phase Readiness
- The `JiraGateway` Protocol + `FakeJira` + `build_adf` + `describe` are the exact seam Plan 04's defect pipeline + `/api/defects` router consume (file/dedup via the gateway, ADF body via build_adf, prose via describe).
- No blockers. The deterministic suite is green keyless (385 passed with local Postgres; 370 passed core-only).

## Self-Check: PASSED

---
*Phase: 09-defect-intelligence-jira-agent*
*Completed: 2026-06-28*
