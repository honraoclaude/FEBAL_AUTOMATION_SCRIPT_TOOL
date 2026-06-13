---
phase: 01-foundation-dev-environment
plan: 02
subsystem: api
tags: [fastapi, uv, pydantic-settings, structlog, sqlalchemy-async, alembic, redis, pytest, docker]

# Dependency graph
requires:
  - phase: 01-foundation-dev-environment (plan 01-01)
    provides: compose core (postgres+redis), repo-root .env contract, canonical compose invocation
provides:
  - FastAPI app skeleton at apps/api — Settings (pydantic-settings), structlog with redact_sensitive, async SQLAlchemy engine/SessionLocal/get_db, Base(DeclarativeBase)
  - Async Alembic pipeline (env.py reads settings.database_url at runtime, target_metadata = Base.metadata)
  - GET /health at root pinging Postgres (SELECT 1) + Redis (ping), 200/503 with boolean component status
  - Wave 0 pytest scaffolding — asyncio_mode auto, functional/e2e markers, live-HTTP client fixture (D-02)
  - Self-migrating api Docker image (uv-based, alembic upgrade head before uvicorn) + compose api service (mem_limit 1g, healthcheck, hot-reload mount)
  - TARGET_CREDENTIAL_KEY filled in .env (valid Fernet key)
affects: [01-03, 01-04, 01-05, 01-06, 01-07, 01-08]

# Tech tracking
tech-stack:
  added: [fastapi 0.136, uvicorn 0.49, pydantic 2.13, pydantic-settings 2.14, sqlalchemy[asyncio] 2.0, asyncpg 0.31, alembic 1.18, greenlet 3.5, pyjwt 2.13, argon2-cffi 25.1, cryptography 48, redis 8.0, httpx 0.28, structlog 26, pytest 9, pytest-asyncio 1.4, pytest-playwright 0.8, ruff, mypy]
  patterns: [module-level settings singleton, lifespan engine dispose, live-HTTP functional tests (no ASGITransport), self-migrating container entrypoint]

key-files:
  created:
    - apps/api/pyproject.toml
    - apps/api/app/main.py
    - apps/api/app/core/config.py
    - apps/api/app/core/logging.py
    - apps/api/app/db/base.py
    - apps/api/app/db/session.py
    - apps/api/app/routers/health.py
    - apps/api/alembic/env.py
    - apps/api/tests/conftest.py
    - apps/api/tests/functional/test_health.py
    - apps/api/Dockerfile
  modified:
    - infra/docker-compose.yml
    - .env.example

key-decisions:
  - "API host-facing port moved 8000 -> 8001: host port 8000 is permanently held by another local project's auto-starting container (user chose to keep it). Container-internal port stays 8000; compose maps 8001:8000; API_URL/API_BASE_URL and conftest default updated."
  - "Host .wslconfig retuned to memory=3GB/processors=2/swap=4GB — host has only 5.7 GB RAM; the 16GB template value made the Docker engine unbootable (machine reboot required to clear the wedged WSL VM)."

patterns-established:
  - "Interfaces contract: plans 01-03/01-05 import settings, get_db, SessionLocal, Base exactly as defined in 01-02-PLAN <interfaces>"
  - "Functional tests hit the live stack over HTTP via the client fixture; API_BASE_URL env overrides the 8001 default"
  - "Container healthchecks use python urllib against container-internal port 8000"

requirements-completed: [INFRA-01]

# Metrics
duration: ~3h wall clock (split across interrupted sessions; ~45min active execution)
completed: 2026-06-13
---

# Phase 01 Plan 02: FastAPI Skeleton + Self-Migrating API Container Summary

**FastAPI chassis (typed settings, structlog credential redaction, async SQLAlchemy+Alembic, live-tested /health) running as a self-migrating 1g-capped container — one command yields a healthy postgres+redis+api stack**

## Performance

- **Duration:** ~45 min active execution, spread across 3 sessions (two executor interruptions + host reboot)
- **Completed:** 2026-06-13
- **Tasks:** 3 (1 human gate + 2 auto)
- **Files modified:** 25

## Accomplishments
- Full backend dependency set installed via uv after human package-legitimacy approval (Task 1 gate)
- API skeleton matches the plan's `<interfaces>` contract exactly: `settings` singleton, `engine`/`SessionLocal`/`get_db`, `Base`
- `/health` verified BOTH ways per D-09: host uvicorn against dockerized infra (hybrid) and containerized api — 200 with `postgres:true, redis:true`; pinned by passing functional test over live HTTP (D-02)
- Async Alembic wired to the single config source; `alembic upgrade head` exits 0; container entrypoint self-migrates before serving (D-08)
- structlog redaction processor verified: keys matching password/secret/credential/token replaced with [REDACTED] (PLAT-07 control #1)
- TARGET_CREDENTIAL_KEY now a valid Fernet key in .env (closes plan 01-01 TODO)

## Task Commits

1. **Task 1: Package legitimacy gate** — no commit (human approval gate; user approved full set)
2. **Task 2: FastAPI skeleton, Alembic, /health + functional test, conftest** - `a886b01` (feat)
3. **Task 3: api Dockerfile + compose service** - `8fd4119` (feat) — Dockerfile/.dockerignore files were staged with Task 2's commit; compose service in this commit

## Files Created/Modified
- `apps/api/app/core/config.py` - pydantic-settings Settings with credential_keys list (MultiFernet-ready)
- `apps/api/app/core/logging.py` - structlog JSON config + redact_sensitive processor
- `apps/api/app/db/{base,session}.py` - DeclarativeBase, async engine, SessionLocal, get_db dependency
- `apps/api/app/routers/health.py` - component-status health endpoint (booleans only, T-01-05)
- `apps/api/alembic/env.py` - async migrations reading settings.database_url at runtime
- `apps/api/tests/{conftest.py,functional/test_health.py}` - Wave 0 live-HTTP scaffolding + D-02 health test
- `apps/api/Dockerfile` - uv layered build, self-migrating CMD
- `infra/docker-compose.yml` - api service: mem_limit 1g, healthcheck, depends_on healthy, 8001:8000

## Decisions Made
- **Port contract change:** host-facing API port is 8001 (not 8000) — user chose to keep their other project's container on 8000. Container-internal port unchanged (8000). Plans 01-04/01-07/01-08 must use `API_URL=http://localhost:8001` from .env (compose-internal `http://api:8000` unaffected).
- `.wslconfig` retuned for the real host (5.7 GB RAM): memory=3GB/processors=2/swap=4GB.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Host port 8000 occupied by unrelated container**
- **Found during:** Task 2 verification (/health returned 404 from a foreign FastAPI app)
- **Issue:** `oh_ai_agent_qe_framework-agent-1` (another local project) auto-starts with Docker and binds 0.0.0.0:8000
- **Fix:** User decision — keep that container; this API moved to host port 8001 (.env, .env.example, conftest default, compose mapping)
- **Verification:** /health 200 on 8001 in both hybrid and container modes; functional test green
- **Committed in:** a886b01 + 8fd4119

**2. [Rule 3 - Blocking] .wslconfig 16GB cap unbootable on 5.7 GB host**
- **Found during:** resuming Task 2 verification (Docker engine stuck at HTTP 500 for 13+ min)
- **Issue:** plan 01-01 template assumed 24-32 GB host; first `wsl --shutdown` applied the bad cap and wedged the WSL VM (machine reboot required)
- **Fix:** %USERPROFILE%\.wslconfig rewritten to memory=3GB/processors=2/swap=4GB (host file only — .wslconfig.example template unchanged; docs update deferred to plan 01-08)
- **Verification:** Docker engine boots cleanly post-reboot; full 3-service stack healthy within the 3GB cap

---

**Total deviations:** 2 auto-fixed (both blocking environment conflicts)
**Impact on plan:** No scope creep; port contract change must be honored by later plans (recorded above).

## Issues Encountered
- Two executor-agent interruptions (network drop, then session usage limit) left work uncommitted; closed out inline after verification.
- Host machine has 5.7 GB RAM — far below the stack's design assumption. Phase-1 footprint (512m+256m+1g) fits in the 3GB WSL cap, but **Phase 3+ (neo4j 2g) and Phase 9/10 (elasticsearch 1.5g) will NOT fit**. Carried in STATE.md as a blocker to resolve before Phase 3 (options: more RAM, remote services, or trimmed mem_limits).

## User Setup Required

None - .wslconfig already applied (reboot done); no external service configuration required.

## Next Phase Readiness
- Plans 01-03 (auth) and 01-05 (target registry) can import settings/get_db/Base exactly per the interfaces contract
- Plan 01-04 (web) must use API_URL=http://localhost:8001 for hybrid rewrites; compose-internal http://api:8000 unchanged
- Memory ceiling concern carried for Phase 3+ (see Issues)

---
*Phase: 01-foundation-dev-environment*
*Completed: 2026-06-13*
