---
phase: 10-dashboards-rbac-coverage-traceability
plan: 01
subsystem: auth
tags: [rbac, fastapi, dependency-injection, alembic, jwt, sqlalchemy, pydantic, postgres]

# Dependency graph
requires:
  - phase: 01-foundation-dev-environment
    provides: User model, get_current_user, JWT cookie auth, seed_admin, /me, alembic chain (0001-0009)
provides:
  - users.role column (admin|qa_lead|qa_engineer|developer) via reversible migration 0010
  - require_role(*roles) FastAPI dependency factory (reads role off the row, 403 on mismatch)
  - services/rbac.py static ROLE_PERMISSIONS map + can(role, cap) helper + endpoint->role matrix
  - admin-only GET /api/users + POST /api/users/{id}/role (self-demote 400, invalid 422, unknown 404)
  - GET /api/auth/me now returns the caller's role
affects: [10-02-dashboards, 10-03-coverage-traceability, 10-04-search, 10-05-ui-nav, rbac, dashboards]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "require_role(*roles) composes on get_current_user, reads role off the User row (no JWT claim)"
    - "static role->permission map (NOT a permissions table) — D-01 / CLAUDE.md 4-static-roles"
    - "router-level dependencies=[Depends(require_role('admin'))] deny-by-default gate"

key-files:
  created:
    - apps/api/alembic/versions/0010_user_role.py
    - apps/api/app/services/rbac.py
    - apps/api/app/routers/users.py
    - apps/api/tests/unit/test_require_role.py
    - apps/api/tests/unit/test_rbac_map.py
    - apps/api/tests/integration/test_role_assign.py
    - apps/api/tests/integration/test_migration_0010.py
  modified:
    - apps/api/app/models/user.py
    - apps/api/app/core/security.py
    - apps/api/app/schemas/auth.py
    - apps/api/app/routers/auth.py
    - apps/api/app/main.py

key-decisions:
  - "Role read OFF THE ROW per request (D-01/A1), never baked into the JWT — no stale-role window; create_token untouched"
  - "users.role NOT NULL with server_default='admin' so the existing seeded admin row is valid with no data backfill"
  - "RoleAssignRequest is a Literal of the four roles — invalid role 422s at the schema boundary before any DB write"
  - "Self-demote guard returns 400 before the target lookup — the only admin can never lock themselves out"

patterns-established:
  - "require_role(*roles) factory: the canonical RBAC gate Plans 02-05 reuse via router-level dependencies"
  - "endpoint->role matrix documented as a comment block in rbac.py — the single reference for downstream gate wiring"

requirements-completed: [PLAT-04]

# Metrics
duration: ~30min
completed: 2026-06-28
---

# Phase 10 Plan 01: RBAC Foundation Summary

**Four-role RBAC: a `users.role` column (migration 0010) read off the row by a `require_role(*roles)` FastAPI dependency, a static role→permission map, an admin-only role-assignment API with a self-demote lockout guard, and the role surfaced on `/me`.**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-06-28
- **Tasks:** 3 (all TDD: RED→GREEN)
- **Files modified:** 12 (7 created, 5 modified)

## Accomplishments

- `users.role` String(16) column (`admin | qa_lead | qa_engineer | developer`) via reversible migration 0010 (`down_revision='0009'`), `server_default='admin'` so the seeded admin is an Admin with no data backfill; up/down/up round-trip proven.
- `require_role(*allowed)` dependency factory in `core/security.py` that composes on `get_current_user`, reads `user.role` off the row (never the JWT — T-10-03/04), and 403s a disallowed role.
- `services/rbac.py`: the static `ROLE_PERMISSIONS` map (D-01: Admin=all; QA Lead=manage+all dashboards+coverage+traceability+search; QA Engineer=run+QA dashboard+search; Developer=read+Dev dashboard+coverage+traceability+search), a pure `can(role, cap)` helper, and the documented endpoint→role matrix for Plans 02-05.
- Admin-only `GET /api/users` + `POST /api/users/{id}/role` (router-gated `require_role("admin")`): non-admin→403, self-demote→400, invalid role→422, unknown id→404; registered before `stubs_router`.
- `GET /api/auth/me` now returns `role` — the surface Plan 05's nav gating reads.

## Task Commits

1. **Task 1: role column + migration 0010 + seed_admin role + /me role** — `ba4e19f` (feat)
2. **Task 2: require_role DI + rbac.py static map + endpoint→role matrix** — `5923466` (feat)
3. **Task 3: admin-only users router (list + assign role) + registration** — `6c0aaf4` (feat)

_TDD tasks combined RED+GREEN into one commit each (the failing test and its implementation shipped together per atomic-task commit)._

## Files Created/Modified

- `apps/api/alembic/versions/0010_user_role.py` - adds `users.role` (server_default='admin', NOT NULL); reversible downgrade drops it.
- `apps/api/app/models/user.py` - `role: Mapped[str] = mapped_column(String(16), server_default="admin")`.
- `apps/api/app/core/security.py` - `require_role(*allowed)` factory (role off the row, 403 on mismatch).
- `apps/api/app/services/rbac.py` - static `ROLE_PERMISSIONS` + `can()` + the endpoint→role matrix.
- `apps/api/app/routers/users.py` - Admin-gated list + role-assign router.
- `apps/api/app/schemas/auth.py` - `MeResponse.role`, `UserSummary`, `RoleAssignRequest` (Literal of 4 roles).
- `apps/api/app/routers/auth.py` - `/me` returns `role=user.role`.
- `apps/api/app/main.py` - `seed_admin` sets `role="admin"`; `users_router` included before `stubs_router`.
- `apps/api/tests/unit/test_require_role.py` - allow/403 + role-off-row (5 tests).
- `apps/api/tests/unit/test_rbac_map.py` - the D-01 map contract (7 tests).
- `apps/api/tests/integration/test_role_assign.py` - 401/403/list/assign/self-demote/invalid/404 (8 tests).
- `apps/api/tests/integration/test_migration_0010.py` - up/down/up + admin-row='admin' + downgrade-drops (2 tests).

## Decisions Made

- **Role-on-row, not in-token** (D-01 / A1): `create_token` is unchanged; `require_role` reads `user.role` from the row `get_current_user` already fetches. A role change takes effect on the next request — no reissue, no stale-role window (mitigates T-10-03/04). This is the research-flagged deviation-with-rationale against CONTEXT's literal "JWT carries the role"; it is strictly safer and the planner's chosen reading.
- **server_default='admin'** on the NOT NULL column: existing rows (the seeded admin) become Admin with no data step (Pitfall 6); `seed_admin` also sets `role="admin"` explicitly so the intent is local to the seed.
- **RoleLiteral at the schema boundary**: invalid roles 422 before any handler logic runs; the body role is the value being ASSIGNED, never an authorization input.
- **Migration/role tests placed in `tests/integration/`** per the plan's verify commands (the existing 0009 analog lives in `tests/functional/`); both carry the skip-if-Postgres-down discipline.

## Deviations from Plan

None - plan executed exactly as written. No Rule 1-4 deviations were required; all interfaces matched the plan's `<interfaces>` block verbatim.

## Issues Encountered

- **Full-suite flake (out of scope):** During the `not live_llm and not e2e and not graph and not functional and not search` regression run, `tests/unit/test_classifier_evidence.py::test_gather_evidence_and_classify_product_failure` failed once with a Windows asyncio proactor teardown error (`'NoneType' object has no attribute 'send'` in `proactor_events.py` connection-lost). The test **passes cleanly in isolation** (2 passed) — it is a pre-existing Windows event-loop teardown race in an unrelated file (the classifier path, untouched by this plan), not a regression. Logged as out-of-scope per the SCOPE BOUNDARY rule; not fixed. Remaining suite: 429 passed.

## Known Stubs

None — every file is wired to real data/logic. No placeholder values, no TODO/FIXME, no empty data sources.

## Threat Flags

None — the plan's `<threat_model>` (T-10-01..06) is fully covered by this plan's surface; no new security surface beyond what the threat register anticipated was introduced.

## Verification

- All four plan test files green: `test_require_role.py` + `test_rbac_map.py` + `test_role_assign.py` + `test_migration_0010.py` → **22 passed**.
- Grep gates: `user.role` read off the row in `security.py` ✓; no `role` added to `create_token`/JWT (only the 403 detail string matches) ✓; `down_revision='0009'` exactly once in `0010_user_role.py` ✓.
- `alembic current` → `0010 (head)`; reversible up/down/up confirmed by the migration test.
- Full deterministic suite: 429 passed, 1 out-of-scope Windows teardown flake (passes in isolation).

## Next Phase Readiness

- The RBAC gate (`require_role`), the static map (`rbac.ROLE_PERMISSIONS` + the endpoint→role matrix), and `/me` returning `role` are all ready for Plans 02-05 to wire dashboard/coverage/traceability/search routers and the role-gated frontend nav.
- Plans 02-05 should gate their routers per the documented matrix in `rbac.py`.

## Self-Check: PASSED

All 7 created files exist on disk; all 3 task commits (`ba4e19f`, `5923466`, `6c0aaf4`) are in the git log.

---
*Phase: 10-dashboards-rbac-coverage-traceability*
*Completed: 2026-06-28*
