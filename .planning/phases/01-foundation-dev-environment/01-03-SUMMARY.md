---
phase: 01-foundation-dev-environment
plan: 03
subsystem: auth
tags: [fastapi, pyjwt, argon2, httponly-cookies, alembic, tdd, functional-tests]

# Dependency graph
requires:
  - phase: 01-foundation-dev-environment (plan 01-02)
    provides: settings/get_db/SessionLocal/Base interfaces, async Alembic pipeline, live-HTTP test scaffolding, self-migrating api container
provides:
  - app/core/security.py — hash_password/verify_password (argon2id), create_token/decode_token (HS256 with type+jti claims), set/clear cookie helpers, get_current_user dependency
  - POST /api/auth/login, /refresh, /logout; GET /api/auth/me — live in the compose stack
  - users table (alembic 0001_users) with unique indexed email
  - Idempotent lifespan admin seed from ADMIN_EMAIL/ADMIN_PASSWORD (D-03)
  - tests/conftest.py authed_client + clean_targets fixtures (reused by 01-05/01-06)
  - tests/functional/test_auth.py — 7 green D-02 tests (VALIDATION row PLAT-03/functional)
affects: [01-04, 01-05, 01-06, 01-08]

# Tech tracking
tech-stack:
  added: [email-validator 2.3 (pydantic[email] extra), dnspython 2.8 (transitive)]
  patterns: [uniform-401 login (byte-identical bodies), dummy-hash timing pad on unknown email, type-claim token gate, refresh cookie path-scoped to /api/auth, TDD red-commit-then-green-commit]

key-files:
  created:
    - apps/api/app/models/user.py
    - apps/api/app/schemas/auth.py
    - apps/api/app/core/security.py
    - apps/api/app/routers/auth.py
    - apps/api/alembic/versions/0001_users.py
    - apps/api/tests/functional/test_auth.py
  modified:
    - apps/api/app/main.py
    - apps/api/alembic/env.py
    - apps/api/tests/conftest.py
    - apps/api/pyproject.toml

key-decisions:
  - "JWT claims include jti (uuid4) beyond the planned sub/type/iat/exp — iat has 1s resolution, so same-second access tokens would be byte-identical and refresh rotation unobservable"
  - "pydantic[email] extra added — plan-specified EmailStr requires email-validator (official pydantic extra at the pinned 2.13.* version)"
  - "Test data must avoid special-use TLDs (.invalid/.test): email-validator rejects them with 422 at the schema boundary before the handler"

patterns-established:
  - "Auth tests parse Set-Cookie headers directly (get_list) for flag assertions; cookie jars only for session-continuity assertions"
  - "Host-side DB access in tests: DATABASE_URL rewritten (+asyncpg stripped, postgres->localhost) via conftest _host_dsn()"
  - "New alembic versions or new dependencies require api image rebuild (--build); pure app/ changes do not (hot-reload mount)"

requirements-completed: [PLAT-03]

# Metrics
duration: ~12min
completed: 2026-06-13
---

# Phase 01 Plan 03: Auth Slice (JWT Cookie Login + Seeded Admin) Summary

**Email/password login with HS256 access(30m)/refresh(7d) httpOnly cookies, argon2id hashing, env-seeded idempotent admin, and uniform-401 anti-enumeration — pinned by 7 live-stack functional tests written red-first**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-06-13
- **Tasks:** 2 (TDD: RED then GREEN)
- **Files modified:** 13

## Accomplishments

- RED first (D-02 + failing-test-first): 7 functional tests committed failing with 404 before any implementation existed
- All 6 VALIDATION PLAT-03 behaviors green against the live compose stack: httpOnly+SameSite=lax cookies on login, byte-identical 401 for unknown-email vs wrong-password, cookie-only /me, refresh rotates the access cookie, logout expires both cookies, refresh token rejected in the access slot (type-claim gate)
- Admin seed verified idempotent: api restarted twice → log shows one `admin_user_seeded` then `admin_user_exists`; `SELECT count(*) FROM users` = 1
- Issued access token decoded: claims {sub:"1", type:"access", iat, exp} with exactly 30.0-minute expiry
- Log hygiene: full api container logs contain neither the plaintext admin password nor the JWT secret; login body is `{"ok":true}` only
- conftest now exposes `authed_client` (cookie-bearing) and `clean_targets` (asyncpg truncate, no-op until 01-05) for downstream plans

## Task Commits

1. **Task 1: Failing functional auth tests (RED)** - `b4a220d` (test)
2. **Task 2: User model, migration, seed, security core, router (GREEN)** - `356713e` (feat)

## Files Created/Modified

- `apps/api/app/core/security.py` - argon2id hash/verify, JWT mint/decode (type+jti claims), cookie set/clear helpers, get_current_user
- `apps/api/app/routers/auth.py` - login (uniform 401 + dummy-hash timing pad), refresh, logout, me
- `apps/api/app/models/user.py` / `apps/api/alembic/versions/0001_users.py` - users table, unique indexed email
- `apps/api/app/schemas/auth.py` - LoginRequest (EmailStr), MeResponse
- `apps/api/app/main.py` - auth router included; lifespan idempotent admin seed (D-03, Pitfall 7)
- `apps/api/alembic/env.py` - user model import for autogenerate
- `apps/api/tests/conftest.py` - dotenv fallback, ADMIN_* env, authed_client, clean_targets
- `apps/api/tests/functional/test_auth.py` - 7 live-HTTP tests (VALIDATION row PLAT-03/functional)
- `apps/api/pyproject.toml` / `uv.lock` - pydantic[email] extra

## Decisions Made

- Added `jti` (uuid4) claim to all tokens: with 1-second `iat` resolution, two access tokens minted in the same second would otherwise be byte-identical, making refresh rotation unobservable (and the rotation test flaky)
- `pydantic[email]==2.13.*` extra adopted for the plan-specified `EmailStr` (email-validator 2.3.0 + dnspython 2.8.0, both official ecosystem packages, installed cleanly)
- Unknown-email test data uses a normal-looking domain — email-validator rejects special-use TLDs (`.invalid`, `.test`) with 422 before the handler runs

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] EmailStr requires the email-validator package**
- **Found during:** Task 2 (schemas/auth.py)
- **Issue:** Plan specifies `LoginRequest{email: EmailStr}`; pydantic's EmailStr imports `email_validator`, which was not installed
- **Fix:** `uv add "pydantic[email]==2.13.*"` — the official pydantic extra at the already-pinned version (install succeeded first try; no package-legitimacy gate triggered)
- **Files modified:** apps/api/pyproject.toml, apps/api/uv.lock
- **Commit:** 356713e

**2. [Rule 1 - Bug] Unknown-email test used a special-use TLD**
- **Found during:** Task 2 GREEN run
- **Issue:** `nobody@example.invalid` returned 422 (EmailStr rejects special-use domains at the schema boundary), not 401 — undetectable in RED because the endpoint 404'd before validation
- **Fix:** Test data changed to `nobody@no-such-user-01-03.com` with an explanatory comment
- **Files modified:** apps/api/tests/functional/test_auth.py
- **Commit:** 356713e

**3. [Rule 1 - Bug] Same-second token mints would be byte-identical**
- **Found during:** Task 2 implementation (create_token)
- **Issue:** Planned claims {sub, type, iat, exp} have 1s resolution — login followed by refresh within the same second yields an identical access token, so "rotation" would be a no-op and the rotation test flaky
- **Fix:** Added standard `jti` (uuid4 hex) claim to create_token; acceptance-criteria claims sub/type/iat/exp still present and verified
- **Files modified:** apps/api/app/core/security.py
- **Commit:** 356713e

**Total deviations:** 3 auto-fixed (1 blocking dependency, 2 correctness)
**Impact on plan:** None on scope; interfaces contract delivered exactly as specified.

## TDD Gate Compliance

- RED gate: `b4a220d` `test(01-03)` — all tests failing with 404 against the live stack (no unexpected passes)
- GREEN gate: `356713e` `feat(01-03)` — 7/7 green, no test behavior weakened (only invalid test data corrected)
- REFACTOR: not needed; no cleanup commit

## Known Stubs

None — all endpoints are wired to the real users table and live cookies; no placeholder data paths.

## Issues Encountered

- Pre-existing untracked runtime logs (`alembic-run.log`, `uvicorn.log`, `verify-t2.log`) and `.claude/` at repo root — out of scope for this plan; logged to `deferred-items.md` for plan 01-08 cleanup.

## User Setup Required

None — admin credentials were already present in `.env` (ADMIN_EMAIL/ADMIN_PASSWORD); the stack self-migrated and self-seeded on rebuild.

## Next Phase Readiness

- Plan 01-04 (web shell) can build the login UI against live `/api/auth/*` endpoints; `authed_client` fixture available for e2e setup
- Plan 01-05 (targets) imports `get_current_user` from `app.core.security` to protect routes and uses `clean_targets` for test isolation
- Reminder for later plans: new alembic versions or dependencies need `up -d --build api`; pure `app/` edits hot-reload

## Self-Check: PASSED

All 6 key created/modified artifact files exist on disk; commits b4a220d and 356713e verified in git log.

---
*Phase: 01-foundation-dev-environment*
*Completed: 2026-06-13*
