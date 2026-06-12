# Phase 1: Foundation & Dev Environment - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Stand up the platform skeleton locally with one command: Docker Compose core (PostgreSQL + Redis active; all other services as dormant profiles), FastAPI backend with email/password login (JWT), encrypted target-app registry reachable via API and a Next.js UI shell, and a self-hosted snapshot-restorable demo target (SauceDemo). Requirements: PLAT-01, PLAT-03, PLAT-07, INFRA-01, QUAL-04.

NOT in this phase: RBAC roles (Phase 10), LLM gateway (Phase 2), any exploration/generation/execution capability (Phases 3+), Neo4j/RabbitMQ/Elasticsearch activation.

</domain>

<decisions>
## Implementation Decisions

### Process directive (user-locked)
- **D-01:** [informational] User delegated implementation decisions to Claude: "If you are clear what needs to be done we can start building in loop and keep developing." Build iteratively — after context, proceed to plan and execute without further discussion rounds; keep momentum phase to phase.
- **D-02:** **Every feature ships with functional tests.** This is a standing directive for ALL phases, not just Phase 1. For Phase 1: API features get pytest functional tests (httpx AsyncClient against the running FastAPI app, real Postgres via the compose stack); UI flows (login, target registration) get Playwright functional tests. Tests are written alongside each feature, not deferred to a testing phase.

### Account bootstrap & login (Claude's discretion, applied)
- **D-03:** First admin user is seeded from environment variables (`ADMIN_EMAIL` / `ADMIN_PASSWORD`) on first startup; no public signup page (solo-user deployment; RBAC and user management arrive in Phase 10).
- **D-04:** JWT access token (short-lived, ~30 min) + refresh token (~7 days) delivered as httpOnly cookies; passwords hashed with argon2. Logout invalidates the session client-side and clears cookies.

### Target-app registration (Claude's discretion, applied)
- **D-05:** v1 registration fields: name, base URL, one credential set (username/password), and exploration rules: origin allowlist (defaults to the base-URL origin), sandbox flag (marks target as restorable — gates destructive actions in Phase 4; default false), and optional budget overrides (max steps / depth / wall-clock / token spend) over global defaults.
- **D-06:** Credentials are write-only through the API: accepted on create/update, never returned in any response, masked in the UI. Encrypted at rest via app-level symmetric encryption (Fernet) with the master key supplied via environment variable — never committed.
- **D-07:** Targets support edit and soft-delete (deactivate) so historical exploration/execution data keeps its foreign keys in later phases.

### Dev workflow & compose (Claude's discretion, applied)
- **D-08:** `docker compose up` is the one command: brings up Postgres, Redis, the FastAPI API, and the Next.js web shell with healthchecks and per-container memory limits (success criterion). Dormant services (Neo4j, RabbitMQ, Elasticsearch, MinIO-equivalent stores if any) exist only as compose profiles, not started by default.
- **D-09:** A documented hybrid dev mode also exists for fast iteration: infra in Docker, API (uvicorn --reload) and web (next dev) on the host. Both modes share the same `.env` configuration.

### Demo targets & snapshots (Claude's discretion, applied)
- **D-10:** Phase 1 ships SauceDemo (Sauce Labs sample-app-web) self-hosted in Docker as the first demo target. It is stateless, so snapshot/restore = container restart — but the snapshot/restore contract (a script/API: `reset-target <name>`) is defined generically now so a stateful target (OrangeHRM) can plug in at Phase 4 when the Explorer needs it.

### Claude's Discretion
User explicitly delegated all four presented gray areas (account bootstrap, target registration shape, dev workflow, demo targets). Decisions D-03 through D-10 are Claude's picks grounded in `.planning/research/` — planner may refine details but must not contradict them without surfacing the change.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Stack & versions
- `.planning/research/STACK.md` — pinned library versions and patterns (FastAPI 0.136, SQLAlchemy 2.0 async, PyJWT + argon2-cffi, Next.js 16 + shadcn/ui, redis 8.0); what NOT to use

### Architecture & structure
- `.planning/research/ARCHITECTURE.md` — two-plane architecture, monorepo layout (apps/api, agents/, workers/, kg/, shared/events/, workspaces/), component boundaries
- `.planning/research/PITFALLS.md` — Pitfall 8 (infra over-engineering) and Pitfall 9 (Windows 11/Docker Desktop resource limits: .wslconfig caps, per-container memory limits) directly constrain this phase

### Scope & requirements
- `.planning/REQUIREMENTS.md` — PLAT-01, PLAT-03, PLAT-07, INFRA-01, QUAL-04 definitions
- `.planning/ROADMAP.md` — Phase 1 success criteria (5)

</canonical_refs>

<code_context>
## Existing Code Insights

Greenfield — no code exists yet. This phase establishes the monorepo structure that all later phases build on (apps/api, apps/web, agents/, kg/, workers/, shared/, workspaces/, infra/ per ARCHITECTURE.md).

### Integration Points
- Compose profiles defined now are activated by later phases (Neo4j in Phase 3/5, RabbitMQ in Phase 7, Elasticsearch in Phase 9)
- Target-app registry schema (including sandbox flag and budget overrides) is consumed by the Explorer in Phase 4
- The reset-target contract is consumed by execution reproducibility checks in Phase 7

</code_context>

<specifics>
## Specific Ideas

- "Start building in loop and keep developing" — user wants continuous build momentum with minimal ceremony between phases
- "Write functional test for each feature" — feature-level functional tests are a deliverable of every plan, standing for all phases

</specifics>

<deferred>
## Deferred Ideas

- Stateful demo target (OrangeHRM) with real DB snapshot/restore — Phase 4, when the Explorer needs realistic workflows
- User management UI / role assignment — Phase 10 (PLAT-04)

</deferred>

---

*Phase: 1-Foundation & Dev Environment*
*Context gathered: 2026-06-12*
