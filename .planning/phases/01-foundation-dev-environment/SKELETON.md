# Walking Skeleton — Autonomous QA Engineer Platform

**Phase:** 1
**Generated:** 2026-06-12

## Capability Proven End-to-End

A user runs `docker compose up`, logs in at `http://localhost:3000/login` with the env-seeded admin account, and lands on an authenticated `/targets` page — Next.js UI → rewrite proxy → FastAPI → argon2 verify against a seeded PostgreSQL row → httpOnly JWT cookies → protected route.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Backend framework | FastAPI 0.136.x (Python 3.13, uv-managed) on uvicorn 0.49 | Locked by STACK.md; lifespan hooks own engine/seed; OpenAPI is the frontend contract |
| Frontend framework | Next.js 16.2 App Router + React 19.2 + TypeScript 5.9 | Locked by STACK.md; `proxy.ts` (not middleware.ts) for route protection; rewrites make the API same-origin |
| Data layer | PostgreSQL 17 + SQLAlchemy 2.0 async + asyncpg + Alembic (single migration history, applied by API container entrypoint) | Locked by STACK.md; async end-to-end; `docker compose up` is self-migrating (D-08) |
| Cache/infra | Redis 8 (Phase 1: health-ping connectivity only) | Staggered activation (PITFALLS Pitfall 8); real use arrives with LLM caching in Phase 2 |
| Auth | Backend-issued PyJWT HS256 access (30 min) + refresh (7 d) in httpOnly SameSite=Lax cookies; argon2-cffi hashing; env-seeded admin, no signup (D-03/D-04) | NextAuth banned by STACK.md; web tier never holds the JWT secret |
| Secrets at rest | Fernet (`cryptography` 48.x, MultiFernet for rotation) for target-app credentials; key from env only; write-only API surface (D-06) | PLAT-07; response models structurally lack credential fields |
| UI system | shadcn/ui (new-york, zinc, CSS vars), Tailwind 4 CSS-first, dark-only theme, Geist fonts | Locked by 01-UI-SPEC.md (approved contract) |
| Deployment target | Docker Compose v2 on Windows 11/Docker Desktop — `docker compose up` from `infra/docker-compose.yml`; hybrid host mode (uvicorn/next dev on host, infra in Docker) is the primary iteration workflow (D-09, Turbopack/WSL2 watch limits) | INFRA-01; one command, healthchecks, per-container `mem_limit` |
| Test strategy | pytest 9 + httpx 0.28 functional tests against the LIVE stack (no in-process transport, no DB mocks); pytest-playwright e2e on host against :3000 (D-02) | Standing user directive — every feature ships with functional tests |
| Directory layout | Monorepo: `apps/api`, `apps/web`, `agents/`, `workers/`, `kg/`, `shared/events/`, `workspaces/` (stubs), `infra/` (compose, targets, scripts), `docs/` | research/ARCHITECTURE.md; later phases populate stubs without restructuring |

## Stack Touched in Phase 1

- [x] Project scaffold (monorepo, uv project, create-next-app, ruff/ESLint, pytest config)
- [x] Routing — `/login`, `/targets` (Next App Router); `/api/auth/*`, `/api/targets`, `/health` (FastAPI)
- [x] Database — real write (admin seed, target registration) AND real read (login verify, targets list)
- [x] UI — login form and target-registration dialog wired to the API through rewrites
- [x] Deployment — `docker compose -f infra/docker-compose.yml up -d --wait` brings up the full stack locally with healthchecks and memory limits

## Out of Scope (Deferred to Later Slices)

- RBAC / roles / user management UI — Phase 10 (PLAT-04)
- Server-side token revocation / denylist — Phase 10 (D-04: client-side logout only in Phase 1)
- LLM gateway, budgets, kill-switch — Phase 2
- Neo4j, RabbitMQ, Elasticsearch activation — compose profiles exist dormant; activated Phases 3/7/9
- Stateful demo target (OrangeHRM) with DB snapshot/restore — Phase 4
- Light theme, theme toggle — tokens are CSS variables; later phase
- Dirty-state confirmation on dialog cancel — documented UI-SPEC default

## Subsequent Slice Plan

- Phase 2: LLM gateway — every future agent call metered through one budget-enforced path
- Phase 3: Tracer bullet — explore → graph → scenario → spec → execution against SauceDemo
- Phase 4+: Explorer depth, KG, generation, execution, healing, defect intelligence, dashboards, ops
