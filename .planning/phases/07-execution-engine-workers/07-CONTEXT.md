# Phase 7: Execution Engine & Workers - Context

**Gathered:** 2026-06-20
**Status:** Ready for planning (needs --research-phase — RabbitMQ worker topology under the 3GB cap, pytest-bdd tier tagging + risk-based selection, per-step artifact capture wiring, the flaky-retry classifier, and the graceful Redis-flag kill drain have no canonical reference)

<domain>
## Phase Boundary

Turn Phase 6's accepted, owned Playwright automation into a RUN-AT-SCALE execution engine. The user runs tiered regression suites — smoke, sanity, regression, full, and risk-based — as RabbitMQ-distributed parallel Playwright workers (NO LLM anywhere in the execution loop), watches a live per-test view with a kill switch, and gets full per-step evidence (screenshots, trace, console/network logs, video-on-failure) stored on the filesystem with paths in PostgreSQL. Execution history shows pass/fail trends, durations, and flaky-test detection (retries distinguish infra flake from product failure). The SAME suite runs locally, in Docker, and from a GitHub Actions trigger with status reported back, and two consecutive runs against a reset target produce identical results. Delivers EXEC-01..EXEC-06. UI hint: yes (live execution view + execution history → needs a UI-SPEC).

**In scope:** suite-tier model + risk-based dynamic selection (EXEC-01); local/Docker/CI execution parity + GitHub Actions trigger with status reporting (EXEC-02); RabbitMQ-distributed stateless workers with browser- and flow-level parallelism (EXEC-03); per-step artifact capture (screenshots/trace/logs always, video on failure) on the filesystem with paths in Postgres (EXEC-04); execution history with pass/fail trends, durations, and flaky detection via a retry classifier (EXEC-05); the live execution view + kill switch (EXEC-06); determinism (two runs vs a reset target identical).
**Out of scope (own phases):** self-healing of failing tests (Phase 8); failure CLASSIFICATION into product/infra/test-bug + Jira filing (Phase 9 — this phase's flaky-retry classifier only distinguishes infra-flake from product-failure for retry purposes, it does NOT do defect intelligence); dashboards/RBAC/coverage/Elasticsearch search (Phase 10); K8s manifests + CI/CD for PLATFORM images + Prometheus/Grafana (Phase 11 — this phase delivers the CI trigger that RUNS suites, not the platform's own build/deploy pipeline); MinIO/S3 artifact store (deferred — ROADMAP SC4 mandates filesystem + Postgres paths this phase).

</domain>

<decisions>
## Implementation Decisions

### Suite tiers & risk-based selection (EXEC-01)
- **D-01:** Tier membership is expressed as NATIVE Gherkin tags on scenarios (`@smoke` / `@sanity` / `@regression`), authored at generation time and editable in the Phase-6 review queue. `full` = every approved/accepted spec. Execution maps a tier to a pytest-bdd marker selector (`pytest -m smoke`). Native to pytest-bdd, keeps the reviewer in control of tier composition, no new column.
- **D-02:** The `risk-based` tier is computed DYNAMICALLY at run time — top-N flows by (Phase-5 flow risk score + recent failure history from execution history), NOT a stored tier. So it always reflects the latest risk + failure signal. (Research: the exact N / ranking formula — risk-weight vs failure-weight — and whether failure history is read from the EXEC-05 history tables.)

### Worker / parallelism model under the 3GB cap (EXEC-03)
- **D-03:** A SINGLE dedicated worker container (new compose service under the `queue` profile alongside RabbitMQ) consumes the execution queue with `prefetch_count` = parallel browser capacity (2–3 concurrent Chromium contexts locally to stay under the 3GB WSL cap). Browser- and flow-level parallelism = multiple flow jobs pulled concurrently up to the prefetch bound. Horizontal scale is deferred to replica count in K8s (Phase 11) — the worker is STATELESS so replicas need no extra design now. Matches the CLAUDE.md "prefetch_count = parallel browser capacity" pattern.
- **D-03a:** The worker reuses the Phase-3 `execution.py` subprocess pytest runner VERBATIM (isolated `uv run pytest`, argv list, no shell, never in-process pytest — the sync-Playwright-in-asyncio deadlock guard). A job = a unit of work off the queue (a flow/spec or a tier shard); the worker runs it as a subprocess. NO LLM call anywhere in the worker (SC3).
- **D-03b:** Memory sequencing under 3GB: the execution stack (RabbitMQ 512m + worker + Chromium contexts + Postgres/Redis) must fit WITHOUT neo4j up (neo4j stays `profiles:[graph]`, off during runs). Tier selection that needs the graph (risk-based reads flow risk) resolves risk BEFORE the run phase, then runs without neo4j — mirrors the Phase-6 codegen→stop-neo4j→run sequencing.

### Artifacts & flaky/retry policy (EXEC-04/05)
- **D-04:** Capture per-step screenshots + Playwright trace + console/network logs on EVERY test; capture video ONLY on failure (disk/memory budget — green-test video is rarely viewed). All artifacts land under `workspaces/<run_id>/...` on the filesystem; only PATHS are recorded in PostgreSQL (no binaries in Postgres — carry-forward rule). (Research: pytest-playwright fixture flags / conftest wiring for per-step screenshots + trace + on-failure video; the exact run-scoped layout.)
- **D-05:** Retry a failed test up to 2× (Playwright/pytest retry). Classification for THIS phase: passes on a retry → flaky (treat as infra flake); fails all attempts → product failure. This is a RETRY classifier only (infra-flake vs product-failure) — full 3-way defect classification + Jira is Phase 9. Flaky status, attempt count, durations, and pass/fail land in the execution-history tables that power trends (EXEC-05).

### Live view, kill switch & CI (EXEC-06/02)
- **D-06:** The live execution view REUSES the Phase-4 Redis pub/sub → SSE seam (`sse-starlette` already a dep; the explorer's progress/SSE pattern). Workers publish per-test progress events (test id, status, attempt, timing) to a Redis channel keyed by run_id; the SSE endpoint re-emits to the browser. Per-test granularity (not per-step in the live view — per-step lives in artifacts/history).
- **D-07:** Kill switch is GRACEFUL via a Redis kill-flag: the API sets `run:{run_id}:kill`; workers check it between tests and DRAIN (finish/abort the current test, pull no new tests), and queued messages for that run are purged. No SIGKILL — avoids orphaned Chromium processes and corrupted partial artifacts.
- **D-08:** CI parity uses the SAME engine: a GitHub Actions workflow calls the platform API to start a tier run and POLLS run status back (pass/fail reported to the Actions run). CI does NOT run pytest directly — a second code path would diverge from the worker engine and break the "identical across local/Docker/CI" determinism goal (SC5). (Research: auth for the CI→API call — a scoped token; how status maps to the Actions check conclusion.)

### Claude's Discretion / for research (--research-phase)
- RabbitMQ topology: exchange/queue/routing design for tier runs + per-run kill drain; `connect_robust`, publisher confirms, QoS prefetch (aio-pika — NOT yet a dep, add per the locked stack).
- The risk-based selection ranking formula (N, risk vs failure-history weighting) and where failure history is sourced.
- pytest-playwright / conftest wiring for per-step screenshots + trace + on-failure video + retries, and the flaky classifier's exact rule + history schema.
- Execution-history data model (runs / test-results / artifacts tables; migration after 0006) + trends/durations/flaky queries.
- The determinism harness (two runs vs a reset target identical) — reuse the SauceDemo reset hook; how to assert identical results deterministically (the Phase-6 planted-spec trick may apply for a keyless proof).
- The GitHub Actions trigger workflow + scoped CI auth token + status mapping.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — EXEC-01..EXEC-06.
- `.planning/ROADMAP.md` (Phase 7 section) — the 5 success criteria (tiered + risk-based suites; local/Docker/CI parity with GH Actions trigger; RabbitMQ-distributed parallel workers, no LLM in the loop; per-step artifacts + history + flaky detection; live view + kill switch + determinism).

### Locked stack & carried conventions
- `CLAUDE.md` — aio-pika 9.6.x (RabbitMQ; `connect_robust`, publisher confirms, prefetch = parallel browser capacity), pytest-xdist, pytest-playwright fixtures (per-worker browser contexts), playwright 1.60 trace/video/screenshot, sse-starlette (live progress), structlog→ES (later), executor image bakes `playwright install --with-deps chromium`, Docker Compose profiles (`queue` profile for rabbitmq). MinIO listed in stack but DEFERRED this phase (ROADMAP SC4 = filesystem + Postgres paths).
- **3GB WSL cap (STATE.md ENVIRONMENT FACTS):** the defining constraint — bounded prefetch, neo4j off during runs, RabbitMQ 512m.

### Reusable seams (read the summaries)
- `.planning/phases/03-tracer-bullet-minimal-end-to-end-loop/03-*-SUMMARY.md` — `execution.py` subprocess pytest runner (`create_subprocess_exec`, argv list, no shell, `_run_cwd`, output cap, run_id-derived spec path, fresh `SessionLocal` in the BackgroundTask) — the worker's run primitive.
- `.planning/phases/04-explorer-agent/04-*-SUMMARY.md` + `apps/api/app/services/explorer/progress.py` + `apps/api/app/routers/explore.py` — the Redis pub/sub → SSE live-view pattern (absolute-value counters, run-scoped channel, auth-gated SSE) — the live execution view + the kill-flag seam.
- `.planning/phases/06-bdd-playwright-generation/06-*-SUMMARY.md` — `stability.py` (N-run subprocess harness, `accept_spec`), `codegen/project.py` (the generated project tree under `workspaces/<run_id>/`, `conftest.py.j2` reading `TARGET_BASE_URL`), the seeded-bug build + reset pattern — feeds what the engine RUNS and the determinism proof.
- `.planning/phases/05-knowledge-graph-flow-learning/05-*-SUMMARY.md` — flow risk scores (the risk-based tier input via `kg/reader`).
- `.planning/phases/01-foundation-dev-environment/01-*-SUMMARY.md` — the SauceDemo reset hook (`infra/scripts/reset_target.py`) for determinism, compose profile conventions, the locked design system the live-view/history UI reuses.

### Known issues / project-wide
- `graph_mode down` leaves neo4j running (manual stop) — relevant: neo4j must be OFF during runs for the 3GB budget.
- Provider keys empty → live generation upstream is Manual-Only; the EXECUTION loop has NO LLM, so the engine + determinism + flaky detection are FULLY deterministic and keyless-testable (with generated specs present). Live end-to-end against a freshly LLM-generated suite is the only Manual-Only slice.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `apps/api/app/services/execution.py` — the subprocess pytest runner; the worker wraps this per job (already battle-tested, Phase 6 reuses it in `stability.py`).
- `apps/api/app/services/explorer/progress.py` + `routers/explore.py` — Redis pub/sub publish + SSE re-emit; the live execution view and kill-flag reuse this exact seam (same lifespan `get_redis()` client).
- `apps/api/app/services/stability.py` — `_run_spec_once` / `run_stability` shape (subprocess discipline, TARGET_BASE_URL override) — directly analogous to a worker job + the determinism harness.
- `apps/api/app/services/codegen/project.py` + templates — the generated project under `workspaces/<run_id>/`; conftest already reads `TARGET_BASE_URL` (env-repointable for Docker/CI parity).
- `apps/api/app/services/run_service.py` + Postgres models + Alembic chain (latest 0006) — new execution/test-result/artifact tables + migration 0007 chains after 0006.
- `infra/docker-compose.yml` — `rabbitmq:4-management` already present under `profiles:[queue]` (512m); the new worker service joins the same profile. SauceDemo + reset hook for determinism.
- `apps/web` shell + Phase-4 live-view + Phase-5/6 table/card patterns + locked design system — the live execution view and execution-history UI.

### Established Patterns
- Subprocess (never in-process) pytest for any run; fresh `SessionLocal` per background task; auth-gated routers; absolute-value Redis progress events on a run-scoped channel; artifacts on the filesystem under `workspaces/<run_id>/` with only paths in Postgres; compose profiles to keep dormant services off (memory).
- Carry forward: NO LLM in the execution loop (hard SC3 invariant — assert no `init_chat_model`/gateway import in worker/execution code); deterministic, keyless-testable engine logic with functional tests under the live stack; the Phase-6 planted-spec trick for a keyless determinism proof.

### Integration Points
- New worker container (compose `queue` profile) consuming RabbitMQ via aio-pika (new dep); the API enqueues tier runs and owns the kill-flag; Redis pub/sub → SSE for live progress; new execution-history models + migration 0007 + execution router(s); per-step artifact capture wired into the generated conftest/templates (extends Phase-6 codegen); a GitHub Actions workflow that triggers the API + reports status; the SauceDemo reset hook for the determinism harness.

</code_context>

<specifics>
## Specific Ideas

- The execution loop is the platform's deterministic core — every gray area resolved toward determinism + the 3GB memory budget (bounded prefetch, neo4j off during runs, graceful drain over SIGKILL, single engine code path for local/Docker/CI).
- Tier composition stays in the user's hands via native Gherkin tags (editable in the existing review queue) rather than an opaque auto-derivation; only risk-based is automatic (and dynamic).
- Video only on failure; everything else (screenshots/trace/logs) always — the evidence the user actually opens, sized for the local disk.
- Kill is graceful (Redis flag + drain + queue purge), never a process kill — no orphaned browsers, no corrupt artifacts.

</specifics>

<deferred>
## Deferred Ideas

- MinIO/S3 artifact store with presigned URLs → later (ROADMAP SC4 mandates filesystem + Postgres paths this phase; MinIO is in the stack table for when artifact volume/sharing demands it).
- Full 3-way failure classification (product / test-bug / infra) + calibrated confidence + Jira filing → Phase 9 (this phase's retry classifier only does infra-flake vs product-failure for retry/flaky purposes).
- Self-healing of failing automation when locators drift → Phase 8.
- Dashboards / RBAC / graph-derived coverage / Elasticsearch-backed execution search → Phase 10 (this phase persists history + exposes a live view + basic execution-history table, not the analytics dashboards).
- K8s manifests + worker autoscaling + Prometheus/Grafana execution metrics + CI/CD for the platform's OWN images → Phase 11 (this phase delivers the stateless worker that scales by replicas later, and the CI trigger that RUNS suites — not the platform build pipeline).

None of these block Phase 7 — discussion stayed within the execution-engine scope.

</deferred>

---

*Phase: 7-execution-engine-workers*
*Context gathered: 2026-06-20*
