---
phase: 03-tracer-bullet-minimal-end-to-end-loop
plan: 03
subsystem: generation
tags: [generation, llm-gateway, gherkin, jinja2, playwright-spec, run-id, bdd, workspaces, auth-gate]

# Dependency graph
requires:
  - phase: 03-tracer-bullet-minimal-end-to-end-loop
    plan: 01
    provides: gherkin-official 29.x parser (transitive), jinja2 3.1, neo4j lifespan driver get_neo4j(), graph marker
  - phase: 03-tracer-bullet-minimal-end-to-end-loop
    plan: 02
    provides: Run/Execution model + run_service.get_run, POST /explore writing Page/NavigatesTo by run_id, shared/events, poll_until_terminal
  - phase: 02-llm-gateway
    plan: 01
    provides: llm_gateway.complete(db, messages, *, operation_type, run_id, max_tokens) -> LLMResult (the ONLY LLM path), fake_chat_model unit fixture
provides:
  - generation service (generate_bdd + generate_scripts) routing exclusively through the metered LLM gateway by run_id (D-07)
  - gherkin-official validate-before-write gate (malformed Gherkin -> GenerationError, no .feature)
  - Jinja2 spec skeleton (app/templates/test_login.py.j2) owning ALL spec structure + the observed SauceDemo selectors; LLM fills only narrow slots
  - POST /api/generate-bdd + /api/generate-scripts (auth-gated) returning run_id-keyed artifact paths under workspaces/<run_id>/
  - mocked-gateway unit determinism + live_llm end-to-end SC2 functional proof
affects: [execution, phase-04-explorer, phase-05-kg, phase-06-bdd-generation]

# Tech tracking
tech-stack:
  added: []   # no new deps — jinja2 + gherkin-official already present from 03-01
  patterns:
    - "Generation is metered-only (D-07): both steps call llm_gateway.complete() with the explore run_id; NO direct provider/init_chat_model chat call (grep-asserted)"
    - "Validate-before-write: gherkin-official Parser().parse(text) gates the .feature; a malformed result writes NOTHING"
    - "Jinja2 owns ALL spec structure AND every selector (the observed set is hard-coded in the template, not a slot); the LLM fills only a narrow sanitized scenario label (Pitfall 5)"
    - "ast.parse() on the rendered spec before writing — a non-importable spec raises GenerationError instead of landing on disk"
    - "Artifacts land under workspaces/<run_id>/ resolved relative to the repo (gitignored workspaces/*), keyed by the run_id that threads explore -> generate -> execute"

key-files:
  created:
    - apps/api/app/services/generation.py
    - apps/api/app/templates/test_login.py.j2
    - apps/api/app/routers/generate.py
    - apps/api/tests/unit/test_generation_render.py
    - apps/api/tests/functional/test_generation.py
  modified:
    - apps/api/app/schemas/run.py
    - apps/api/app/main.py

key-decisions:
  - "Both generate-bdd and generate-scripts route through llm_gateway.complete() with the explore run_id (D-07) — never a direct provider call; the gateway owns budgets/kill-switch/cache/ledger."
  - "gherkin-official validates result.content BEFORE the file write; on a malformed result generate_bdd raises GenerationError and writes NO .feature (T-03-12)."
  - "The Jinja2 template (test_login.py.j2) owns ALL structure and hard-codes the observed selectors (#user-name/#password/#login-button/.inventory_list); the LLM fills only a narrow, sanitized scenario label — never control flow or selectors (Pitfall 5)."
  - "SauceDemo PUBLIC demo creds (standard_user/secret_sauce) are literal template values, never target ciphertext or decrypted creds (PLAT-07 / T-03-10)."
  - "The graph read for run_id is best-effort: on any neo4j error it returns [] and generation stays grounded in the deterministic observed selectors, so a missing graph never blocks the tracer (unit tests need no live graph)."

patterns-established:
  - "Generation endpoints mirror targets.py: router-level Depends(get_current_user) + typed-exception translation (GenerationError -> 422, unknown run_id -> 404)."
  - "SC2 deterministic parts (gateway routing, gherkin validation, Jinja render, file write) are proven zero-spend with fake_chat_model; the real-spend runnable-spec proof is a gated live_llm functional test."

requirements-completed: []   # PLAT-02 stays OPEN — full 10-endpoint surface (with 501 stubs) lands in 03-04

# Metrics
duration: 70min
completed: 2026-06-14
---

# Phase 3 Plan 03: Generation Service (generate-bdd + generate-scripts) Summary

**A metered generation service that reads the explored graph for a run_id, routes BOTH generate-bdd and generate-scripts through the Phase-2 LLM gateway (D-07), validates the returned Gherkin with gherkin-official BEFORE writing, renders a runnable pytest-playwright spec from a Jinja2 skeleton (the LLM fills only crawl-observed SauceDemo selectors — Pitfall 5), and writes both artifacts under `workspaces/<run_id>/` — surfaced by auth-gated POST /generate-bdd and /generate-scripts, with the run_id threading explore -> generate.**

## Performance

- **Duration:** ~70 min
- **Tasks:** 3 auto (Task 1 TDD-style: unit determinism test alongside the service)
- **Files:** 5 created, 2 modified + this SUMMARY

## Accomplishments

- **Task 1 — Jinja2 skeleton + generation service.** `app/templates/test_login.py.j2` is a pytest-playwright SYNC spec skeleton that owns ALL structure (imports, the `test_login` function, navigation, login flow, `.inventory_list` assertion) and hard-codes the four observed selectors — the LLM cannot inject a selector. `app/services/generation.py` implements `generate_bdd(db, run_id)` (reads Page nodes for run_id to ground the prompt via parameterized Cypher; calls `llm_gateway.complete(operation_type="generate-bdd", run_id=run_id)`; validates `result.content` with `gherkin.parser.Parser().parse(...)`; writes `workspaces/<run_id>/login.feature` ONLY when valid) and `generate_scripts(db, run_id)` (calls the gateway with `operation_type="generate-scripts"` for a narrow scenario label, renders the Jinja2 skeleton with SauceDemo's public demo creds as literal values, `ast.parse()`s the result, writes `workspaces/<run_id>/test_login.py`, and returns the spec_path). Both steps route exclusively through `llm_gateway.complete()` — no direct provider call.
- **Task 2 — generate router + main wiring.** `app/routers/generate.py` mirrors targets.py: `APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])` with `POST /generate-bdd` and `POST /generate-scripts`, a `GenerateRequest(run_id)` Pydantic body (added to `schemas/run.py`), an unknown-run_id -> 404 guard via `run_service.get_run`, and `GenerationError -> 422` translation. Included in `main.py` after explore/executions. Verified live: both routes appear in the OpenAPI surface and return **401 unauthenticated**.
- **Task 3 — tests.** `tests/unit/test_generation_render.py` proves (zero spend, via `fake_chat_model`): valid Gherkin -> `login.feature` written; malformed Gherkin (`"not gherkin {{{"`) -> `GenerationError` + NO file; `generate_scripts` -> ast-parseable `test_login.py` referencing only the observed selectors + the public demo creds; and a source grep that generation never calls `init_chat_model` directly. `tests/functional/test_generation.py` adds the default-gate auth-gate proof (401 on both endpoints) and the `live_llm+graph` end-to-end SC2 proof (explore -> generate-bdd -> generate-scripts -> both artifacts exist + spec ast-parseable), gated off the default suite.

## Task Commits

1. **Task 1** — `8c69958` (feat): generation service + Jinja2 skeleton + unit determinism test.
2. **Task 2** — `a8a679d` (feat): generate router + GenerateRequest schema + main wiring.
3. **Task 3** — `4842710` (test): auth-gate (default) + live_llm end-to-end SC2 proof.

Plan metadata (this SUMMARY + STATE/ROADMAP) committed separately.

## Verification

- `cd apps/api && uv run pytest tests/unit/test_generation_render.py -q` -> **4 passed**.
- `cd apps/api && uv run pytest -m "not live_llm and not e2e and not graph" -q` -> **79 passed, 13 deselected** (after restarting the api container so the new router loads).
- Live: `POST /api/generate-bdd` and `/api/generate-scripts` both return **401** unauthenticated; both appear in `/openapi.json`.
- Grep: `generation.py` contains `llm_gateway.complete(` for both operations and NO direct `init_chat_model` call site.

## Deviations from Plan

### Auto-fixed blocking issues (Rule 3)

**1. [Rule 3 — Blocking] New router/service/template files not picked up by the running api container**
- **Found during:** Task 3 live verification — `POST /api/generate-bdd` returned 404 and `/openapi.json` listed no generate routes, even though the files are inside the bind-mounted `app/` tree.
- **Issue:** uvicorn's `--reload` watcher did not register the brand-new files (new router module + new `templates/` dir) without a process restart; the verification environment (D-07 is "the right place to prove the gateway end-to-end") needs the routes live to assert the 401 auth gate.
- **Fix:** `docker compose -f infra/docker-compose.yml restart api`; after restart both routes appear in OpenAPI and return 401 unauthenticated. No code change — purely a verification-environment readiness step (checkpoint "automation before verification").
- **Files:** none (operational).

**Total deviations:** 1 (Rule 3 verification-environment readiness; no scope or code change). No Rule 4 architectural decisions; no auth gates encountered.

## Known Stubs

- The generate-bdd prompt grounds on the explored Page nodes when neo4j is reachable, but on any graph error it falls back to `[]` and generates from the known SauceDemo login flow. This is intentional tracer pragmatism (the deterministic observed selectors carry generation regardless) and lets the unit suite run with no live graph. The real graph-grounded path is exercised by the `live_llm+graph` functional test.
- The generated `.feature` is a validated artifact but is NOT yet driven via pytest-bdd step defs — `/execute` (Plan 04) runs the plain pytest-playwright `test_login.py` (RESEARCH Open Q1: tracer favors the plain spec). Documented and intentional.

## Threat Flags

None — all new surface is covered by the plan's registered threat_model and mitigated as planned: D-07 metered-only routing (no provider key/creds in prompts or artifacts — T-03-10), gherkin-official validate-before-write + Jinja2-owned structure (T-03-12), observed-selectors-only prompt with no raw DOM (T-03-11, scoped), router-level auth gate with a 401 test (T-03-13), and the gateway's inherited budget/kill-switch (T-03-14). The literal creds in the spec are SauceDemo's public demo creds, never target ciphertext (PLAT-07).

## Issues Encountered

- The default-gate run intermittently surfaced a `httpx.ReadTimeout` on `test_auth.py::test_login_sets_httponly_cookies` immediately after the container restart (cold-start argon2 login latency, unrelated to this plan); it passes on its own and on a clean re-run (79 passed). Not a generation regression.

## Next Phase Readiness

- generate-bdd produces one gherkin-validated `.feature` and generate-scripts produces one runnable, ast-parseable pytest-playwright spec under `workspaces/<run_id>/`, both threaded by the explore run_id — Plan 04's `/execute` slice can subprocess-run the returned spec_path and finish the Execution row.
- PLAT-02 stays OPEN — the full 10-endpoint surface (with 501 stubs) and the run_id traceability sweep land in 03-04.

## Self-Check: PASSED

- FOUND: apps/api/app/services/generation.py
- FOUND: apps/api/app/templates/test_login.py.j2
- FOUND: apps/api/app/routers/generate.py
- FOUND: apps/api/tests/unit/test_generation_render.py
- FOUND: apps/api/tests/functional/test_generation.py
- FOUND commit: 8c69958 (Task 1)
- FOUND commit: a8a679d (Task 2)
- FOUND commit: 4842710 (Task 3)

---
*Phase: 03-tracer-bullet-minimal-end-to-end-loop*
*Completed: 2026-06-14*
