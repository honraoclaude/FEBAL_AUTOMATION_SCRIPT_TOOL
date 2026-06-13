---
phase: 01-foundation-dev-environment
plan: 07
subsystem: infra
tags: [saucedemo, docker, nginx, spa, reset-target, demo-target, functional-tests, qual-04]

# Dependency graph
requires:
  - phase: 01-foundation-dev-environment (plan 01-02)
    provides: canonical compose invocation, functional-test scaffolding (functional marker, live-HTTP), api stack
  - phase: 01-foundation-dev-environment (plan 01-04)
    provides: full default-profile compose stack to append saucedemo to
provides:
  - Self-hosted SauceDemo demo target at http://localhost:8080 (own multi-stage build, pinned upstream SHA, default compose profile)
  - Generic reset-target <name> contract (infra/scripts/reset_target.py) — name->strategy registry, compose-restart strategy, health-poll, exit 0/1/2
  - QUAL-04 functional smoke suite (test_reset_target.py)
affects: ["Phase 4 Explorer (consumes saucedemo as first explore target + reset contract for stateful targets)", "Phase 7 reproducibility checks (consume reset-target exit-code contract)"]

# Tech tracking
tech-stack:
  added: [nginx:alpine (saucedemo serve stage), node:16-bullseye (saucedemo build stage)]
  patterns: [own multi-stage build over unusable upstream Dockerfile, SHA-pinned third-party build, name->strategy reset registry, stdlib-only host script, registry-key-as-argv-guard]

key-files:
  created:
    - infra/targets/saucedemo/Dockerfile
    - infra/targets/saucedemo/nginx.conf
    - infra/scripts/reset_target.py
    - apps/api/tests/functional/test_reset_target.py
  modified:
    - infra/docker-compose.yml

key-decisions:
  - "Healthcheck and reset health-poll both target 127.0.0.1, not localhost: inside the saucedemo container localhost resolves to ::1 (IPv6) but nginx listens on IPv4 0.0.0.0:80, so a localhost probe gets connection-refused."
  - "node:16-bullseye is the OpenSSL-3 (A1/Pitfall 9) mitigation by itself — the --openssl-legacy-provider flag is NOT set: node:16 ships OpenSSL 1.1.1 and rejects that flag in NODE_OPTIONS even for `npm ci`."

requirements-completed: [QUAL-04]

# Metrics
duration: ~12min active
completed: 2026-06-13
---

# Phase 01 Plan 07: SauceDemo Demo Target + Generic Reset Contract Summary

**Self-hosted, SHA-pinned SauceDemo serving on :8080 inside the one-command stack, plus a generic name->strategy `reset-target` contract (compose-restart now, db-snapshot-ready for Phase 4) exercised by green functional tests — QUAL-04 complete.**

## Performance

- **Duration:** ~12 min active execution
- **Completed:** 2026-06-13
- **Tasks:** 2 (both auto)
- **Files modified:** 5 (4 created, 1 modified)

## Accomplishments
- SauceDemo ("Swag Labs") self-hosted from our own multi-stage build (`node:16-bullseye` build → `nginx:alpine` serve), pinned to upstream commit `89b11dca1b11b5cae36966e34b8c902212670c9a` — not `master` (T-01-25 mitigation: reproducible, fixed revision, static-files-only image).
- saucedemo added to the **default** compose profile (no `profiles:` key) — comes up with `docker compose up`; `mem_limit` verified at 134217728 (128m exactly).
- nginx SPA fallback (`try_files $uri /index.html`) confirmed: an arbitrary deep route (`/some/deep/route`) returns 200, so Phase 4 exploration can hit client-side routes directly without 404s.
- Generic `reset_target.py <name>` contract: a `STRATEGIES` registry maps target name → strategy; the `compose-restart` strategy restarts the service then polls the health_url to 200 (60s cap); exit 0 success / 1 strategy-or-health failure / 2 unknown name. Compose path resolved relative to the script, so it runs from any cwd.
- 3 functional tests green against the live stack; full functional suite 22/22 (no regressions).

## Task Commits

1. **Task 1: SauceDemo image + compose service** — `58500ac` (feat)
2. **Task 2: Generic reset-target contract + functional test** — `7748eff` (feat)

## Files Created/Modified
- `infra/targets/saucedemo/Dockerfile` - own multi-stage build, `SAUCEDEMO_SHA` ARG default pinned to a real 40-char SHA
- `infra/targets/saucedemo/nginx.conf` - static SPA serve on :80 with `try_files $uri /index.html` fallback (A5)
- `infra/docker-compose.yml` - appended `saucedemo` service (build context, mem_limit 128m, 127.0.0.1 wget healthcheck, 8080:80, default profile); existing services untouched
- `infra/scripts/reset_target.py` - stdlib-only `reset-target <name>` registry + compose-restart strategy + health poll
- `apps/api/tests/functional/test_reset_target.py` - QUAL-04 smoke suite (serves 200; reset exits 0 + healthy; unknown name exits 2)

## Decisions Made
- **127.0.0.1 over localhost (container-internal probes):** inside the saucedemo container `localhost` resolves to `::1` (IPv6 only) while nginx listens on IPv4 `0.0.0.0:80`, so a `localhost` probe is connection-refused. Both the compose healthcheck and the reset script's `health_url` poll target IPv4 explicitly. (The reset script's `health_url` is `http://localhost:8080` — that is the *host-side* mapped port reached from the host, where localhost→127.0.0.1 works; only the in-container healthcheck needed the IPv4 fix.)
- **No `--openssl-legacy-provider`:** the pinned `node:16-bullseye` base IS the A1/Pitfall-9 mitigation (OpenSSL 1.1.1, no md4 removal). Setting the legacy-provider flag globally via `NODE_OPTIONS` makes node abort even for `npm ci`. The Dockerfile documents that the flag only becomes relevant if the base is ever bumped to Node 17+.

## Reset Contract — Honesty Note (RESEARCH Pattern 6)
SauceDemo's mutable state lives entirely in the browser's `localStorage`; a container restart resets nothing the *tests* observe. Real per-run isolation for SauceDemo comes from Playwright's fresh browser contexts. The `reset-target` contract still ships now because it is the generic seam that Phase 4 (stateful target OrangeHRM via a future `db-snapshot` strategy) and Phase 7 (reproducibility checks) plug into without changing the CLI or callers (D-10).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `--openssl-legacy-provider` aborted the build**
- **Found during:** Task 1 first build
- **Issue:** Plan/RESEARCH suggested `ENV NODE_OPTIONS=--openssl-legacy-provider` as the A1 fallback, set unconditionally. On `node:16` (OpenSSL 1.1.1) node rejects this flag in `NODE_OPTIONS` and exits 9 — even at `npm ci`.
- **Fix:** Removed the `ENV`; the pinned `node:16-bullseye` base is the actual OpenSSL mitigation. Documented in the Dockerfile that the flag is only relevant on a Node 17+ bump.
- **Files modified:** infra/targets/saucedemo/Dockerfile
- **Commit:** 58500ac

**2. [Rule 1 - Bug] In-container healthcheck got connection-refused on `localhost`**
- **Found during:** Task 1 first `--wait` (container reported unhealthy though nginx was up)
- **Issue:** Plan's healthcheck used `http://localhost:80`. Inside the container `localhost` resolves to `::1` (IPv6) but nginx listens IPv4-only, so `wget` → connection refused → unhealthy. (The nginx:alpine `10-listen-on-ipv6-by-default.sh` did not patch in an IPv6 listen for our custom config.)
- **Fix:** Healthcheck changed to `wget -q -O /dev/null http://127.0.0.1:80/`.
- **Files modified:** infra/docker-compose.yml
- **Commit:** 58500ac

---

**Total deviations:** 2 auto-fixed (both Task-1 environment/config bugs). No scope creep; no architectural changes.

## Out-of-Scope / Deferred
- Pre-existing untracked artifacts at repo root (`alembic-run.log`, `uvicorn.log`, `verify-t2.log`, `.claude/`) were present before this plan and are NOT created by it — left untouched, not committed. Candidate for a `.gitignore` sweep in a later housekeeping/docs plan (01-08), not this one.

## Authentication Gates
None.

## Known Stubs
None — both deliverables are fully wired and exercised by passing functional tests.

## User Setup Required
None — saucedemo builds and runs under the standard `docker compose ... up -d --build --wait`; no external service or credential configuration.

## Next Phase Readiness
- Phase 4 Explorer has its first concrete explore target (SauceDemo @ :8080) and the `reset-target` seam to add OrangeHRM's `db-snapshot` strategy without changing callers.
- Phase 7 reproducibility checks can invoke `reset-target <name>` and rely on its exit-code contract.
- Plan 01-08 remains (final phase plan; docs/gate per ROADMAP).

## Self-Check: PASSED

- All 4 created files present on disk (Dockerfile, nginx.conf, reset_target.py, test_reset_target.py)
- Both task commits present in git history (58500ac, 7748eff)

---
*Phase: 01-foundation-dev-environment*
*Completed: 2026-06-13*
