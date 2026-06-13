---
phase: 01-foundation-dev-environment
plan: 05
subsystem: api
tags: [targets, fernet, encryption, crypto, rbac-auth, soft-delete, sqlalchemy, alembic, pydantic, pytest]

# Dependency graph
requires:
  - phase: 01-foundation-dev-environment (plan 01-02)
    provides: settings.credential_keys, get_db, Base, async engine
  - phase: 01-foundation-dev-environment (plan 01-03)
    provides: get_current_user, authed_client fixture, seeded admin
provides:
  - /api/targets CRUD (POST/GET list/GET id/PATCH/DELETE) behind get_current_user
  - Fernet/MultiFernet encrypt/decrypt keyed from settings.credential_keys (app/core/crypto.py)
  - Target model + 0002_targets migration (encrypted_username/password LargeBinary, origin_allowlist, sandbox, budget_overrides, is_active, timestamps)
  - TargetResponse schema — structurally credential-free (has_credentials bool only)
  - target_service: single get_decrypted_credentials surface (Phase 4 Explorer input contract)
  - PLAT-07 credential-leak test suite (response / DB-ciphertext / logs)
affects: [01-06, 01-08, "Phase 4 Explorer (consumes target schema + get_decrypted_credentials)"]

# Tech tracking
tech-stack:
  added: []
  patterns: [encrypt-on-write in service layer, whitelist-by-omission response schema, single decrypt surface, router-level auth dependency, server-computed origin_allowlist default]

key-files:
  created:
    - apps/api/app/core/crypto.py
    - apps/api/app/models/target.py
    - apps/api/app/schemas/target.py
    - apps/api/app/services/target_service.py
    - apps/api/app/routers/targets.py
    - apps/api/alembic/versions/0002_targets.py
    - apps/api/tests/functional/test_targets.py
  modified:
    - apps/api/app/main.py
    - apps/api/alembic/env.py
    - apps/api/tests/functional/test_credential_security.py

key-decisions:
  - "Credential leak prevention is structural (TargetResponse has no credential fields) not filtered — whitelist by omission"
  - "Single decrypt surface (get_decrypted_credentials in target_service); grep-gated so decrypt cannot sprawl"

patterns-established:
  - "encrypt-on-write lives in the service layer, never the router"
  - "origin_allowlist defaults server-side to the base_url origin (scheme://host[:port])"
  - "functional tests use uuid-suffixed names and never assert global row counts (Pitfall 8)"

requirements-completed: [PLAT-07]

# Metrics
duration: ~15min active (executor interrupted by model-access error; finished inline on opus)
completed: 2026-06-13
---

# Phase 01 Plan 05: Encrypted Target Registry Summary

**/api/targets CRUD with Fernet write-only credentials — encrypted at rest, never in responses/DB-plaintext/logs, soft-delete + reactivate, all behind auth**

## Performance

- **Duration:** ~15 min active execution (split: executor wrote RED+GREEN then hit a model-access error; verification + commit + summary finished inline on opus)
- **Completed:** 2026-06-13
- **Tasks:** 2 (TDD: RED → GREEN)
- **Files modified:** 10

## Accomplishments
- 11 new functional tests green against the live stack (7 registry CRUD + 4 credential-security), full functional suite 19/19
- Fernet/MultiFernet encryption keyed from env; DB columns hold ciphertext, decrypt round-trips to original plaintext
- TargetResponse is credential-free by construction — `has_credentials` boolean only; the exact password string is absent from POST/GET/PATCH response bodies and from container logs
- Soft-delete (is_active=false) excludes from default list, surfaces under `?include_inactive=true`, and PATCH reactivates (D-07)
- Target schema carries the Phase 4 Explorer contract: origin_allowlist (server-defaulted), sandbox flag, budget_overrides

## Task Commits

1. **Task 1: Failing registry + credential-leak tests (RED)** - `1c346ca` (test)
2. **Task 2: Encrypted registry — crypto, model, migration, service, router (GREEN)** - `c72d857` (feat)

## Files Created/Modified
- `apps/api/app/core/crypto.py` - MultiFernet encrypt/decrypt from settings.credential_keys
- `apps/api/app/models/target.py` - Target model (encrypted binary creds, allowlist, sandbox, budgets, soft-delete)
- `apps/api/app/schemas/target.py` - CredentialsIn (input-only), TargetCreate/Update, credential-free TargetResponse
- `apps/api/app/services/target_service.py` - encrypt-on-write, single get_decrypted_credentials surface, soft-delete
- `apps/api/app/routers/targets.py` - CRUD behind router-level get_current_user
- `apps/api/alembic/versions/0002_targets.py` - targets table (down_revision chained to 0001)
- `apps/api/tests/functional/test_targets.py` + `test_credential_security.py` - PLAT-01/PLAT-07 specs

## Decisions Made
- None beyond plan — implemented per RESEARCH Pattern 3 and the `<interfaces>` contract exactly.

## Deviations from Plan

None - plan executed as written. Execution note: the spawning executor agent hit a transient model-access error after writing both commits' content (RED committed, GREEN staged-but-uncommitted); work was verified against all acceptance criteria and committed inline. No code deviations.

## Issues Encountered
- Executor model-access error mid-plan left the GREEN implementation staged but uncommitted. Resolved inline: restarted api container (ran 0002 migration), ran both suites (11/11) + full functional suite (19/19), confirmed schema/decrypt-surface acceptance criteria, then committed `c72d857`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Plan 01-06 (targets UI) consumes the /api/targets contract documented in the plan's `<interfaces>` block
- Phase 4 Explorer consumes the target schema and the single get_decrypted_credentials surface
- PLAT-01 is the API half only; marked complete once plan 01-06 delivers the UI half

---
*Phase: 01-foundation-dev-environment*
*Completed: 2026-06-13*
