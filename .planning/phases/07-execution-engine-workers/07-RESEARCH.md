# Phase 7: Execution Engine & Workers - Research

**Researched:** 2026-06-20
**Domain:** RabbitMQ-distributed Playwright execution (aio-pika workers, pytest-bdd tier selection, per-step artifact capture, flaky-retry classification, graceful kill, determinism)
**Confidence:** HIGH on the reused seams (read from source), HIGH on aio-pika topology shape, MEDIUM on the retry-plugin question (one new-package decision), MEDIUM on risk-based ranking formula (tunable, no canonical reference)

## Summary

Phase 7 turns the Phase-6 generated Playwright project tree (`workspaces/<run_id>/<target>/`) into a run-at-scale execution engine. The genuine new infrastructure is one stateless worker container under the compose `queue` profile that consumes a RabbitMQ queue via **aio-pika 9.6.2** (the one expected new dep — already in the locked CLAUDE.md stack), runs each job as an isolated `uv run pytest` subprocess reusing `execution.py`'s runner verbatim, captures per-step artifacts via pytest-playwright CLI flags, and publishes per-test progress to the **existing Redis pub/sub → SSE seam** (`progress.py` + `routers/explore.py`). Everything in the execution loop is deterministic and keyless-testable — there is NO LLM anywhere — so the engine, capture, flaky classifier, kill drain, and determinism harness are all functionally provable with planted specs and no provider keys. Only a live run against a freshly-LLM-generated suite is Manual-Only.

The single hard external constraint is the **3GB WSL cap**. With neo4j OFF during runs (it stays `profiles:[graph]`), RabbitMQ at 512m, and the existing postgres(512m)+redis(256m)+api(1g)+saucedemo(128m) baseline, the safe worker budget is **prefetch_count=2** Chromium contexts (3 is the documented ceiling, 2 is the safe default). Risk-based tier selection must resolve risk from the graph BEFORE the run phase (mirroring the Phase-6 codegen→stop-neo4j→run sequencing), because the run phase cannot afford neo4j's 1g concurrently with browsers.

The one real package decision: pytest-playwright has **no built-in retry** [VERIFIED: playwright.dev/python/docs/test-runners]. Retries (D-05) therefore come from EITHER `pytest-rerunfailures` (a NEW package — needs a `checkpoint:human-verify`) OR a worker-side retry loop that re-invokes the subprocess up to 2× (zero new package). The zero-new-package path is recommended and is strictly better for the flaky classifier, because the worker observes each attempt's exit code directly and applies the infra-flake-vs-product-failure rule itself.

**Primary recommendation:** Single stateless aio-pika worker, prefetch_count=2, job = one flow/spec (pytest-bdd tag selector per tier resolved at enqueue time), worker-side retry loop (no new pytest plugin), per-step capture via pytest-playwright `--screenshot=on --tracing=on --video=retain-on-failure --output`, progress/kill over the existing Redis seam, new migration 0007 for `test_runs`/`test_results`/`test_artifacts`, determinism proved keyless with the Phase-6 planted-spec trick + `reset_target.py`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Tier → pytest marker selection (EXEC-01) | API / Backend | — | Tier composition (Gherkin tags) is owned data; the API resolves the selector and enqueues jobs |
| Risk-based dynamic tier (D-02) | API / Backend (reads Neo4j + Postgres history) | Knowledge Graph | Risk must resolve BEFORE the run phase while neo4j is up; reads `kg/risk` + EXEC-05 history |
| Job queue + distribution (EXEC-03) | Worker / Queue (RabbitMQ + aio-pika) | API (producer) | The API publishes; the worker consumes; RabbitMQ owns durability + redelivery |
| Subprocess pytest run (D-03a) | Worker | — | Reuses `execution.py` runner verbatim; isolated child process, no in-process pytest |
| Per-step artifact capture (EXEC-04) | Worker (pytest-playwright in the subprocess) | Filesystem (`workspaces/<run_id>/`) | Capture is a pytest-playwright concern; paths land in Postgres |
| Flaky/retry classification (D-05) | Worker (retry loop) | API/Postgres (persists verdict) | Worker observes per-attempt exit codes; classifier is pure code over outcomes |
| Live per-test progress (EXEC-06) | Worker (publish) → API (SSE) → Browser | Redis pub/sub | Reuses the explorer's `progress.py` + SSE seam verbatim |
| Kill switch / drain (D-07) | API (sets Redis flag + purges queue) → Worker (checks flag) | Redis + RabbitMQ | Graceful cooperative cancel; no SIGKILL |
| Execution history + trends (EXEC-05) | API / Backend | Postgres (migration 0007) | New tables; queries power history UI |
| CI trigger (EXEC-02 / D-08) | GitHub Actions → API (start + poll) | — | Single engine code path; CI calls the API, never runs pytest directly |
| Live view + history UI (EXEC-06/05) | Frontend (Next.js) | API (SSE + REST) | Reuses Phase-4 live-view + Phase-5/6 table patterns |

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXEC-01 | Run suites by tier — smoke/sanity/regression/full + risk-based | Tier → pytest-bdd `-m <tag>` selector (D-01); risk-based dynamic ranking formula below (D-02) |
| EXEC-02 | Local/Docker/CI parity + GitHub Actions trigger + status reporting | Single engine code path; GH Actions workflow calls API + polls; conftest reads `TARGET_BASE_URL` for env parity |
| EXEC-03 | Browser- and flow-level parallel RabbitMQ workers | aio-pika single worker, prefetch_count=2, one flow/spec per job; scale by replicas later |
| EXEC-04 | Per-step screenshots/video/console+network logs, paths in Postgres | pytest-playwright `--screenshot/--tracing/--video/--output` flags; `test_artifacts` table |
| EXEC-05 | History with pass/fail trends, durations, flaky detection | Migration 0007 (`test_runs`/`test_results`/`test_artifacts`); retry classifier; trend queries |
| EXEC-06 | Live execution view + kill switch | Redis pub/sub → SSE (existing seam); graceful kill via Redis flag + drain + queue purge |

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Tier membership = native Gherkin tags (`@smoke`/`@sanity`/`@regression`) authored at generation time, editable in the Phase-6 review queue. `full` = every approved/accepted spec. Execution maps a tier to a pytest-bdd marker selector (`pytest -m smoke`). No new column.
- **D-02:** `risk-based` tier is computed DYNAMICALLY at run time — top-N flows by (Phase-5 flow risk score + recent failure history), NOT a stored tier.
- **D-03:** SINGLE dedicated worker container (new compose service under the `queue` profile) consuming the execution queue with `prefetch_count` = parallel browser capacity (2–3 Chromium contexts under the 3GB cap). Stateless; horizontal scale deferred to K8s replicas (Phase 11).
- **D-03a:** Worker reuses the Phase-3 `execution.py` subprocess pytest runner VERBATIM (isolated `uv run pytest`, argv list, no shell, never in-process). A job = a unit of work off the queue. NO LLM call anywhere in the worker (SC3).
- **D-03b:** Execution stack fits WITHOUT neo4j up. Risk-based resolves risk BEFORE the run phase (graph up), then runs without neo4j — mirrors Phase-6 codegen→stop-neo4j→run.
- **D-04:** Capture per-step screenshots + Playwright trace + console/network logs on EVERY test; video ONLY on failure. All artifacts under `workspaces/<run_id>/...`; only PATHS in Postgres (no binaries in Postgres).
- **D-05:** Retry a failed test up to 2×. passes-on-retry → flaky (infra flake); fails-all-attempts → product failure. RETRY classifier only (full 3-way classification is Phase 9). Flaky status, attempt count, durations, pass/fail land in the history tables.
- **D-06:** Live execution view REUSES the Phase-4 Redis pub/sub → SSE seam (`sse-starlette`). Workers publish per-test progress events keyed by run_id; per-test granularity.
- **D-07:** Kill switch is GRACEFUL via a Redis kill-flag (`run:{run_id}:kill`): workers check between tests and DRAIN; queued messages for that run are purged. No SIGKILL.
- **D-08:** CI parity uses the SAME engine — a GitHub Actions workflow calls the platform API to start a tier run and POLLS run status back. CI does NOT run pytest directly.

### Claude's Discretion
- RabbitMQ topology: exchange/queue/routing design + per-run kill drain; `connect_robust`, publisher confirms, QoS prefetch (aio-pika — add per locked stack).
- Risk-based ranking formula (N, risk vs failure-history weighting) and where failure history is sourced.
- pytest-playwright/conftest wiring for per-step screenshots + trace + on-failure video + retries; the flaky classifier's exact rule + history schema.
- Execution-history data model (runs/test-results/artifacts; migration after 0006) + trends/durations/flaky queries.
- Determinism harness (two runs vs a reset target identical) — reuse the SauceDemo reset hook; assert identical results deterministically (Phase-6 planted-spec trick may apply).
- GitHub Actions trigger workflow + scoped CI auth token + status mapping.

### Deferred Ideas (OUT OF SCOPE)
- MinIO/S3 artifact store with presigned URLs → later (ROADMAP SC4 mandates filesystem + Postgres paths this phase).
- Full 3-way failure classification (product/test-bug/infra) + calibrated confidence + Jira → Phase 9.
- Self-healing of failing automation → Phase 8.
- Dashboards / RBAC / graph-derived coverage / Elasticsearch search → Phase 10.
- K8s manifests + worker autoscaling + Prometheus/Grafana + CI/CD for platform images → Phase 11.

## Project Constraints (from CLAUDE.md)

- **Locked stack additions allowed this phase:** aio-pika 9.6.x ONLY. Any other new package (e.g. a pytest retry plugin) must be flagged and gated behind a `checkpoint:human-verify`.
- **No LLM in the execution loop** (SC3): assert no `init_chat_model` / gateway import in worker/execution code. Enforced via an import grep gate, mirroring the Phase-5 single-write-path grep gate.
- **3GB WSL cap** (STATE.md ENVIRONMENT FACTS): bounded prefetch, neo4j off during runs, RabbitMQ 512m.
- **Subprocess (never in-process) pytest** for any run; argv LIST, no `shell=True`; `spec_path` run_id-derived, never raw client input.
- **Fresh `SessionLocal` per background task** (Pitfall 2); never the request's db.
- **Artifacts on the filesystem** under `workspaces/<run_id>/`; only paths in Postgres (carry-forward rule).
- **Compose profiles** keep dormant services off (`queue` profile for rabbitmq + the new worker).
- **uv** for env management; `ruff` lint/format; `mypy`/pyright type checking.
- **API host port is 8001** (container-internal 8000); the GH Actions CI call hits the published host port / a tunnel.
- **gherkin-official is 29.x transitive** via pytest-bdd 8.1 (`>=29,<30`) — never a direct 40.x pin (MEMORY note + STATE.md).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| aio-pika | 9.6.2 | RabbitMQ async client (the worker consumer + API producer) | The decided client; `connect_robust` auto-reconnect, publisher confirms, QoS prefetch — exactly the long-running-consumer needs. In CLAUDE.md locked stack. [VERIFIED: PyPI 2026-06-20] |
| playwright (Python) | 1.60.x | Browser automation in the generated specs | Already a dep; trace/video/screenshot feed the artifact capture |
| pytest-playwright | 0.8.x | Browser fixtures + artifact CLI flags (`--screenshot/--video/--tracing/--output`) | Already a dev dep; the ONLY artifact-capture wiring needed — no new plugin |
| pytest-bdd | 8.1.x | Runs the generated `.feature` files; tag → marker selection (`-m smoke`) | Already a dep; native tier selection (D-01) |
| sse-starlette | 3.4.x | SSE for the live execution view | Already a dep; reused from the explorer live view |
| redis | 8.0.x | pub/sub (progress) + kill-flag + (optional) run-state | Already a dep; `redis.asyncio` built in |
| SQLAlchemy / asyncpg / alembic | 2.0 / 0.31 / 1.18 | Execution-history tables + migration 0007 | Already deps |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | 26.x | Worker structured logs | Already a dep; worker run/job lifecycle logging |
| httpx | 0.28.x | (GH Actions side uses `curl`; API side already has httpx) | The CI workflow calls the API with `curl`/`gh`; no new dep |
| pytest-xdist | (in CLAUDE.md, NOT yet installed) | In-process flow parallelism `-n auto` WITHIN one subprocess | OPTIONAL — see "Parallelism model" below. Prefer queue-level parallelism (prefetch) over xdist to stay under the memory cap. Flag if adopted. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Worker-side retry loop (zero new package) | `pytest-rerunfailures` 16.x | New package → needs `checkpoint:human-verify`. Plugin retries INSIDE one pytest process (one exit code for the whole run) — the worker can't cleanly observe per-attempt outcomes for the flaky classifier. Worker-loop re-invokes the subprocess per attempt and reads each exit code → better fit for D-05. [VERIFIED: PyPI pytest-rerunfailures 16.3 exists] |
| prefetch (queue) parallelism | pytest-xdist `-n auto` | xdist spawns N browser contexts inside ONE subprocess — harder to bound memory and to map per-test progress events to the live view. prefetch=2 with one-flow-per-job gives the same parallelism with cleaner per-test granularity and memory bounding. |
| Filesystem + Postgres paths | MinIO/S3 | DEFERRED this phase (ROADMAP SC4). Do not introduce. |
| Job = one flow/spec | Job = a tier shard | Per-flow jobs give finer parallelism, simpler retry/kill granularity, and 1:1 mapping to per-test live events. Recommended. |

**Installation:**
```bash
# The ONE expected new dep (locked in CLAUDE.md):
uv add aio-pika==9.6.*
# IF retries via plugin is chosen (NOT recommended; needs checkpoint:human-verify):
# uv add --group dev pytest-rerunfailures==16.*
```

**Version verification:** aio-pika 9.6.2 confirmed live on PyPI 2026-06-20 (`pip index versions aio-pika`) — matches the CLAUDE.md pin. pytest-rerunfailures 16.3 confirmed present (only relevant if the plugin path is chosen).

## Package Legitimacy Audit

> aio-pika is the only new runtime dep. slopcheck was not run in this session (offline); aio-pika is an established, long-lived package explicitly named in the locked CLAUDE.md stack and verified on PyPI, so it is treated as approved. The planner SHOULD still gate the install behind the standard verification per project policy.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| aio-pika | PyPI | ~9 yrs (since 2016) | very high (millions/mo) | github.com/mosquito/aio-pika | not run (offline) | Approved — locked stack, PyPI-verified 9.6.2 |
| pytest-rerunfailures | PyPI | ~13 yrs | high | github.com/pytest-dev/pytest-rerunfailures | not run (offline) | CONDITIONAL — only if plugin retry path chosen; NEW package → `checkpoint:human-verify` required |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*slopcheck unavailable at research time: per protocol, the planner should gate the aio-pika install behind a verification step. aio-pika's presence in the locked stack + live PyPI confirmation substantially de-risks it.*

## Architecture Patterns

### System Architecture Diagram

```
                        ┌─────────────────────────────────────────────┐
   POST /api/execute    │                  API (FastAPI)               │
   {tier, run_id?}  ──► │                                              │
                        │  1. resolve tier:                            │
                        │     - tag tiers (D-01): selector = "-m smoke"│
   GET /executions/...  │     - risk-based (D-02): read kg/risk +      │
   (poll status)    ◄───│       EXEC-05 failure history → top-N flows  │  ◄── Neo4j (UP only for
                        │       [BEFORE run phase, neo4j up]           │       risk resolution]
   GET .../events (SSE) │  2. create test_run row (Postgres)          │
        ▲               │  3. enqueue per-flow JOBS ─────────┐         │
        │               │  4. owns kill-flag + queue purge   │         │
        │               └────────────────────────────────────┼─────────┘
        │                                                     │ publish (persistent,
        │                                                     │ publisher-confirm)
        │ re-emit                                             ▼
        │                                          ┌──────────────────────┐
        │                                          │ RabbitMQ (queue prof, │
        │                                          │ 512m) durable queue   │
        │                                          │  exec.jobs            │
        │                                          └──────────┬───────────┘
        │                                                     │ prefetch_count=2
        │           Redis pub/sub                             ▼
   ┌────┴───────┐   exec:{run_id}        ┌──────────────────────────────────────┐
   │  Browser   │◄──────────────────────│  WORKER container (queue profile)       │
   │ live view  │   per-test events     │  - aio-pika connect_robust consumer     │
   │ + kill btn │                       │  - per job: check kill-flag → run        │
   └────────────┘                       │    `uv run pytest <flow spec> \          │
                                        │      --screenshot=on --tracing=on \      │
   set run:{id}:kill ──────────────────│      --video=retain-on-failure --output` │
   (graceful drain)                     │    (execution.py runner VERBATIM)        │
                                        │  - retry loop up to 2× → flaky classifier│
                                        │  - publish per-test progress (Redis)     │
                                        │  - write test_results + test_artifacts   │──► Postgres
                                        │  - NO LLM ANYWHERE                        │      (paths only)
                                        └──────────────────────┬───────────────────┘
                                                               │ artifacts (binaries)
                                                               ▼
                                                  workspaces/<run_id>/... (filesystem)

   GitHub Actions ──(curl, CI token)──► POST /api/execute ──► poll GET status ──► check conclusion
```

### Recommended Project Structure
```
apps/api/app/
├── services/
│   ├── execution.py            # REUSED verbatim (the subprocess runner primitive)
│   ├── worker/
│   │   ├── __init__.py
│   │   ├── consumer.py         # aio-pika connect_robust, set_qos, queue.iterator() loop
│   │   ├── job.py              # run one flow job: kill-check → subprocess → retry loop → persist
│   │   ├── classifier.py       # PURE flaky-vs-product rule (no I/O) — table-testable
│   │   └── progress.py         # per-test event builder + publish (mirrors explorer/progress.py)
│   ├── exec_service.py         # tier resolution, risk ranking, enqueue, kill+purge
│   └── exec_history.py         # trends / durations / flaky queries
├── routers/
│   └── execute.py             # POST /execute, GET status, GET .../events (SSE), POST .../kill
├── models/
│   └── execution_history.py   # TestRun / TestResult / TestArtifact ORM
└── alembic/versions/
    └── 0007_execution_history.py
apps/api/app/worker_main.py     # worker container entrypoint (runs the consumer loop)
infra/docker-compose.yml        # + worker service under profiles:[queue]
.github/workflows/run-suite.yml # CI trigger
```

### Pattern 1: aio-pika robust consumer with bounded prefetch
**What:** A single worker connects with `connect_robust` (auto-reconnect + state recovery), sets QoS prefetch to bound concurrent in-flight jobs to browser capacity, and consumes via the async iterator with per-message `process()` (auto ack on success / requeue on exception).
**When to use:** The worker container's main loop.
**Example:**
```python
# Source: aio-pika docs (docs.aio-pika.com) — 9.x API [CITED: docs.aio-pika.com]
import aio_pika

async def run_worker(amqp_url: str, prefetch: int = 2) -> None:
    connection = await aio_pika.connect_robust(amqp_url)        # auto-reconnect + recovery
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=prefetch)         # = parallel browser capacity (2)
        queue = await channel.declare_queue("exec.jobs", durable=True)
        async with queue.iterator() as it:
            async for message in it:
                # process(): ack on clean exit; on exception the message is requeued/nacked.
                # requeue=False on a poison message would dead-letter instead of looping.
                async with message.process(requeue=True):
                    job = json.loads(message.body)
                    await run_flow_job(job)                     # subprocess + retry + persist
```
**Memory note:** prefetch_count=2 means at most 2 jobs in flight → at most 2 Chromium contexts. This is the SAFE default under the 3GB cap. 3 is the documented ceiling — only with neo4j confirmed down and headroom measured.

### Pattern 2: Producer with publisher confirms + persistent messages
**What:** The API publishes one durable, persistent message per flow job; publisher confirms guarantee the broker accepted it before the API reports the run as enqueued.
**Example:**
```python
# Source: aio-pika docs — 9.x API [CITED: docs.aio-pika.com]
import aio_pika
from aio_pika import Message, DeliveryMode

async def enqueue_jobs(amqp_url: str, run_id: str, jobs: list[dict]) -> None:
    connection = await aio_pika.connect_robust(amqp_url)
    async with connection:
        # publisher_confirms=True is the default for channels in aio-pika 9.x;
        # default_exchange.publish awaits the broker's confirm.
        channel = await connection.channel()
        await channel.declare_queue("exec.jobs", durable=True)
        for job in jobs:
            body = json.dumps({**job, "run_id": run_id}).encode()
            await channel.default_exchange.publish(
                Message(body, delivery_mode=DeliveryMode.PERSISTENT),
                routing_key="exec.jobs",
            )
```

### Pattern 3: Per-run graceful kill (Redis flag + drain + queue purge)
**What:** Kill is cooperative. The API sets a Redis flag; the worker checks it BEFORE pulling/running each job and drains; the API purges queued messages for the run. No SIGKILL — avoids orphaned Chromium + corrupt partial artifacts (D-07).
**Example:**
```python
# API side — set flag, then purge the queue of this run's pending jobs.
async def kill_run(run_id: str) -> None:
    await get_redis().set(f"run:{run_id}:kill", "1")            # worker checks this between tests
    connection = await aio_pika.connect_robust(settings.amqp_url)
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue("exec.jobs", durable=True)
        await queue.purge()   # purge pending; in-flight jobs drain via the flag check

# Worker side — check between tests (mirrors explorer check_cancel at loop-top).
async def run_flow_job(job: dict) -> None:
    run_id = job["run_id"]
    if await get_redis().get(f"run:{run_id}:kill"):
        await publish_progress(run_id, _killed_event(job))     # mark this test skipped/aborted
        return                                                 # pull no new work for this run
    ...
```
**Note on purge granularity:** `queue.purge()` purges the WHOLE queue. With a single worker and one run at a time this is fine. If concurrent runs ever share one queue, switch to per-run queues (`exec.jobs.{run_id}`) so a purge is run-scoped — flag this as a forward design note, not a Phase-7 requirement.

### Pattern 4: Per-step artifact capture via pytest-playwright CLI flags
**What:** The worker invokes the subprocess with the pytest-playwright artifact flags. screenshots + trace ALWAYS; video ONLY on failure (D-04). No new plugin.
**Example:**
```python
# Worker subprocess argv (extends execution.py's argv list — same discipline, no shell).
# [VERIFIED: playwright.dev/python/docs/test-runners — flag names + accepted values]
argv = [
    "uv", "run", "pytest", spec_path, "-q",
    "--screenshot=on",            # on | off | only-on-failure  → ALWAYS (D-04)
    "--tracing=on",               # on | off | retain-on-failure → ALWAYS (trace = console+network)
    "--video=retain-on-failure",  # on | off | retain-on-failure → video ON FAILURE ONLY (D-04)
    "--output", str(run_artifacts_dir),   # artifacts under workspaces/<run_id>/...
]
```
**Console/network logs:** The Playwright **trace** (`--tracing`) already captures console messages and network requests/responses and is viewable in the trace viewer — so "console/network logs always" is satisfied by `--tracing=on` (no separate log-capture wiring needed). If a plain-text console log is also wanted, add a `page.on("console", ...)` / `page.on("requestfinished", ...)` hook in the generated conftest writing to `console.log`/`network.log` under the run dir — extends `conftest.py.j2`. [CITED: playwright.dev/python/docs/trace-viewer]

### Pattern 5: Tier → pytest-bdd selector (D-01)
**What:** Gherkin `@smoke`/`@sanity`/`@regression` tags become pytest markers; pytest-bdd applies them so `-m smoke` selects only `@smoke` scenarios. `full` runs everything; risk-based selects specific flow specs.
**How:** pytest-bdd converts Gherkin tags to pytest markers automatically. The tier→argv mapping:
```python
TIER_SELECTOR = {
    "smoke":      ["-m", "smoke"],
    "sanity":     ["-m", "sanity"],
    "regression": ["-m", "regression"],
    "full":       [],                       # no marker filter → all approved specs
    # risk-based: no -m; enqueue ONLY the chosen flows' spec paths (resolved from risk)
}
```
**Important:** pytest-bdd requires the markers be registered (in `pyproject.toml [tool.pytest.ini_options] markers`) OR `--strict-markers` will warn/error. The GENERATED project's pytest config (or conftest) must register `smoke`/`sanity`/`regression`. This is a small codegen extension to the Phase-6 project tree. [CITED: pytest-bdd.readthedocs.io — "Organizing your scenarios" / tags-as-markers]

### Pattern 6: Risk-based dynamic tier ranking (D-02)
**What:** At run time (neo4j UP, BEFORE the run phase), rank flows by a combined score and take the top-N. Reuses the existing PURE `kg/risk.risk_score` (already 0–100, deterministic) and reads failure history from the new EXEC-05 tables.
**Recommended formula (tunable starting point — frozen weights, mirroring `RiskWeights`):**
```python
# combined = risk_weight * risk_score(flow)  +  failure_weight * failure_rate(flow) * 100
# failure_rate(flow) = recent_failures / recent_runs over the last K runs (0..1) from test_results.
RISK_WEIGHT = 0.6        # graph-derived structural risk (kg/risk.risk_score, 0..100)
FAILURE_WEIGHT = 0.4     # empirical recent failure signal (history, normalized 0..100)
TOP_N = 10               # cap the risk-based suite size (tunable; bounds run time + memory)
```
**Where failure history is read:** the EXEC-05 `test_results` table — `failure_rate = failed_attempts / total_runs` per flow over the last K test_runs (K≈10). Before any history exists, failure_weight contributes 0 and the tier is pure structural risk (graceful cold-start).
**Confidence:** MEDIUM — the 0.6/0.4 split and N=10 are tunable starting points with no canonical reference (same posture as `RiskWeights` in `kg/risk.py`); the SHAPE (weighted sum of structural risk + recent failure rate, top-N) is HIGH confidence. Tag the exact weights `[ASSUMED]` for the planner to surface.

### Anti-Patterns to Avoid
- **In-process pytest in the worker:** a sync-Playwright call inside the asyncio worker process deadlocks/crashes (the Phase-3 Pitfall 3 invariant). ALWAYS subprocess.
- **SIGKILL the worker/browser to stop a run:** orphans Chromium processes + leaves corrupt partial artifacts. Use the cooperative Redis flag + drain (D-07).
- **Storing artifact binaries in Postgres:** carry-forward rule violation. Filesystem + paths only.
- **neo4j up during the run phase:** the 1g neo4j + 2 Chromium contexts overruns the 3GB cap. Resolve risk first, then stop neo4j.
- **xdist inside the subprocess AND high prefetch:** multiplies browser contexts → OOM. Pick ONE parallelism axis (prefetch), keep it bounded.
- **A second Redis client:** reuse the lifespan `get_redis()` (PITFALLS memory note from Phase 4).
- **LLM/gateway import in worker code:** violates SC3. Enforce with an import grep gate.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Reliable queue consumption + reconnect | Custom AMQP socket loop | aio-pika `connect_robust` + `queue.iterator()` | Auto-reconnect, state recovery, ack/nack semantics are subtle |
| Browser artifact capture | Manual screenshot/video/trace calls everywhere | pytest-playwright `--screenshot/--video/--tracing` | Per-test lifecycle, on-failure conditionals, output layout handled |
| Console/network log capture | Custom CDP log scraping | Playwright trace (`--tracing`) | Trace viewer already records console + network |
| Live progress fan-out | New WebSocket server | Existing Redis pub/sub → sse-starlette seam | `progress.py` + `routers/explore.py` already do this; reuse verbatim |
| Subprocess run discipline | New runner | `execution.py` `run_execution` / `stability._run_spec_once` | Battle-tested argv-list, no-shell, output-cap, fresh-session shape |
| Target reset for determinism | New reset script | `infra/scripts/reset_target.py` | Generic name→strategy contract, exit-code contract Phase 7 consumes |
| Flow risk number | New risk model | `kg/risk.risk_score` (pure, 0–100) | Deterministic, auditable, free, already shipped |

**Key insight:** Phase 7 is overwhelmingly an ASSEMBLY phase. The only genuinely new code is the aio-pika consumer/producer wiring, the per-flow job runner (a thin wrapper over `execution.py`), the pure flaky classifier, the history tables/queries, and the GH Actions workflow. Almost everything else is reuse.

## Common Pitfalls

### Pitfall 1: OOM under the 3GB cap from too many browsers
**What goes wrong:** prefetch_count too high, or neo4j left running, OOM-kills the WSL VM mid-run (the 16GB template wedge precedent in STATE.md).
**Why:** baseline postgres(512)+redis(256)+api(1g)+saucedemo(128)+rabbitmq(512) ≈ 2.4GB leaves ~600MB for the worker + browsers. Each Chromium context is ~150–300MB.
**How to avoid:** prefetch_count=2 (safe), neo4j OFF during the run phase, worker `mem_limit` set (~512m–768m), risk resolved before stopping neo4j.
**Warning signs:** worker container killed (exit 137), API loses RabbitMQ connection, WSL VM restart.

### Pitfall 2: Risk-based tier needs neo4j but the run phase can't afford it
**What goes wrong:** Resolving risk reads Neo4j; running needs browsers; both up at once OOMs.
**How to avoid:** D-03b sequencing — resolve+rank flows WHILE neo4j is up, materialize the chosen flow list (spec paths), THEN stop neo4j and enqueue/run. The Phase-6 codegen→stop-neo4j→run sequencing is the exact precedent.
**Warning signs:** risk-based runs OOM where tag-tier runs succeed.

### Pitfall 3: pytest-bdd markers not registered → tier selection silently empty/erroring
**What goes wrong:** `-m smoke` against a project whose `smoke` marker isn't registered warns (or errors under `--strict-markers`), or selects nothing.
**How to avoid:** The generated project must register `smoke`/`sanity`/`regression` markers (codegen extension to the Phase-6 tree config/conftest). Verify a tag-selected run actually runs the tagged scenarios.
**Warning signs:** "0 selected" or PytestUnknownMarkWarning.

### Pitfall 4: Flaky classifier conflates flake with product failure
**What goes wrong:** A test that fails then passes is product-broken-but-lucky, or vice versa.
**How to avoid:** Apply D-05 strictly: ANY attempt passes within the 2-retry budget → flaky(infra); ALL attempts fail → product failure. Record attempt_count + each attempt's exit code so the verdict is auditable. The classifier is PURE (no I/O) and table-testable.
**Warning signs:** flaky-rate inexplicably high/low; verdicts not reproducible from recorded attempts.

### Pitfall 5: Kill leaves orphaned Chromium / corrupt artifacts
**What goes wrong:** Force-killing the worker mid-test orphans the browser subprocess and leaves a half-written trace/video.
**How to avoid:** Cooperative flag check between tests + queue purge (D-07); let the in-flight subprocess finish or abort cleanly. Never SIGKILL.
**Warning signs:** lingering chromium processes after a kill; unreadable trace zips.

### Pitfall 6: Non-determinism breaks the two-runs-identical proof
**What goes wrong:** Timestamps, random data, or target state drift make two runs differ.
**How to avoid:** Reset the target between runs (`reset_target.py saucedemo`); compare on STATUS + flaky verdict, NOT timing/timestamps; use the Phase-6 planted-spec trick for a keyless deterministic proof. SauceDemo state lives in browser localStorage so fresh Playwright contexts already isolate runs (reset_target.py honesty note).
**Warning signs:** the determinism functional test flakes.

### Pitfall 7: CI token leaks or over-scopes
**What goes wrong:** A full-privilege JWT in GH Actions secrets, or a token in logs.
**How to avoid:** A scoped CI credential (a dedicated service account / a narrowly-scoped JWT that can only start runs + read status). Pass via GH Actions secret, never echo it. Mirror PLAT-07 credential discipline.
**Warning signs:** token visible in workflow logs; CI can do more than start/poll.

## Runtime State Inventory

> Phase 7 is greenfield feature work (new worker + new tables + new routes), not a rename/refactor. This section is included only to confirm no hidden runtime state is being mutated.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | New Postgres tables (test_runs/test_results/test_artifacts) via migration 0007; no existing data renamed | migration only |
| Live service config | RabbitMQ `exec.jobs` durable queue created at runtime (not in git); worker service added to compose `queue` profile | compose edit + runtime declare |
| OS-registered state | None — worker is a container, no OS-level registrations | None |
| Secrets/env vars | New: `AMQP_URL` (worker+api), `CI_*` token for GH Actions. No existing secret renamed | add to .env / GH secrets |
| Build artifacts | Worker reuses the api image (same `uv` project) OR a thin image baking `playwright install --with-deps chromium`; no stale artifacts | dockerfile/compose |

**Nothing found that mutates existing runtime state** — verified by reading the existing models, compose, and services.

## Code Examples

### The flaky classifier (PURE — table-testable, no I/O)
```python
# app/services/worker/classifier.py — D-05. NO LLM, NO I/O.
def classify_retry(attempt_exit_codes: list[int]) -> dict:
    """Infra-flake vs product-failure from the retry-loop outcomes (D-05).

    passed at any attempt (exit 0) within the budget -> flaky (infra flake).
    all attempts failed -> product failure.
    """
    passed = any(code == 0 for code in attempt_exit_codes)
    final_passed = attempt_exit_codes[-1] == 0
    retried = len(attempt_exit_codes) > 1
    if passed:
        # passed at least once; if it needed a retry to pass it's flaky.
        verdict = "flaky" if retried else "passed"
    else:
        verdict = "product_failure"
    return {
        "verdict": verdict,
        "attempts": len(attempt_exit_codes),
        "passed": passed,
        "final_passed": final_passed,
        "exit_codes": attempt_exit_codes,
    }
```

### The worker job: kill-check → subprocess retry loop → classify → persist
```python
# app/services/worker/job.py — reuses execution.py subprocess shape verbatim.
async def run_flow_job(job: dict) -> None:
    run_id, flow_id, spec_path = job["run_id"], job["flow_id"], job["spec_path"]
    if await get_redis().get(f"run:{run_id}:kill"):
        await publish_test_event(run_id, flow_id, status="aborted", attempt=0)
        return
    exit_codes: list[int] = []
    MAX_ATTEMPTS = 3  # original + up to 2 retries (D-05)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if await get_redis().get(f"run:{run_id}:kill"):
            break
        await publish_test_event(run_id, flow_id, status="running", attempt=attempt)
        result = await _run_spec_with_capture(spec_path, run_id)   # uv run pytest + artifact flags
        exit_codes.append(result["exit_code"] if result["exit_code"] is not None else 1)
        if result["exit_code"] == 0:
            break                                                  # passed → stop retrying
    verdict = classify_retry(exit_codes)                           # pure classifier
    async with SessionLocal() as db:                               # FRESH session (Pitfall 2)
        await exec_history.record_result(db, run_id, flow_id, verdict, artifact_paths=...)
    await publish_test_event(run_id, flow_id, status=verdict["verdict"], attempt=len(exit_codes))
```

### Per-test progress event (mirrors explorer/progress.py)
```python
# app/services/worker/progress.py — reuses the lifespan get_redis() client (no 2nd client).
async def publish_test_event(run_id: str, flow_id: str, *, status: str, attempt: int,
                             duration_s: float = 0.0) -> None:
    event = {"run_id": run_id, "flow_id": flow_id, "status": status,
             "attempt": attempt, "duration_s": duration_s}
    await get_redis().publish(f"exec:{run_id}", json.dumps(event))
```

### GitHub Actions trigger (calls the API, polls status, maps to conclusion)
```yaml
# .github/workflows/run-suite.yml — D-08. Single engine code path; CI never runs pytest.
name: run-suite
on: { workflow_dispatch: { inputs: { tier: { default: smoke } } } }
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - name: Start tier run
        id: start
        run: |
          RUN_ID=$(curl -fsS -X POST "$API_URL/api/execute" \
            -H "Authorization: Bearer $CI_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"tier\":\"${{ inputs.tier }}\"}" | jq -r .run_id)
          echo "run_id=$RUN_ID" >> "$GITHUB_OUTPUT"
        env: { API_URL: ${{ secrets.PLATFORM_API_URL }}, CI_TOKEN: ${{ secrets.CI_TOKEN }} }
      - name: Poll until terminal
        run: |
          for i in $(seq 1 120); do
            S=$(curl -fsS "$API_URL/api/executions/${{ steps.start.outputs.run_id }}" \
              -H "Authorization: Bearer $CI_TOKEN" | jq -r .status)
            [ "$S" = "passed" ] && exit 0
            [ "$S" = "failed" ] && exit 1
            sleep 10
          done
          echo "timed out"; exit 1
        env: { API_URL: ${{ secrets.PLATFORM_API_URL }}, CI_TOKEN: ${{ secrets.CI_TOKEN }} }
```
A failed `exit 1` maps to the GitHub check conclusion `failure`; `exit 0` → `success`. The platform API must be reachable from GitHub runners (a tunnel/ngrok or self-hosted runner on the dev box — note that host port 8001 is local; document the reachability assumption).

## Execution-History Data Model (migration 0007, chains after 0006)

```python
# 0007_execution_history.py — APP TABLES ONLY (LangGraph checkpoint tables stay self-owned).
# test_runs: one row per tier run.
test_runs(
    id PK, run_id str(64) UNIQUE indexed, tier str(16), selector str(64) null,
    status str(16) default 'queued',         # queued|running|passed|failed|killed
    total int default 0, passed int default 0, failed int default 0, flaky int default 0,
    started_at, finished_at null, created_at,
)
# test_results: one row per flow per run (after the retry loop resolves).
test_results(
    id PK, run_id str(64) indexed, flow_id str(255) indexed,
    verdict str(16),                          # passed|flaky|product_failure|aborted
    attempts int, exit_codes JSON, duration_ms int null, created_at,
)
# test_artifacts: one row per captured artifact (PATHS only — no binaries).
test_artifacts(
    id PK, run_id str(64) indexed, flow_id str(255) indexed,
    kind str(16),                             # screenshot|trace|video|console_log|network_log
    path str(1024),                           # relative to workspaces/<run_id>/
    created_at,
)
```
**Trend / duration / flaky queries (the EXEC-05 surface):**
- Pass-rate trend: `SELECT date_trunc('day', started_at), sum(passed)::float/sum(total) FROM test_runs GROUP BY 1 ORDER BY 1`
- Durations: `SELECT flow_id, avg(duration_ms), max(duration_ms) FROM test_results GROUP BY flow_id`
- Flaky leaderboard: `SELECT flow_id, count(*) FROM test_results WHERE verdict='flaky' GROUP BY flow_id ORDER BY 2 DESC`
- Failure history (for risk-based, last K runs): `SELECT flow_id, sum(CASE WHEN verdict='product_failure' THEN 1 ELSE 0 END)::float/count(*) FROM test_results WHERE run_id IN (<last K run_ids>) GROUP BY flow_id`

## Parallelism Model (reconciling browser + flow parallelism under the cap)

**Job granularity:** one message = one flow/spec (D-03a "a unit of work"). This is the recommended granularity.
- **Flow-level parallelism (SC3):** prefetch_count=2 → the worker pulls up to 2 flow jobs concurrently → 2 flows run in parallel.
- **Browser-level parallelism:** each flow job is its own subprocess with its own Playwright browser context → the 2 concurrent jobs ARE 2 concurrent browsers. Browser + flow parallelism collapse to the SAME axis under the single-worker model, which is exactly right for the memory budget.
- **Why not xdist:** xdist would add a SECOND parallelism axis inside each subprocess (N contexts × prefetch jobs) — uncontrollable memory, and per-worker xdist output is harder to map to per-test live events. Keep ONE axis (prefetch). Scale later by adding worker REPLICAS (stateless — D-03), not by raising prefetch or adding xdist.
- **Tag tiers vs risk-based enqueue:** for tag tiers, enqueue one job per approved flow whose scenario carries the tag (the API filters by tag at enqueue time, OR enqueues a single `-m <tag>` job per run if per-flow granularity isn't needed — per-flow is preferred for live granularity + retry/kill scope). For risk-based, enqueue exactly the top-N chosen flows' spec paths.

## Memory Budget Math (the 3GB cap)

| Component | mem_limit | Up during run phase? |
|-----------|-----------|----------------------|
| postgres | 512m | yes |
| redis | 256m | yes |
| api | 1g | yes |
| saucedemo (target) | 128m | yes |
| rabbitmq | 512m | yes |
| **subtotal** | **~2.4g** | |
| worker container (recommend mem_limit ~512–768m incl. 2 Chromium contexts) | ~600m | yes |
| **run-phase total** | **~3.0g** | TIGHT — neo4j MUST be off |
| neo4j | 1g | **NO** — risk resolved before run phase, then stopped |

**Safe prefetch_count = 2.** 3 is the documented ceiling and only if measured headroom exists with the web tier (1.5g) also stopped during a run. **Sequencing:** (1) if risk-based, start neo4j (graph_mode stops web first), resolve+rank flows, materialize spec list; (2) stop neo4j; (3) start the `queue` profile (rabbitmq + worker); (4) enqueue + run. This mirrors the Phase-6 codegen→stop-neo4j→run pattern exactly.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| aioredis | `redis.asyncio` (built in) | merged into redis-py | Use the existing `get_redis()` — no aioredis |
| Celery for async work | aio-pika consumers in worker containers | project decision (CLAUDE.md) | No Celery; aio-pika direct |
| In-process pytest.main | isolated `uv run pytest` subprocess | Phase 3 invariant | Sync-Playwright-in-asyncio deadlock guard |

**Deprecated/outdated:**
- gherkin-official 40.x as a direct pin: incompatible with pytest-bdd 8.1 (`>=29,<30`) — irrelevant here (no Gherkin generation) but do not re-introduce.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Risk-based weights RISK_WEIGHT=0.6 / FAILURE_WEIGHT=0.4, TOP_N=10 | Pattern 6 | Tier picks the wrong flows; tunable, low blast radius (user can adjust like RiskWeights) |
| A2 | aio-pika 9.x `channel` defaults to publisher_confirms=True | Pattern 2 | If not default, must pass explicitly; verify against installed version's docs |
| A3 | `--tracing=on` fully satisfies "console/network logs always" | Pattern 4 | If a plain-text log is required separately, add conftest `page.on` hooks |
| A4 | safe prefetch_count=2 under the 3GB cap | Memory math | If OOM at 2, drop to 1 (serial); measure with `docker stats` during the first run |
| A5 | GH runners can reach the platform API (tunnel/self-hosted runner) | GH Actions example | If unreachable, CI trigger needs a self-hosted runner on the dev box |
| A6 | One run at a time → whole-queue purge is safe for kill | Pattern 3 | Concurrent runs need per-run queues (`exec.jobs.{run_id}`) |
| A7 | Worker shares the api image (same uv project + baked chromium) | Project structure | If a separate image, add a worker Dockerfile baking `playwright install --with-deps chromium` |

## Open Questions

1. **Worker image: reuse api image or a dedicated worker image?**
   - What we know: the api image already bakes `playwright install --with-deps chromium` (Phase 3) and is the same uv project.
   - What's unclear: whether to run the worker from the same image with a different entrypoint (`python -m app.worker_main`) or a slimmer dedicated image.
   - Recommendation: reuse the api image with a different `command:` in compose — fastest, no duplicate browser-baking, and the worker shares all services/models. Revisit for K8s.

2. **Exact CI reachability mechanism (A5).**
   - What we know: host port 8001 is local; GH-hosted runners are external.
   - Recommendation: document a self-hosted runner on the dev box (simplest, no tunnel/secret-exposure) as the default; ngrok/cloudflared tunnel as an alternative. This is a deployment detail, not engine code.

3. **Per-flow enqueue vs single `-m tag` job for tag tiers.**
   - What we know: per-flow gives finer live granularity + retry/kill scope; single-job is simpler.
   - Recommendation: per-flow enqueue for ALL tiers (uniform engine path; live view + flaky classifier are naturally per-flow). The API resolves which approved flows carry the tag.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| RabbitMQ (rabbitmq:4-management) | EXEC-03 worker queue | ✓ (compose `queue` profile, 512m) | 4.x | none — required |
| aio-pika | worker/producer | ✗ (not yet installed) | 9.6.2 on PyPI | none — the one expected new dep |
| Redis | progress + kill flag | ✓ (running) | 8.x | none |
| Postgres | history tables | ✓ (running) | 17 | none |
| Chromium (baked in api image) | execution | ✓ (Phase 3 `playwright install --with-deps`) | 1.60 | none |
| Neo4j | risk-based tier resolution ONLY | ✓ (graph profile; off during runs) | 2025 | tag tiers don't need it |
| `uv` runner | subprocess pytest | ✓ (Phase 3) | — | none |
| GH Actions runner reachable to API | EXEC-02 CI trigger | ✗ (host port 8001 is local) | — | self-hosted runner / tunnel (A5) |

**Missing dependencies with no fallback:**
- aio-pika (install per locked stack — the expected new dep).

**Missing dependencies with fallback:**
- GH-hosted runner reachability → self-hosted runner on the dev box.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.x (+ pytest-asyncio 1.4 auto mode, pytest-playwright 0.8) |
| Config file | `apps/api/pyproject.toml` `[tool.pytest.ini_options]` (markers: functional, e2e, live_llm, graph) |
| Quick run command | `cd apps/api && uv run pytest tests/unit -q` |
| Full suite command | `cd apps/api && uv run pytest -q` (functional needs the live stack with the `queue` profile) |

### The deterministic-vs-Manual split (make this explicit for VALIDATION)
- **FULLY deterministic + keyless** (NO LLM in the execution loop): the aio-pika topology, the per-flow job runner, the retry loop, the flaky classifier, artifact capture, the kill drain + purge, history persistence + queries, the risk ranking math, and the determinism harness. ALL provable with PLANTED specs and NO provider keys (the Phase-6 planted-spec trick).
- **Manual-Only** (needs provider keys): a live end-to-end run against a freshly LLM-GENERATED suite. ONE slice only.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXEC-01 | tag tier → correct pytest-bdd selector; risk ranking math | unit | `uv run pytest tests/unit/test_exec_tiers.py tests/unit/test_risk_ranking.py -q` | ❌ Wave 0 |
| EXEC-01 | risk-based picks top-N flows from risk+history | unit | `uv run pytest tests/unit/test_risk_ranking.py -q` | ❌ Wave 0 |
| EXEC-02 | tier run starts via API + polls to terminal (same engine) | functional | `uv run pytest tests/functional/test_execute_tier.py -m functional -q` | ❌ Wave 0 |
| EXEC-02 | GH Actions workflow yaml lints + maps exit→conclusion | unit (yaml/contract) | `uv run pytest tests/unit/test_ci_workflow_contract.py -q` | ❌ Wave 0 |
| EXEC-03 | worker consumes a queued job + runs the subprocess; prefetch bound honored | functional | `uv run pytest tests/functional/test_worker_consume.py -m functional -q` | ❌ Wave 0 |
| EXEC-03 | NO-LLM import gate (no init_chat_model/gateway in worker) | unit (grep gate) | `uv run pytest tests/unit/test_no_llm_in_worker.py -q` | ❌ Wave 0 |
| EXEC-04 | planted spec run produces screenshot+trace always, video on failure; paths in Postgres | functional | `uv run pytest tests/functional/test_artifact_capture.py -m functional -q` | ❌ Wave 0 |
| EXEC-05 | flaky classifier table tests (pass/flaky/product) | unit | `uv run pytest tests/unit/test_flaky_classifier.py -q` | ❌ Wave 0 |
| EXEC-05 | history persistence + trend/flaky queries | functional | `uv run pytest tests/functional/test_exec_history.py -m functional -q` | ❌ Wave 0 |
| EXEC-06 | per-test events publish to Redis; SSE re-emits; snapshot on reconnect | functional + e2e | `uv run pytest tests/functional/test_live_exec.py -m functional -q` | ❌ Wave 0 |
| EXEC-06 | kill flag drains + purges; no SIGKILL; no orphaned process | functional | `uv run pytest tests/functional/test_kill_drain.py -m functional -q` | ❌ Wave 0 |
| Determinism | two runs vs reset target identical (planted spec, keyless) | functional | `uv run pytest tests/functional/test_determinism.py -m functional -q` | ❌ Wave 0 |
| Manual | live LLM-generated suite end-to-end | manual | (documented manual steps; needs provider key) | n/a |

### Sampling Rate
- **Per task commit:** `cd apps/api && uv run pytest tests/unit -q` (fast, keyless, no stack)
- **Per wave merge:** `cd apps/api && uv run pytest -q` (unit + functional; functional needs the live stack with `queue` profile + a planted spec, neo4j off)
- **Phase gate:** full suite green (unit + functional) before `/gsd:verify-work`; the determinism functional test green; the NO-LLM gate green.

### Wave 0 Gaps
- [ ] `tests/unit/test_flaky_classifier.py` — covers EXEC-05 (pure classifier table tests)
- [ ] `tests/unit/test_risk_ranking.py` — covers EXEC-01 (risk+history ranking, cold-start)
- [ ] `tests/unit/test_exec_tiers.py` — covers EXEC-01 (tier→selector map)
- [ ] `tests/unit/test_no_llm_in_worker.py` — SC3 import grep gate
- [ ] `tests/unit/test_ci_workflow_contract.py` — EXEC-02 (yaml parse + exit→conclusion)
- [ ] `tests/functional/test_worker_consume.py` — EXEC-03 (consume + subprocess + prefetch)
- [ ] `tests/functional/test_artifact_capture.py` — EXEC-04 (planted spec artifacts + Postgres paths)
- [ ] `tests/functional/test_exec_history.py` — EXEC-05 (persistence + queries)
- [ ] `tests/functional/test_live_exec.py` — EXEC-06 (Redis→SSE per-test)
- [ ] `tests/functional/test_kill_drain.py` — EXEC-06/D-07 (drain + purge, no orphan)
- [ ] `tests/functional/test_determinism.py` — two-runs-identical (planted spec + reset_target)
- [ ] `tests/functional/test_execute_tier.py` — EXEC-02 (API start + poll, single engine path)
- [ ] Worker test fixture: a planted/generated spec under `workspaces/<run_id>/` + a queued message helper
- [ ] No framework install needed beyond `uv add aio-pika==9.6.*` (pytest stack already present)

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Scoped CI token (JWT/service account) for the GH Actions → API call; existing JWT cookie for the live view (SSE auth-gated like the explorer) |
| V3 Session Management | yes | Reuse existing httpOnly cookie + SSE auth gate (`get_current_user` router dependency) |
| V4 Access Control | yes | Execution routes behind the router-level auth gate (mirror `routers/explore.py`); RBAC roles land in Phase 10 |
| V5 Input Validation | yes | `tier` is validated against an allow-list; `spec_path` is run_id-derived, never client input; `run_id` is the only client key |
| V6 Cryptography | no | No new crypto; target creds (PLAT-07) untouched in the execution loop |

### Known Threat Patterns for {RabbitMQ worker + subprocess execution}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Command injection via spec_path / tier | Tampering | argv LIST + no `shell=True`; spec_path run_id-derived; tier allow-list (carry-forward T-03-15) |
| Poison message infinite redelivery | DoS | `message.process(requeue=...)` with a redelivery cap / dead-letter; bound retries to 2 |
| CI token leak in workflow logs | Info Disclosure | GH secret, never echoed; scoped to start+poll only (Pitfall 7) |
| SSE/live view info leak to unauth user | Info Disclosure | Router-level auth gate on all execution routes (mirror explorer) |
| Artifact path traversal when serving evidence | Tampering | Reuse the `routers/explore.py` screenshot containment guard (reject `..`/separators; resolve inside run dir) |
| LLM call sneaks into the worker (SC3 breach) | (governance) | Import grep gate asserting no `init_chat_model`/gateway import in worker/execution code |

## Sources

### Primary (HIGH confidence)
- Codebase (read directly): `apps/api/app/services/execution.py`, `stability.py`, `explorer/progress.py`, `routers/explore.py`, `codegen/project.py`, `templates/conftest.py.j2`, `templates/steps/steps.py.j2`, `kg/risk.py`, `run_service.py`, `alembic/versions/0004,0006`, `infra/docker-compose.yml`, `infra/scripts/reset_target.py`, `pyproject.toml` — the reused seams + invariants.
- PyPI (queried live 2026-06-20): aio-pika 9.6.2, pytest-rerunfailures 16.3.
- `.planning/phases/07-execution-engine-workers/07-CONTEXT.md` — locked decisions D-01..D-08.
- CLAUDE.md — locked stack + What-NOT-to-use.

### Secondary (MEDIUM confidence)
- [playwright.dev/python/docs/test-runners] — pytest-playwright `--screenshot/--video/--tracing/--output` flags + values; no built-in retry. [VERIFIED]
- [docs.aio-pika.com] — connect_robust, set_qos, declare_queue, publisher confirms, queue.iterator/process/purge (API shape; exact signatures from training knowledge of the stable 9.x API). [CITED]
- [playwright.dev/python/docs/trace-viewer] — trace captures console + network. [CITED]
- pytest-bdd docs — Gherkin tags become pytest markers; `-m` selection; marker registration. [CITED]

### Tertiary (LOW confidence)
- Risk-based ranking weights (0.6/0.4, N=10) — no canonical source; tunable starting point (A1). [ASSUMED]

## Metadata

**Confidence breakdown:**
- Reused seams (runner, SSE, Redis, codegen, reset, risk): HIGH — read from source.
- aio-pika topology (consume/produce/QoS/purge): HIGH on shape, MEDIUM on exact 9.x signatures (verify against installed docs).
- pytest-playwright capture flags: HIGH — verified on official docs.
- Retry/flaky approach (worker loop, no new plugin): HIGH — derived from D-05 + pytest-playwright's lack of retry.
- Risk-based ranking formula: MEDIUM (shape) / LOW (exact weights) — tunable.
- Memory budget (prefetch=2): MEDIUM-HIGH — arithmetic over known mem_limits; measure on first run.

**Research date:** 2026-06-20
**Valid until:** 2026-07-20 (stable stack; aio-pika/pytest-playwright lines are mature)
