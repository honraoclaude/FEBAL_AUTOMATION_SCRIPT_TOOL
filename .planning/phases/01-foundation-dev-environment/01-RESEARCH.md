# Phase 1: Foundation & Dev Environment - Research

**Researched:** 2026-06-12
**Domain:** Full-stack platform scaffold — FastAPI + Next.js monorepo, Docker Compose on Windows 11/Docker Desktop, JWT cookie auth, encrypted credential storage, self-hosted demo target
**Confidence:** HIGH (stack pre-pinned and registry-verified; patterns verified against official docs; two MEDIUM items flagged inline)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Process directive (user-locked)**
- **D-01:** User delegated implementation decisions to Claude: "If you are clear what needs to be done we can start building in loop and keep developing." Build iteratively — after context, proceed to plan and execute without further discussion rounds; keep momentum phase to phase.
- **D-02:** **Every feature ships with functional tests.** This is a standing directive for ALL phases, not just Phase 1. For Phase 1: API features get pytest functional tests (httpx AsyncClient against the running FastAPI app, real Postgres via the compose stack); UI flows (login, target registration) get Playwright functional tests. Tests are written alongside each feature, not deferred to a testing phase.

**Account bootstrap & login (Claude's discretion, applied)**
- **D-03:** First admin user is seeded from environment variables (`ADMIN_EMAIL` / `ADMIN_PASSWORD`) on first startup; no public signup page (solo-user deployment; RBAC and user management arrive in Phase 10).
- **D-04:** JWT access token (short-lived, ~30 min) + refresh token (~7 days) delivered as httpOnly cookies; passwords hashed with argon2. Logout invalidates the session client-side and clears cookies.

**Target-app registration (Claude's discretion, applied)**
- **D-05:** v1 registration fields: name, base URL, one credential set (username/password), and exploration rules: origin allowlist (defaults to the base-URL origin), sandbox flag (marks target as restorable — gates destructive actions in Phase 4; default false), and optional budget overrides (max steps / depth / wall-clock / token spend) over global defaults.
- **D-06:** Credentials are write-only through the API: accepted on create/update, never returned in any response, masked in the UI. Encrypted at rest via app-level symmetric encryption (Fernet) with the master key supplied via environment variable — never committed.
- **D-07:** Targets support edit and soft-delete (deactivate) so historical exploration/execution data keeps its foreign keys in later phases.

**Dev workflow & compose (Claude's discretion, applied)**
- **D-08:** `docker compose up` is the one command: brings up Postgres, Redis, the FastAPI API, and the Next.js web shell with healthchecks and per-container memory limits (success criterion). Dormant services (Neo4j, RabbitMQ, Elasticsearch, MinIO-equivalent stores if any) exist only as compose profiles, not started by default.
- **D-09:** A documented hybrid dev mode also exists for fast iteration: infra in Docker, API (uvicorn --reload) and web (next dev) on the host. Both modes share the same `.env` configuration.

**Demo targets & snapshots (Claude's discretion, applied)**
- **D-10:** Phase 1 ships SauceDemo (Sauce Labs sample-app-web) self-hosted in Docker as the first demo target. It is stateless, so snapshot/restore = container restart — but the snapshot/restore contract (a script/API: `reset-target <name>`) is defined generically now so a stateful target (OrangeHRM) can plug in at Phase 4 when the Explorer needs it.

### Claude's Discretion
User explicitly delegated all four presented gray areas (account bootstrap, target registration shape, dev workflow, demo targets). Decisions D-03 through D-10 are Claude's picks grounded in `.planning/research/` — planner may refine details but must not contradict them without surfacing the change.

### Deferred Ideas (OUT OF SCOPE)
- Stateful demo target (OrangeHRM) with real DB snapshot/restore — Phase 4, when the Explorer needs realistic workflows
- User management UI / role assignment — Phase 10 (PLAT-04)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAT-01 | User can register a target application (name, URL, credentials, exploration rules) via API and UI | Targets data model + write-only credential pattern (Pattern 3), shadcn/ui form + table on Next.js 16 (Standard Stack), CRUD router pattern (Code Examples) |
| PLAT-03 | User can log in with email/password; sessions persist via JWT | PyJWT + argon2-cffi httpOnly-cookie pattern (Pattern 2), Next.js 16 `proxy.ts` route protection + rewrites-based same-origin API access (Pattern 4) |
| PLAT-07 | Target-app credentials stored encrypted, never in logs/prompts/generated code | Fernet via `cryptography` 48.x (Pattern 3), Pydantic response-model whitelisting, structlog redaction processor, dedicated leak-tests (Validation Architecture) |
| INFRA-01 | Platform runs locally via Docker Compose with healthchecks and per-container memory limits suited to Windows 11/Docker Desktop | Compose file with profiles/healthchecks/limits (Pattern 1), `.wslconfig` setup (currently MISSING on this machine — see Environment Availability), limit-enforcement verification step (Pitfall 3) |
| QUAL-04 | Self-hosted demo target apps run in Docker with snapshot/restore for repeatable exploration | SauceDemo self-host Dockerfile (Pattern 5), generic `reset-target <name>` contract design (Pattern 6) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack is locked:** Next.js/React/TypeScript frontend; FastAPI/Python backend; PostgreSQL; Redis; Docker — adopted as specified. STACK.md pins are authoritative; do not re-litigate versions.
- **Dev environment:** Windows 11 + Docker Desktop — all services must run locally via Docker Compose.
- **What NOT to use (from STACK.md, binding):** NextAuth/Auth.js (backend-issued JWT instead), passlib (argon2-cffi directly), python-jose (PyJWT), psycopg2 (asyncpg), aioredis (`redis.asyncio`), Selenium (Playwright), TypeScript 6.0 (pin 5.9).
- **GSD workflow enforcement:** file changes go through GSD commands (`/gsd:execute-phase` for planned phase work).
- **Conventions:** not yet established — Phase 1 sets them; planner should treat lint/format tooling (ruff, ESLint 9 flat config) as part of scaffolding.

## Summary

Phase 1 is a walking skeleton: prove the architecture with the thinnest end-to-end slice (Next.js UI → FastAPI → PostgreSQL) wrapped in the one-command Compose environment all 10 later phases build on. Nothing here is novel engineering — every component (JWT cookie auth, Fernet encryption, async SQLAlchemy + Alembic, compose profiles) is a solved problem with a canonical pattern. The risk is not "can we build it" but Windows-specific environment friction (file-watching across the WSL2 boundary, memory-limit enforcement quirks, bind-mount performance) and quiet security mistakes (credentials leaking into logs or responses).

Research confirmed three Windows-critical facts: (1) Turbopack — Next.js 16's default bundler — does **not** reliably detect bind-mounted file changes inside containers on Windows [VERIFIED: docker/compose#12827], which makes D-09's hybrid host-mode the primary iteration workflow, not a nice-to-have; (2) uvicorn's reloader works in containers with `WATCHFILES_FORCE_POLLING=true` [VERIFIED: uvicorn docs/discussions]; (3) sources conflict on whether `deploy.resources.limits` is enforced by non-swarm `docker compose` — so the plan must use the guaranteed service-level `mem_limit`/`cpus` keys and add a runtime verification step (`docker inspect`). Also: the upstream SauceDemo repo's bundled Dockerfile is incomplete (node:14 base, no CMD/EXPOSE, Sauce Connect cruft) — we write our own multi-stage build to nginx.

The local environment is ready (Docker 29.4.3, Compose v5.1.3, Node 24, Python 3.13.13, uv 0.11.11) with one gap: **no `.wslconfig` exists** — creating it is a Phase 1 deliverable per PITFALLS.md Pitfall 9.

**Primary recommendation:** Build in six vertical slices (scaffold+compose → API skeleton+migrations → auth → web shell → target registry → SauceDemo+reset), each shipping its functional tests per D-02, with `docker compose up` green as the phase gate.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Email/password verification, JWT issue/refresh | API / Backend (FastAPI) | — | Backend owns auth (STACK.md: no NextAuth); RBAC arrives Phase 10 in the same place |
| Session persistence | Browser (httpOnly cookies) | API sets/clears them | Cookies are the transport; only the API can read/mint tokens |
| Route protection / login redirect | Frontend Server (Next.js `proxy.ts`) | API / Backend (authority) | `proxy.ts` does coarse cookie-presence redirects; the API is the only signature-verifying authority (web tier never holds the JWT secret) |
| Target registration CRUD + validation | API / Backend | Frontend (zod form validation as UX nicety) | Business rules and persistence live server-side; client validation is duplicated convenience only |
| Credential encryption/decryption (Fernet) | API / Backend | — | Master key exists only in the API container's env; web tier never sees plaintext credentials |
| Credential masking | API / Backend (omit from response schema) | Frontend (render "••••" placeholder) | Masking by omission at the schema boundary, not by frontend string-mangling |
| Healthchecks, memory limits, service lifecycle | Infra (Compose) | — | Compose owns container lifecycle; apps just expose `/health` |
| Demo target hosting + reset | Infra (Compose service + reset script) | API (none in Phase 1) | D-10: reset is a script contract now; API wrapping is a later-phase concern |
| Database schema evolution | API / Backend (Alembic) | — | Single migration history from day one; applied as an API startup/entrypoint step |

## Standard Stack

All versions below were re-verified live against PyPI on 2026-06-12 in this session (and against npm in STACK.md, dated 2026-06-12). This is the Phase 1 subset of the project-wide STACK.md — do not install later-phase packages (langgraph, neo4j, aio-pika, elasticsearch) now (Pitfall 8: staggered activation).

### Core (backend — `apps/api`, managed with uv, Python 3.13)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.136.x (0.136.3 current) | REST API | Locked by STACK.md [VERIFIED: PyPI] |
| uvicorn[standard] | 0.49.x | ASGI server (+ watchfiles reloader) | Locked by STACK.md; `[standard]` pulls watchfiles needed for container reload [VERIFIED: PyPI] |
| pydantic / pydantic-settings | 2.13.x / 2.14.x | Schemas + 12-factor env config | Locked by STACK.md |
| sqlalchemy[asyncio] | 2.0.x (≥2.0.50) | Async ORM | Locked by STACK.md |
| asyncpg | 0.31.x | Postgres async driver | Locked by STACK.md |
| alembic | 1.18.x | Migrations | Locked by STACK.md |
| greenlet | 3.5.x | SQLAlchemy async bridge (explicit pin for Windows wheels) | Locked by STACK.md |
| pyjwt | 2.13.x (2.13.0 current) | JWT mint/verify | Locked by STACK.md [VERIFIED: PyPI] |
| argon2-cffi | 25.1.x (25.1.0 current) | Password hashing | Locked by STACK.md [VERIFIED: PyPI] |
| **cryptography** | **48.x (48.0.1 current)** | **Fernet credential encryption** | Not in STACK.md (new for D-06). The canonical Python crypto library; Fernet is its documented recipe for symmetric authenticated encryption [VERIFIED: PyPI; CITED: cryptography.io/en/latest/fernet/] |
| redis | 8.0.x | Redis client (Phase 1: connectivity in `/health` only) | Locked by STACK.md |
| httpx | 0.28.x | Async HTTP client (used by tests) | Locked by STACK.md |
| structlog | 26.x | Structured JSON logging + credential redaction processor | Locked by STACK.md |

### Supporting (dev/test)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest / pytest-asyncio | 9.0.x / 1.4.x (`asyncio_mode = "auto"`) | Functional test runner | All API tests (D-02) |
| pytest-playwright | 0.8.x (0.8.0 current) | Playwright fixtures for pytest | UI functional tests (login, target registration) — one runner for API + UI tests [VERIFIED: PyPI] |
| playwright (Python) | 1.60.x | Browser automation for UI tests | Pulled by pytest-playwright; `playwright install chromium` required once |
| ruff / mypy | latest | Lint+format / type check | Scaffolding deliverable |
| uv | 0.11.x (installed: 0.11.11) | Python env/package manager | `uv sync` locally, in Docker builds |

### Frontend (`apps/web`, Node 22 LTS in containers; host has Node 24 — both satisfy Next 16's ≥20.9)

| Library | Version | Purpose |
|---------|---------|---------|
| next | 16.2.x | App Router framework — note `proxy.ts` replaces `middleware.ts` (see State of the Art) |
| react / react-dom | 19.2.x | UI runtime |
| typescript | 5.9.x | Pin 5.9, NOT 6.0 (STACK.md) |
| tailwindcss | 4.3.x | CSS-first config (`@theme`), via `@tailwindcss/postcss` |
| shadcn/ui (CLI) | latest | Form, Input, Button, Card, Table, Dialog components for login + target registry |
| zod | 4.x | Form/response validation |
| @tanstack/react-query | 5.x | Server state (targets list) |
| lucide-react | 1.x | Icons |

Defer `recharts`, `@tanstack/react-table`, `zustand` until a phase needs them (Pitfall 8) — `zustand` only if client state actually appears; Phase 1 likely needs none.

### Infra images (Compose)

| Image | Tag | Phase 1 state |
|-------|-----|---------------|
| postgres | 17-alpine | Active |
| redis | 8-alpine | Active |
| apps/api Dockerfile | python:3.13-slim + uv | Active |
| apps/web Dockerfile | node:22-alpine (dev) / multi-stage standalone (later) | Active |
| saucedemo (own Dockerfile) | build: node:16-bullseye → serve: nginx:alpine | Active (tiny) |
| neo4j | 2025.x | Dormant — `profiles: [graph]` |
| rabbitmq | 4-management | Dormant — `profiles: [queue]` |
| elasticsearch | 9.x | Dormant — `profiles: [search]` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pytest-playwright (Python) for UI tests | Playwright Test (Node) in apps/web | Node runner is idiomatic for frontend teams, but splits the test toolchain in two; Python keeps one runner/one report and matches the project's eventual pytest-bdd execution stack. Use Python. |
| Next.js rewrites proxying `/api/*` → FastAPI | CORS + cookies cross-origin | Cross-origin cookies need `SameSite=None; Secure` (impossible on plain-http localhost) and CORS credential config. Rewrites make all calls first-party — strictly simpler and safer. Use rewrites. |
| Fernet (cryptography) | pgcrypto in Postgres | pgcrypto puts the key in SQL/DB layer and couples encryption to Postgres; Fernet keeps key handling in the app where D-06 places it. Use Fernet. |
| Own SauceDemo Dockerfile | Upstream repo's Dockerfile | Upstream Dockerfile is incomplete (node:14, no CMD/EXPOSE, bundles Sauce Connect) [VERIFIED: raw.githubusercontent.com saucelabs/sample-app-web Dockerfile]. Write our own multi-stage build. |

**Installation:**
```bash
# Backend (inside apps/api)
uv init --python 3.13 && uv add "fastapi==0.136.*" "uvicorn[standard]==0.49.*" \
  "pydantic==2.13.*" "pydantic-settings==2.14.*" "sqlalchemy[asyncio]==2.0.*" \
  "asyncpg==0.31.*" "alembic==1.18.*" "greenlet==3.5.*" "pyjwt==2.13.*" \
  "argon2-cffi==25.1.*" "cryptography==48.*" "redis==8.0.*" "httpx==0.28.*" "structlog==26.*"
uv add --dev "pytest==9.0.*" "pytest-asyncio==1.4.*" "pytest-playwright==0.8.*" ruff mypy
uv run playwright install chromium

# Frontend
npx create-next-app@16 apps/web --typescript --tailwind --eslint --app
cd apps/web && npm install zod@4 @tanstack/react-query@5 lucide-react && npx shadcn@latest init
```

## Package Legitimacy Audit

slopcheck could not be installed in this session (environment policy denied installing an agent-chosen package — appropriately, since it is itself not in any project manifest). Per protocol, graceful degradation applies. Mitigating context: **every package below is already pinned in `.planning/research/STACK.md`, which verified them live against PyPI/npm + official docs on 2026-06-12**, and this session independently re-confirmed current versions on PyPI for the Phase 1 delta set. All are decade-old, multi-million-download ecosystem staples with official source repos — none is a plausible slopsquat. Formal disposition per protocol: tagged `[ASSUMED — slopcheck unavailable]`; the planner should gate the two dependency-manifest tasks (backend `uv add`, frontend `npm install`) behind a single `checkpoint:human-verify` each rather than per-package checkpoints.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| fastapi 0.136.3 | PyPI | ~8 yrs | very high | github.com/fastapi/fastapi | unavailable | Approved (registry+docs verified) |
| cryptography 48.0.1 | PyPI | ~12 yrs | very high | github.com/pyca/cryptography | unavailable | Approved (registry+docs verified) |
| pyjwt 2.13.0 | PyPI | ~11 yrs | very high | github.com/jpadilla/pyjwt | unavailable | Approved |
| argon2-cffi 25.1.0 | PyPI | ~10 yrs | high | github.com/hynek/argon2-cffi | unavailable | Approved |
| pytest-playwright 0.8.0 | PyPI | ~5 yrs | high | github.com/microsoft/playwright-pytest | unavailable | Approved (Microsoft official) |
| sqlalchemy / asyncpg / alembic / uvicorn / pydantic / redis / httpx / structlog / greenlet / pytest / pytest-asyncio | PyPI | all mature | all high | all official orgs | unavailable | Approved (pinned in STACK.md, registry-verified) |
| next / react / typescript / tailwindcss / zod / @tanstack/react-query / lucide-react / shadcn CLI | npm | all mature | all high | vercel/facebook/microsoft/etc. | unavailable | Approved (pinned in STACK.md, npm-verified 2026-06-12) |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none
**Ecosystem cross-check:** all Python packages verified on PyPI (`pip index versions`, this session); all JS packages verified on npm (STACK.md, 2026-06-12). No cross-ecosystem confusion candidates.

## Architecture Patterns

### System Architecture Diagram

```
Browser (user)
   │  http://localhost:3000  (cookies: access_token, refresh_token — httpOnly)
   ▼
┌──────────────────────────────┐    rewrite /api/:path* ─────────────┐
│ Next.js 16 web (apps/web)    │                                     │
│  proxy.ts: no access cookie  │                                     ▼
│  on protected route → /login │                     ┌────────────────────────────┐
│  pages: /login, /targets     │                     │ FastAPI (apps/api) :8000   │
└──────────────────────────────┘                     │ routers: auth, targets,    │
                                                     │          health            │
   docker compose up (default profile)               │ lifespan: alembic check,   │
┌─────────────────────────────────────────────┐      │   seed admin (D-03),       │
│ postgres:17 ◄── SQLAlchemy async/asyncpg ───┼──────│   structlog w/ redaction   │
│ redis:8     ◄── redis.asyncio (health ping)─┼──────│ crypto: Fernet(key=env)    │
│ saucedemo (nginx static)  ◄─ demo target    │      └────────────────────────────┘
│                                             │                  ▲
│ dormant profiles (defined, never started):  │                  │
│   neo4j [graph] rabbitmq [queue]            │       reset-target saucedemo
│   elasticsearch [search]                    │       (script → compose restart)
└─────────────────────────────────────────────┘
```

Primary use case trace: browser submits login form → Next.js rewrite forwards `/api/auth/login` to FastAPI → FastAPI verifies argon2 hash in Postgres → sets httpOnly cookies → browser navigates to `/targets` → `proxy.ts` sees cookie, allows → page fetches `/api/targets` → FastAPI validates JWT from cookie → returns targets (credentials omitted by response schema).

### Recommended Project Structure

Monorepo per ARCHITECTURE.md. Phase 1 creates the full top-level skeleton but only populates `apps/` and `infra/` — later-phase directories get a README stub only (Pitfall 8: no speculative code).

```
/
├── apps/
│   ├── api/                      # FastAPI — uv project
│   │   ├── app/
│   │   │   ├── main.py           # app factory, lifespan (engine, seed admin)
│   │   │   ├── core/
│   │   │   │   ├── config.py     # pydantic-settings Settings
│   │   │   │   ├── security.py   # argon2 hash/verify, JWT mint/decode, cookie helpers
│   │   │   │   ├── crypto.py     # Fernet encrypt/decrypt for target credentials
│   │   │   │   └── logging.py    # structlog config + redaction processor
│   │   │   ├── db/               # engine, async_sessionmaker, Base, deps
│   │   │   ├── models/           # user.py, target.py (SQLAlchemy)
│   │   │   ├── schemas/          # auth.py, target.py (Pydantic — response models omit credentials)
│   │   │   ├── routers/          # auth.py, targets.py, health.py
│   │   │   └── services/         # target_service.py (encrypt-on-write lives here)
│   │   ├── alembic/  alembic.ini
│   │   ├── tests/
│   │   │   ├── conftest.py       # base-url config, db-truncate fixture, auth helper
│   │   │   ├── functional/       # test_auth.py, test_targets.py, test_credential_security.py
│   │   │   └── e2e/              # test_login_ui.py, test_targets_ui.py (pytest-playwright)
│   │   ├── pyproject.toml  uv.lock  Dockerfile
│   ├── web/                      # Next.js 16
│   │   ├── app/
│   │   │   ├── login/page.tsx
│   │   │   └── (dashboard)/targets/page.tsx   # list + register dialog
│   │   ├── lib/api/              # typed fetch client
│   │   ├── proxy.ts              # NOT middleware.ts (Next 16)
│   │   ├── next.config.ts        # rewrites: /api/:path* → API_URL
│   │   └── Dockerfile
├── agents/  workers/  kg/  shared/events/  workspaces/   # README stubs only
├── infra/
│   ├── docker-compose.yml
│   ├── targets/saucedemo/Dockerfile   # our multi-stage build (pinned upstream SHA)
│   └── scripts/reset_target.py        # generic reset contract (D-10)
├── docs/dev-setup.md             # .wslconfig, hybrid mode, reset-target usage
├── .env.example                  # every var documented; .env gitignored
├── .gitattributes                # *.sh / Dockerfile / *.py eol=lf  (Windows CRLF guard)
└── .wslconfig.example            # copied to %USERPROFILE%\.wslconfig (documented step)
```

### Pattern 1: Compose with profiles, healthchecks, and memory limits (INFRA-01, D-08)

**What:** One `docker-compose.yml`; default services postgres/redis/api/web/saucedemo; dormant services carry `profiles:` so `docker compose up` never starts them; every service has a healthcheck; app services use `depends_on: condition: service_healthy`.

**Memory limits — conflict found, prescriptive resolution:** community sources state non-swarm `docker compose` ignores `deploy.resources.limits` without `--compatibility`, while the Compose Spec documents the syntax without that caveat; older GitHub issues (docker/compose#5803, #7307) predate Compose v2's spec implementation. **Use the service-level `mem_limit:` and `cpus:` keys, which are unconditionally enforced in non-swarm mode, and verify at runtime** (`docker inspect -f '{{.HostConfig.Memory}}' <container>` must be non-zero). [CITED: docs.docker.com/compose/compose-file/deploy/; conflict noted — see Open Questions]

```yaml
# infra/docker-compose.yml (shape — source: Compose Spec docs + PITFALLS.md Pitfall 9)
services:
  postgres:
    image: postgres:17-alpine
    mem_limit: 512m
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes: [pgdata:/var/lib/postgresql/data]
    ports: ["5432:5432"]          # exposed for hybrid host mode (D-09)

  redis:
    image: redis:8-alpine
    mem_limit: 256m
    healthcheck: { test: ["CMD", "redis-cli", "ping"], interval: 5s, timeout: 3s, retries: 10 }
    ports: ["6379:6379"]

  api:
    build: ../apps/api
    mem_limit: 1g
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      REDIS_URL: redis://redis:6379/0
      WATCHFILES_FORCE_POLLING: "true"     # bind-mount reload on Windows
    volumes: ["../apps/api/app:/app/app"]  # hot-reload source mount
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status==200 else 1)"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
    ports: ["8000:8000"]

  web:
    build: ../apps/web
    mem_limit: 1536m               # next dev + Turbopack is memory-hungry
    environment:
      API_URL: http://api:8000
      WATCHPACK_POLLING: "true"
    volumes:
      - "../apps/web:/app"
      - /app/node_modules          # volume-mask: NEVER bind-mount node_modules on Windows
      - /app/.next
    depends_on:
      api: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "node", "-e", "fetch('http://localhost:3000').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 40s
    ports: ["3000:3000"]

  saucedemo:
    build: ./targets/saucedemo
    mem_limit: 128m
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:80"]
      interval: 10s
      timeout: 3s
      retries: 5
    ports: ["8080:80"]

  # Dormant — defined now, activated by later phases (D-08)
  neo4j:
    image: neo4j:2025
    profiles: [graph]
    mem_limit: 2g
  rabbitmq:
    image: rabbitmq:4-management
    profiles: [queue]
    mem_limit: 512m
  elasticsearch:
    image: elasticsearch:9.4.1
    profiles: [search]
    mem_limit: 1536m
    environment: { ES_JAVA_OPTS: "-Xms512m -Xmx1g", discovery.type: single-node }

volumes: { pgdata: }
```

### Pattern 2: JWT httpOnly-cookie auth — FastAPI side (PLAT-03, D-04)

**What:** Backend-issued access (30 min) + refresh (7 d) JWTs set as httpOnly cookies. PyJWT HS256 with a `type` claim distinguishing token kinds; argon2-cffi `PasswordHasher` for password storage; admin seeded idempotently at startup from `ADMIN_EMAIL`/`ADMIN_PASSWORD` (D-03).

**When to use:** All authenticated endpoints via a `get_current_user` dependency reading the cookie.

**CSRF posture:** `SameSite=Lax` cookies + JSON-only request bodies on a localhost solo deployment is the accepted MVP posture (Lax blocks cross-site POSTs; no cross-site embedding exists). `secure=False` is required on plain-http localhost or browsers drop the cookie — make it a setting (`COOKIE_SECURE`) defaulting false in dev. Document that real deployments flip it true. [ASSUMED — standard practice; multiple valid CSRF strategies exist]

```python
# Source: PyJWT docs (pyjwt.readthedocs.io) + argon2-cffi docs (argon2-cffi.readthedocs.io) + FastAPI cookie docs
import jwt
from datetime import datetime, timedelta, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher()  # argon2id defaults = OWASP-recommended

def create_token(sub: str, token_type: str, expires: timedelta) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": sub, "type": token_type, "iat": now, "exp": now + expires},
        settings.jwt_secret, algorithm="HS256",
    )

@router.post("/login")
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_email(db, body.email)
    try:
        ph.verify(user.password_hash, body.password)  # raises on mismatch
    except (VerifyMismatchError, AttributeError):
        raise HTTPException(401, "Invalid credentials")  # same error for unknown user
    access = create_token(str(user.id), "access", timedelta(minutes=30))
    refresh = create_token(str(user.id), "refresh", timedelta(days=7))
    response.set_cookie("access_token", access, httponly=True, samesite="lax",
                        secure=settings.cookie_secure, max_age=1800, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, samesite="lax",
                        secure=settings.cookie_secure, max_age=604800, path="/api/auth")
    return {"ok": True}

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        if payload.get("type") != "access":
            raise HTTPException(401, "Wrong token type")
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    return await get_user(db, payload["sub"])
```

Refresh endpoint: reads `refresh_token` cookie (path-scoped to `/api/auth`), validates `type == "refresh"`, issues a new access cookie. Logout: `response.delete_cookie(...)` for both (D-04: client-side invalidation only — no server-side token denylist in Phase 1; acceptable for solo MVP, revisit with RBAC in Phase 10).

### Pattern 3: Write-only Fernet-encrypted credentials (PLAT-07, D-05/D-06)

**What:** `targets` table stores `encrypted_username` / `encrypted_password` (LargeBinary). Encryption happens in the service layer on create/update; decryption has exactly one caller surface (`get_decrypted_credentials`, consumed by the Explorer in Phase 4 — in Phase 1 it exists only for the round-trip test). Response schemas structurally cannot leak: the Pydantic response model simply has no credential fields — whitelisting by omission, not blacklisting by exclusion.

```python
# Source: cryptography Fernet docs — cryptography.io/en/latest/fernet/
from cryptography.fernet import Fernet, MultiFernet

# key generation (one-time, documented in .env.example):
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
fernet = MultiFernet([Fernet(k) for k in settings.credential_keys])  # list enables future rotation

def encrypt(value: str) -> bytes:
    return fernet.encrypt(value.encode())

def decrypt(token: bytes) -> str:
    return fernet.decrypt(token).decode()
```

```python
# Response schema: credentials are unrepresentable, not "filtered"
class TargetResponse(BaseModel):
    id: int
    name: str
    base_url: str
    has_credentials: bool          # the ONLY credential-derived field
    origin_allowlist: list[str]
    sandbox: bool
    budget_overrides: BudgetOverrides | None
    is_active: bool                # soft delete (D-07)
```

**Log redaction:** a structlog processor drops/masks any event-dict key matching `password|credential|secret|token` before rendering. The leak test (Validation Architecture) captures API logs during a registration round-trip and asserts the plaintext password appears nowhere.

**Target model fields (D-05):** `name` (unique), `base_url`, `encrypted_username`, `encrypted_password`, `origin_allowlist` (JSON, default `[origin(base_url)]` computed server-side), `sandbox` (bool, default false), `budget_overrides` (JSON nullable: max_steps/max_depth/wall_clock_seconds/token_budget), `is_active` (bool, default true — soft delete per D-07), timestamps.

### Pattern 4: Next.js 16 route protection + same-origin API (PLAT-03 frontend)

**What:** Next.js 16 renamed `middleware.ts` → `proxy.ts` (exported function `proxy`, nodejs runtime; middleware.ts still works but logs a deprecation warning) [VERIFIED: nextjs.org/docs/messages/middleware-to-proxy]. `proxy.ts` does a coarse cookie-presence check and redirects to `/login`; it never verifies signatures (the JWT secret stays in the API tier). The API client treats any 401 as "redirect to /login". All API traffic goes through a Next.js rewrite so cookies are first-party and CORS never exists.

```typescript
// proxy.ts — Source: nextjs.org/docs/app/api-reference/file-conventions/proxy
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  const hasSession = request.cookies.has("access_token");
  const isLogin = request.nextUrl.pathname.startsWith("/login");
  if (!hasSession && !isLogin)
    return NextResponse.redirect(new URL("/login", request.url));
  if (hasSession && isLogin)
    return NextResponse.redirect(new URL("/targets", request.url));
  return NextResponse.next();
}
export const config = { matcher: ["/((?!_next|favicon.ico|api).*)"] };
```

```typescript
// next.config.ts — rewrites make FastAPI same-origin from the browser's view
const nextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*",
              destination: `${process.env.API_URL ?? "http://localhost:8000"}/api/:path*` }];
  },
};
```

`API_URL=http://api:8000` in the container, defaults to `http://localhost:8000` in hybrid host mode — this single variable is the D-09 mode switch for the web tier.

### Pattern 5: Self-hosted SauceDemo (QUAL-04, D-10)

**What:** `saucelabs/sample-app-web` is a React SPA (`npm run build` → static `build/` dir; state lives entirely in the browser's localStorage — the server side is stateless static files) [VERIFIED: github.com/saucelabs/sample-app-web README]. The repo's own Dockerfile is unusable (node:14 base, no CMD/EXPOSE, bundles Sauce Connect) [VERIFIED: upstream Dockerfile fetched this session]. Build our own multi-stage image, pinned to an upstream commit SHA for reproducibility:

```dockerfile
# infra/targets/saucedemo/Dockerfile
FROM node:16-bullseye AS build
# node:16: the app's webpack/babel toolchain predates OpenSSL 3; Node 17+ commonly fails
# with ERR_OSSL_EVP_UNSUPPORTED on old webpack builds [ASSUMED — verify on first build;
# fallback: ENV NODE_OPTIONS=--openssl-legacy-provider]
ARG SAUCEDEMO_SHA=master   # pin to a real SHA in the plan
RUN git clone https://github.com/saucelabs/sample-app-web.git /src \
 && cd /src && git checkout ${SAUCEDEMO_SHA}
WORKDIR /src
RUN npm ci && npm run build

FROM nginx:alpine
COPY --from=build /src/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf   # SPA fallback: try_files $uri /index.html
EXPOSE 80
```

### Pattern 6: Generic reset-target contract (D-10)

**What:** `infra/scripts/reset_target.py <name>` — a small registry maps target name → reset strategy. Phase 1 implements one strategy (`compose-restart`); Phase 4 adds `db-snapshot` for OrangeHRM without changing the contract.

**Contract:** `reset-target <name>` (1) performs the strategy, (2) waits until the target's healthcheck passes, (3) exits 0 on success / non-zero with a message on failure. Idempotent; safe to call between every exploration/execution run.

```python
# infra/scripts/reset_target.py (shape)
STRATEGIES = {
    "saucedemo": {"strategy": "compose-restart", "service": "saucedemo",
                  "health_url": "http://localhost:8080"},
    # Phase 4: "orangehrm": {"strategy": "db-snapshot", ...}
}
# compose-restart: subprocess docker compose restart <service>; poll health_url until 200 or timeout
```

Note honestly: because SauceDemo's mutable state is browser-localStorage, a container restart resets nothing the *tests* see — Playwright's fresh browser contexts provide the real isolation. The contract still ships now because Phase 7's reproducibility checks and Phase 4's stateful targets consume it (CONTEXT.md integration points).

### Pattern 7: Walking skeleton build order (thinnest end-to-end slice)

The thinnest slice proving the architecture is **login**: UI form → rewrite → FastAPI → argon2 verify against a seeded Postgres row → cookie → protected page. Get that working end-to-end before widening to the target registry. Suggested plan slicing:

1. **Scaffold + Compose core** — monorepo dirs, `.env.example`, `.gitattributes`, `.wslconfig` docs, compose with postgres+redis healthy
2. **API skeleton** — settings, structlog, async engine/session, Alembic wired (async env.py), `/health` (DB+Redis ping), api container healthy in compose
3. **Auth slice** — users migration, seed admin, login/refresh/logout, `get_current_user` + pytest functional tests (D-02)
4. **Web shell** — Next 16 scaffold, login page, proxy.ts, rewrites, web container healthy + Playwright login test (walking skeleton complete here)
5. **Target registry slice** — model+migration, Fernet crypto, CRUD with write-only credentials + leak tests; targets UI (list + register dialog) + Playwright test
6. **Demo target + phase gate** — SauceDemo image, reset script, full `docker compose up` from clean state, memory-limit verification, docs

### Anti-Patterns to Avoid

- **NextAuth/Auth.js for login:** banned by STACK.md — second source of auth truth; backend owns JWT.
- **Bind-mounting `node_modules` on Windows:** catastrophic I/O performance and broken native binaries (host=Windows, container=Linux); always volume-mask it.
- **Blacklist-filtering credentials out of responses:** use response models that never contain the fields; filtering is one refactor away from a leak.
- **`docker compose up` requiring manual pre-steps:** migrations and admin seeding must run inside the API startup path (entrypoint runs `alembic upgrade head`, lifespan seeds admin idempotently) — one command means one command (D-08).
- **Standing up dormant services "to test the profiles":** profiles are verified by asserting the services are *absent* from `docker compose ps`, not by starting them (Pitfall 8).
- **Building a server-side session store / token denylist now:** D-04 specifies client-side logout; Redis-backed revocation is a Phase 10 (RBAC) concern.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password hashing | Custom salt+SHA loops | argon2-cffi `PasswordHasher` | OWASP-recommended; constant-time verify, tuned params, rehash detection |
| Token format/signing | Custom signed strings | PyJWT | Expiry/clock-skew/claim validation are full of edge cases |
| Symmetric encryption | Raw AES via hazmat layer | `cryptography.fernet.Fernet` / `MultiFernet` | Authenticated encryption + versioned tokens + key rotation built in; hazmat misuse (nonce reuse, no MAC) is the classic vuln |
| Schema migrations | Hand-run SQL files | Alembic | Ordered history, autogenerate, async-compatible env.py |
| Env config parsing | os.environ scattering | pydantic-settings | Typed, validated, single Settings class shared by both run modes (D-09) |
| UI form/table/dialog primitives | Custom CSS components | shadcn/ui | Copy-in components; accessibility and focus management done |
| Frontend/backend type sync | Hand-written TS interfaces | openapi-typescript (optional this phase) | FastAPI's OpenAPI is the contract; generation beats drift |
| SPA static serving | Custom Node static server for SauceDemo | nginx:alpine | Healthcheckable, 10 MB, try_files fallback is one line |

**Key insight:** Phase 1 contains zero novel problems. Every hour spent on a bespoke solution here is an hour stolen from Phase 4 (the genuinely novel Explorer), and bespoke auth/crypto is also where security bugs enter.

## Common Pitfalls

### Pitfall 1: Turbopack ignores bind-mount file changes in containers on Windows
**What goes wrong:** `next dev` (Turbopack is Next 16's default) inside a container doesn't hot-reload when files change on the Windows host; changes sync but no rebuild fires.
**Why it happens:** Filesystem events don't cross the Windows→WSL2-VM boundary on bind mounts; Turbopack's polling support is unreliable in this configuration [VERIFIED: docker/compose#12827, vercel/next.js#71622].
**How to avoid:** Treat hybrid host-mode (D-09: `next dev` on the host) as the primary iteration workflow. In the container set `WATCHPACK_POLLING=true` (helps the webpack fallback path) but don't promise containerized web hot-reload; the compose web service's job is "stack is up and serving", not sub-second DX.
**Warning signs:** Edits visible in the container filesystem but UI never updates without container restart.

### Pitfall 2: uvicorn --reload silent failure in containers
**What goes wrong:** API container never reloads on host edits.
**Why it happens:** Same event-propagation issue; watchfiles defaults to notification-based watching.
**How to avoid:** `WATCHFILES_FORCE_POLLING=true` in the api service environment [VERIFIED: uvicorn settings docs + Kludex/uvicorn#1893].
**Warning signs:** "Started reloader process" in logs but edits require manual restart.

### Pitfall 3: Memory limits silently not applied
**What goes wrong:** `deploy.resources.limits` present in YAML, containers run unlimited; success criterion 1 quietly unmet.
**Why it happens:** Historical non-swarm Compose ignored `deploy.` limits without `--compatibility`; source disagreement on current v2 behavior (see Open Questions).
**How to avoid:** Use service-level `mem_limit:`/`cpus:` (unconditionally enforced non-swarm). Verification step in the plan: `docker inspect -f '{{.Name}} {{.HostConfig.Memory}}' $(docker compose ps -q)` — every value non-zero.
**Warning signs:** `docker stats` shows `LIMIT` equal to total machine memory.

### Pitfall 4: Missing `.wslconfig` lets Vmmem eat the machine (PITFALLS.md Pitfall 9)
**What goes wrong:** WSL2 grabs memory and doesn't return it; afternoon slowdowns; OOM-killed containers misread as app bugs.
**How to avoid:** Ship `.wslconfig.example` (`memory=` cap leaving ≥8 GB for Windows, `autoMemoryReclaim=gradual`, swap configured) + a documented install step (`copy` to `%USERPROFILE%`, `wsl --shutdown`). **This machine currently has no `.wslconfig`** [VERIFIED: probed this session] — creating it is a task, not a doc footnote. Also verify the stack comes up healthy after `wsl --shutdown` + restart ("Looks Done But Isn't" checklist).
**Warning signs:** Vmmem >70% of RAM in Task Manager.

### Pitfall 5: CRLF line endings break container scripts
**What goes wrong:** Shell scripts/entrypoints edited on Windows get CRLF, fail in Linux containers with cryptic `\r: command not found` or "no such file or directory" on the shebang.
**How to avoid:** `.gitattributes` with `*.sh text eol=lf`, `Dockerfile* text eol=lf` from the first commit; prefer Python entrypoints (reset script is Python partly for this reason).

### Pitfall 6: Cookie flags wrong for plain-http localhost
**What goes wrong:** Login "succeeds" but the browser silently drops the cookie → every subsequent request 401s; hours lost.
**Why it happens:** `Secure=true` cookies are rejected over http (localhost exemptions vary by browser); cross-origin cookies need SameSite=None+Secure.
**How to avoid:** `COOKIE_SECURE=false` setting for local dev; same-origin via Next rewrites so SameSite=Lax just works. The Playwright login test catches regressions structurally.

### Pitfall 7: Admin seeding races / re-seeds
**What goes wrong:** Seed-on-startup re-creates or crashes on restart, or races when multiple workers start.
**How to avoid:** Idempotent seed (INSERT ... ON CONFLICT DO NOTHING semantics / check-then-create inside a transaction) in lifespan; run uvicorn single-worker in dev; entrypoint order = `alembic upgrade head` → start app.

### Pitfall 8: Functional tests polluting each other's state
**What goes wrong:** D-02 tests run against the live compose Postgres; leftover rows make tests order-dependent.
**How to avoid:** conftest fixture truncating `targets` (and non-admin `users`) between tests, or unique-per-test names (faker/uuid suffix). Never assert global counts; assert on entities the test created.

### Pitfall 9: SauceDemo build breaks on modern Node
**What goes wrong:** `npm run build` fails in the image with `ERR_OSSL_EVP_UNSUPPORTED` or similar.
**Why it happens:** Upstream targets Node 14-era webpack/Babel; OpenSSL 3 (Node 17+) removed md4 used by old webpack.
**How to avoid:** Build stage on `node:16-bullseye`; if it still fails, `NODE_OPTIONS=--openssl-legacy-provider`. [ASSUMED — verify on first build]

## Code Examples

Verified patterns from official sources (auth, Fernet, proxy.ts, compose shown under Architecture Patterns):

### Async SQLAlchemy session + FastAPI dependency
```python
# Source: docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
```

### Alembic async env.py (the part everyone gets wrong)
```python
# Source: alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic
from sqlalchemy.ext.asyncio import async_engine_from_config

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section), prefix="sqlalchemy.")
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()
```
Note: alembic.ini needs the sync-style URL handled — simplest is setting `sqlalchemy.url` from `DATABASE_URL` in env.py at runtime so `.env` stays the single source (D-09).

### API Dockerfile with uv (dev-oriented)
```dockerfile
# Source: docs.astral.sh/uv/guides/integration/docker/
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY . .
RUN uv sync --frozen --no-dev
EXPOSE 8000
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
```

### Functional test shape (D-02 — live app, real Postgres)
```python
# Source: python-httpx.org/async/ — tests target the RUNNING compose/hybrid stack
import httpx, pytest

BASE = "http://localhost:8000"

@pytest.fixture
async def authed_client():
    async with httpx.AsyncClient(base_url=BASE) as client:
        r = await client.post("/api/auth/login",
                              json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200          # cookies now held by the client
        yield client

async def test_register_target_credentials_never_returned(authed_client):
    r = await authed_client.post("/api/targets", json={
        "name": f"saucedemo-{uuid4().hex[:8]}", "base_url": "http://localhost:8080",
        "credentials": {"username": "standard_user", "password": "secret_sauce"},
    })
    assert r.status_code == 201
    body = r.json()
    assert "secret_sauce" not in r.text and "credentials" not in body
    assert body["has_credentials"] is True
```

### structlog redaction processor
```python
# Source: structlog docs processor pattern — www.structlog.org/en/stable/processors.html
SENSITIVE = re.compile(r"password|passwd|secret|credential|token", re.I)

def redact_sensitive(logger, method_name, event_dict):
    for key in list(event_dict):
        if SENSITIVE.search(key):
            event_dict[key] = "[REDACTED]"
    return event_dict
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `middleware.ts` / exported `middleware()` | `proxy.ts` / exported `proxy()` (nodejs runtime only) | Next.js 16 (Oct 2025) | Scaffold uses proxy.ts; middleware.ts logs deprecation warnings [VERIFIED: nextjs.org/docs/messages/middleware-to-proxy] |
| webpack dev server (`WATCHPACK_POLLING` reliable) | Turbopack default in `next dev` | Next.js 15/16 | Containerized hot-reload on Windows regressed; hybrid host mode is primary DX (Pitfall 1) |
| `tailwind.config.js` | CSS-first `@theme` config via `@tailwindcss/postcss` | Tailwind v4 | shadcn init handles it; don't create a JS config |
| passlib for hashing | argon2-cffi directly | passlib unmaintained (per STACK.md) | Already locked |
| python-jose | PyJWT | jose stagnant (per STACK.md) | Already locked |
| `version:` key in compose files | omitted (Compose Spec) | Compose v2 | Don't write `version: "3.x"` — it's obsolete and triggers warnings |
| Celery/worker for startup tasks | FastAPI lifespan context | FastAPI 0.93+ | Seed admin + engine lifecycle in lifespan, no extra moving parts |

**Deprecated/outdated:** NextAuth v4 / Auth.js v5-beta (banned by STACK.md); `docker-compose` v1 CLI (use `docker compose`); `@next/font` (built-in now).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | SauceDemo build needs node:16 (or `--openssl-legacy-provider`) to avoid OpenSSL 3 webpack failure | Pattern 5, Pitfall 9 | Low — first image build fails fast; fallback documented |
| A2 | Memory values chosen (api 1g, web 1536m, postgres 512m, redis 256m, saucedemo 128m) suffice for dev workloads | Pattern 1 | Low — tune from `docker stats`; limits too low manifest as OOM-kill restarts |
| A3 | SameSite=Lax + JSON-only API is adequate CSRF posture for localhost solo MVP | Pattern 2 | Medium if deployment model changes — flag to user before any network-exposed deployment |
| A4 | No server-side token revocation needed in Phase 1 (D-04 says client-side logout) | Pattern 2 | Low — Phase 10 revisits with RBAC |
| A5 | nginx `try_files $uri /index.html` SPA fallback required for SauceDemo client routing | Pattern 5 | Trivial — direct-URL navigation 404s would surface immediately in Phase 4 |
| A6 | Compose v5.1.3 may or may not enforce `deploy.resources.limits` non-swarm; `mem_limit` definitely works | Pattern 1, Open Q1 | Low — prescription sidesteps the ambiguity; verification step catches it |
| A7 | pytest-playwright UI tests run on the host (not in a container) against http://localhost:3000 | Validation Architecture | Low — containerized browsers come with Phase 7 workers |
| A8 | All package installs (slopcheck unavailable) — see Package Legitimacy Audit | Standard Stack | Very low — all packages pinned in approved STACK.md and registry-verified twice |

## Open Questions

1. **Does Compose v5.1.3 enforce `deploy.resources.limits` without swarm/--compatibility?**
   - What we know: Compose Spec documents the syntax; community sources and old issues say non-swarm needed `--compatibility`; modern Compose v2 implementations reportedly honor it, but no authoritative current statement found.
   - What's unclear: behavior of the exact installed version.
   - Recommendation: don't depend on it — use `mem_limit`/`cpus` (guaranteed) and verify with `docker inspect` as an explicit plan task. If the planner prefers spec-style `deploy.` keys, the verification step still arbitrates.

2. **Pin which upstream SauceDemo commit?**
   - What we know: repo is active master; `npm run build` produces a static `build/` dir.
   - Recommendation: at execution time, resolve current master SHA, build once, pin that SHA in the Dockerfile ARG. Treat "image builds and serves login page" as the acceptance check.

3. **uv workspace vs standalone apps/api project?**
   - What we know: only one Python project exists in Phase 1; `agents/` arrives Phase 2+.
   - Recommendation: standalone `apps/api` uv project now; promote to a uv workspace when the second Python package (Phase 2 `agents/llm` or `shared/events`) appears. Don't pre-build the workspace.

4. **Git repository does not exist yet** (working directory is not a repo despite `commit_docs: true`).
   - Recommendation: `git init` + initial commit (with `.gitattributes` and `.gitignore` covering `.env`, `workspaces/`, `node_modules/`) is part of plan 1's scaffold task.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Desktop | everything (INFRA-01) | ✓ | 29.4.3 | — |
| Docker Compose v2 | compose stack | ✓ | v5.1.3 | — |
| Node.js | apps/web host-mode, SauceDemo build | ✓ | 24.15.0 (≥20.9 OK for Next 16) | containers pin node:22 |
| npm | frontend deps | ✓ | 11.12.1 | — |
| Python | apps/api host-mode | ✓ | 3.13.13 (matches STACK.md 3.13.x) | — |
| uv | Python env mgmt | ✓ | 0.11.11 | — |
| git | repo init, SauceDemo clone in build | ✓ | 2.54.0.windows.1 | — |
| `.wslconfig` | Pitfall 9 memory caps | ✗ | — | **Create as Phase 1 task** (template + documented copy step) |
| Git repo in cwd | commit_docs workflow | ✗ | — | `git init` in scaffold task |

**Missing dependencies with no fallback:** none — all blocking tools installed.
**Missing dependencies with fallback:** `.wslconfig` (create it — explicitly part of INFRA-01 scope per PITFALLS.md Pitfall 9); git repo (init in first task).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.x + pytest-asyncio 1.4.x (`asyncio_mode = "auto"`) + httpx 0.28 (API functional) + pytest-playwright 0.8 / Playwright 1.60 (UI functional) |
| Config file | none — Wave 0 (`apps/api/pyproject.toml [tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/functional -x -q` (from `apps/api`, stack running) |
| Full suite command | `docker compose -f infra/docker-compose.yml up -d --wait && uv run pytest tests -q` |

D-02 mandate: tests are *functional* — they hit the running app over HTTP with real Postgres (no ASGITransport in-process shortcut, no DB mocking). UI tests run Playwright on the host against `http://localhost:3000`.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAT-03 | Login sets httpOnly cookies; bad password 401; authenticated request succeeds; refresh rotates access; logout clears | functional | `uv run pytest tests/functional/test_auth.py -x` | ❌ Wave 0 |
| PLAT-03 | UI: login form → redirected to /targets; unauthenticated visit to /targets → /login | e2e (Playwright) | `uv run pytest tests/e2e/test_login_ui.py -x` | ❌ Wave 0 |
| PLAT-01 | Register/edit/soft-delete target via API; listed; defaults applied (allowlist=origin, sandbox=false) | functional | `uv run pytest tests/functional/test_targets.py -x` | ❌ Wave 0 |
| PLAT-01 | UI: register target via dialog, appears in table, credentials field masked | e2e (Playwright) | `uv run pytest tests/e2e/test_targets_ui.py -x` | ❌ Wave 0 |
| PLAT-07 | Plaintext password absent from every API response; DB column is Fernet ciphertext (decrypt round-trip matches); captured logs contain no plaintext | functional | `uv run pytest tests/functional/test_credential_security.py -x` | ❌ Wave 0 |
| INFRA-01 | All default services healthy; dormant services absent; every container has non-zero memory limit | smoke (script) | `python infra/scripts/verify_stack.py` (wraps `docker compose ps --format json` + `docker inspect`) | ❌ Wave 0 |
| QUAL-04 | SauceDemo serves 200; `reset_target.py saucedemo` exits 0 and target healthy after | smoke (script) | `uv run pytest tests/functional/test_reset_target.py -x` | ❌ Wave 0 |

Manual-only checks (justified — host-level, not CI-able): `.wslconfig` applied (Vmmem bounded after `wsl --shutdown`); stack healthy after Windows reboot ("Looks Done But Isn't" item).

### Sampling Rate
- **Per task commit:** `uv run pytest tests/functional -x -q` (seconds against running stack)
- **Per wave merge:** full suite incl. e2e + smoke scripts
- **Phase gate:** clean-state run — `docker compose down -v && docker compose up -d --wait` then full suite green, then `verify_stack.py` (success criterion 1 evidence)

### Wave 0 Gaps
- [ ] `apps/api/pyproject.toml` pytest config (`asyncio_mode = "auto"`, markers `functional`, `e2e`)
- [ ] `apps/api/tests/conftest.py` — base URLs from env, authed-client fixture, table-truncate fixture
- [ ] `tests/functional/test_auth.py`, `test_targets.py`, `test_credential_security.py`, `test_reset_target.py` — written alongside their features (D-02), files created in each slice
- [ ] `tests/e2e/` Playwright tests + `uv run playwright install chromium` (one-time)
- [ ] `infra/scripts/verify_stack.py` — INFRA-01 evidence script

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | argon2-cffi (argon2id defaults), uniform 401 for unknown-user vs wrong-password, admin seeded from env (no default creds in code) |
| V3 Session Management | yes | PyJWT short-lived access (30 m) + refresh (7 d), httpOnly + SameSite=Lax cookies, refresh cookie path-scoped to `/api/auth`, `type` claim prevents refresh-as-access |
| V4 Access Control | partial | Single authenticated user; every non-auth route behind `get_current_user`. RBAC deferred to Phase 10 (locked scope) |
| V5 Input Validation | yes | Pydantic request models (URL validation on base_url, bounded budget overrides); zod on forms (UX duplicate) |
| V6 Cryptography | yes | Fernet (AES-128-CBC+HMAC, authenticated) via cryptography 48.x; MultiFernet for rotation; key from env only — never hand-roll, never log key |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Credential leak via logs/telemetry | Information Disclosure | structlog redaction processor + leak test capturing logs (PLAT-07's literal requirement) |
| Credential leak via API response | Information Disclosure | Response models structurally lacking credential fields; `test_credential_security.py` asserts |
| SQL injection | Tampering | SQLAlchemy parameterized queries only; no string-built SQL anywhere |
| CSRF on state-changing endpoints | Tampering | SameSite=Lax + same-origin rewrites + JSON bodies (A3 — revisit if network-exposed) |
| XSS stealing tokens | Information Disclosure | Tokens in httpOnly cookies (JS-unreadable); React's default escaping; no `dangerouslySetInnerHTML` |
| Secrets committed to git | Information Disclosure | `.env` gitignored from first commit; `.env.example` documents shape with placeholder values; Fernet key + JWT secret generated per-install |
| Encryption key in compose file | Information Disclosure | Compose references `${TARGET_CREDENTIAL_KEY}` from `.env`; never a literal in YAML |
| Timing-based user enumeration | Information Disclosure | argon2 verify against a dummy hash when user not found (cheap; do it) |

## Sources

### Primary (HIGH confidence)
- PyPI registry, queried live this session (`pip index versions`): cryptography 48.0.1, fastapi 0.136.3, pyjwt 2.13.0, argon2-cffi 25.1.0, watchfiles 1.2.0, pytest-playwright 0.8.0
- `.planning/research/STACK.md` — all other pins, verified live against PyPI/npm 2026-06-12 by upstream research
- [nextjs.org/docs/messages/middleware-to-proxy](https://nextjs.org/docs/messages/middleware-to-proxy) + [proxy file convention](https://nextjs.org/docs/app/api-reference/file-conventions/proxy) — middleware→proxy rename, nodejs runtime
- [github.com/saucelabs/sample-app-web](https://github.com/saucelabs/sample-app-web) README + raw Dockerfile — build process, static SPA, incomplete upstream Dockerfile
- [docs.docker.com/compose/compose-file/deploy/](https://docs.docker.com/compose/compose-file/deploy/) — deploy.resources syntax
- [uvicorn settings](https://www.uvicorn.org/settings/) + [Kludex/uvicorn#1893](https://github.com/Kludex/uvicorn/discussions/1893) — WATCHFILES_FORCE_POLLING
- Local environment probes this session (docker/compose/node/python/uv versions; `.wslconfig` absence)

### Secondary (MEDIUM confidence)
- [docker/compose#12827](https://github.com/docker/compose/issues/12827) + [vercel/next.js#71622](https://github.com/vercel/next.js/issues/71622) — Turbopack hot-reload failure in containers (open issues, multiple corroborating reports)
- Docker community forums / blog posts on non-swarm `deploy.resources.limits` enforcement (conflicting — drove the `mem_limit` prescription)

### Tertiary (LOW confidence — flagged)
- Node 16 / OpenSSL-legacy requirement for SauceDemo build (A1) — training-data pattern for old webpack, not verified against this repo's exact toolchain

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pre-pinned by approved STACK.md, double-verified on PyPI this session
- Architecture (auth, crypto, compose patterns): HIGH — canonical patterns from official docs; Next 16 proxy.ts verified
- Windows/Docker pitfalls: HIGH on file-watching (verified issues), MEDIUM on memory-limit enforcement detail (conflict, mitigated by prescription + verification step)
- SauceDemo specifics: MEDIUM — repo verified, build-toolchain age assumption flagged (A1)

**Research date:** 2026-06-12
**Valid until:** ~2026-07-12 (stable stack; Next.js minor releases are the fastest-moving piece)

---
*Phase: 1-Foundation & Dev Environment*
