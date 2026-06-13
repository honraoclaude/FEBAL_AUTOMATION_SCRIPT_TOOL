---
phase: 01-foundation-dev-environment
plan: 04
subsystem: web
tags: [nextjs-16, react-19, typescript-5.9, tailwind-4, shadcn, proxy-ts, rewrites, jwt-cookies, playwright-e2e, docker-compose]

# Dependency graph
requires:
  - phase: 01-foundation-dev-environment (plan 01-02)
    provides: api compose service on host port 8001 (container-internal 8000), live-HTTP test scaffolding
  - phase: 01-foundation-dev-environment (plan 01-03)
    provides: /api/auth/login|refresh|logout|me endpoints, httpOnly cookie contract, seeded admin (ADMIN_EMAIL/ADMIN_PASSWORD)
provides:
  - Next 16 web shell (apps/web) — dark zinc theme per locked 01-UI-SPEC, shadcn new-york/zinc components, Geist fonts
  - proxy.ts cookie-presence route protection (Next 16 convention, NOT middleware.ts)
  - next.config.ts rewrites /api/:path* -> API_URL (same-origin cookies; hybrid default http://localhost:8001)
  - lib/api/client.ts typed fetch wrapper with refresh-once-then-retry 401 handling (D-04), login/refresh exempt
  - Login page with uniform error state + silent refresh-on-mount session resume
  - App shell: 256px sidebar with NavItem contract ({icon,label,href} flat list), /api/auth/me email footer, log out
  - /targets stub page (header + empty state; plan 01-06 replaces body with real table)
  - web compose service (mem_limit 1536m, healthcheck, node_modules/.next volume-masks) — 4-service stack one-command healthy
  - tests/e2e/test_login_ui.py — 5 green Playwright tests (VALIDATION row PLAT-03/e2e)
affects: [01-05, 01-06, 01-07, 01-08]

# Tech tracking
tech-stack:
  added:
    [
      next 16.2.9, react 19.2.4, react-dom 19.2.4, typescript 5.9 (pinned),
      tailwindcss 4 (@tailwindcss/postcss), zod 4, "@tanstack/react-query 5",
      lucide-react 1, shadcn (14 official components), clsx, tailwind-merge,
      class-variance-authority, tw-animate-css, radix-ui, react-hook-form,
      "@hookform/resolvers", sonner, next-themes,
    ]
  patterns:
    [
      proxy.ts cookie-presence redirects (never an auth authority),
      same-origin API via Next rewrites (no CORS ever),
      refresh-once-then-retry 401 wrapper with per-request retried flag,
      manual components.json for shadcn (new CLI dropped style/base-color flags),
      permanent dark class + CSS-variable tokens for future light theme,
    ]

key-files:
  created:
    - apps/web/proxy.ts
    - apps/web/next.config.ts
    - apps/web/lib/api/client.ts
    - apps/web/app/login/page.tsx
    - apps/web/app/(dashboard)/layout.tsx
    - apps/web/app/(dashboard)/targets/page.tsx
    - apps/web/components/app-sidebar.tsx
    - apps/web/components/ui/* (16 files incl. registry deps sheet/tooltip)
    - apps/web/components.json
    - apps/web/app/globals.css
    - apps/web/Dockerfile
    - apps/web/.dockerignore
    - apps/api/tests/e2e/test_login_ui.py
  modified:
    - infra/docker-compose.yml (web service appended; no other service altered)

key-decisions:
  - "shadcn CLI 4.x removed init's style/base-color flags (preset picker only) — used the documented manual components.json path to honor the locked UI-SPEC preset (new-york/zinc/CSS variables) exactly"
  - "next.config.ts hybrid-mode rewrite fallback is http://localhost:8001 (not the plan-literal 8000) — applies the recorded 01-02 host-port decision; compose web container sets API_URL=http://api:8000 explicitly"
  - "shadcn components' registry-declared deps (radix-ui, react-hook-form, @hookform/resolvers, sonner, next-themes) treated as inside the approved set — they are what the approved official components install by definition"

patterns-established:
  - "Sidebar contract for later phases: flat NavItem[] = {icon: LucideIcon, label, href}; active state derived from route; append items only"
  - "All browser API calls go through the /api rewrite — components never see API hostnames or ports"
  - "Mutating auth state navigates with window.location.assign (full reload clears client caches); in-app success uses router.push/replace"

requirements-completed: [PLAT-03, INFRA-01]

# Metrics
duration: ~26min
completed: 2026-06-13
---

# Phase 01 Plan 04: Next 16 Web Shell + Login E2E (Walking Skeleton) Summary

**Dark-zinc Next 16 shell with proxy.ts route protection, same-origin /api rewrites, refresh-once-then-retry sessions (D-04), and a 1536m web container — 5 Playwright tests drive login through every tier of the 4-service stack**

## Performance

- **Duration:** ~26 min
- **Completed:** 2026-06-13
- **Tasks:** 3 (1 pre-approved human gate + 2 auto)
- **Files modified:** 48

## Accomplishments

- Walking skeleton proven end-to-end by browser automation: UI form → Next rewrite → FastAPI → Postgres → httpOnly cookie → protected page
- Full UI-SPEC §1/§2 contract shipped: exact copy strings ("Invalid email or password.", "Admin account is provisioned from environment configuration.", "Target Applications", "No target applications yet"), dark zinc palette hexes, Display 28px/600 login heading, 256px sidebar, lg (24px) content padding
- D-04 7-day session honored two ways: client wrapper refresh-once-then-retry on 401 (never loops — per-request retried flag), and login-page silent refresh-on-mount so an expired access cookie resumes without re-typing credentials (proven by e2e test 5)
- Four future status tokens (--status-pass/fail/quarantine/neutral) defined in globals.css @theme for Phase 5+ inheritance
- 4-service compose stack healthy under one command; web mem_limit verified at exactly 1610612736 bytes
- All 5 e2e tests green on first run (18.9s) against the containerized web tier; zero hardcoded credentials

## Task Commits

1. **Task 1: Package legitimacy gate** — no commit (pre-approved by user: "Approve all"; install matched the approved set)
2. **Task 2: Next 16 scaffold, login, route protection, app shell** - `c5c0b41` (feat)
3. **Task 3: Web Dockerfile + compose service + Playwright e2e** - `8be1d0f` (feat)

## Files Created/Modified

- `apps/web/proxy.ts` - cookie-presence redirects (no access_token → /login; cookie on /login → /targets); matcher excludes _next/favicon.ico/api
- `apps/web/next.config.ts` - rewrites /api/:path* → ${API_URL ?? http://localhost:8001}
- `apps/web/lib/api/client.ts` - typed JSON wrapper; 401 → POST /api/auth/refresh once → retry once → only then /login; login/refresh exempt
- `apps/web/app/login/page.tsx` - react-hook-form + zod; submitting spinner; uniform error keeps email/clears password; silent refresh probe on mount
- `apps/web/app/(dashboard)/layout.tsx` - QueryClientProvider + SidebarProvider + 24px main padding
- `apps/web/components/app-sidebar.tsx` - NavItem contract, accent active indicator, me-email footer, log out
- `apps/web/app/(dashboard)/targets/page.tsx` - page header + disabled "Register target" + empty state (01-06 replaces body)
- `apps/web/app/globals.css` - locked dark zinc tokens + @theme status tokens; permanent dark class set in app/layout.tsx
- `apps/web/Dockerfile` + `.dockerignore` - node:22-alpine dev image (npm ci, npm run dev)
- `infra/docker-compose.yml` - web service: 1536m, API_URL=http://api:8000, volume-masked node_modules/.next, healthcheck, depends_on api healthy
- `apps/api/tests/e2e/test_login_ui.py` - 5 sync-API Playwright tests incl. clear_cookies(name="access_token") refresh-resume proof

## Decisions Made

- **shadcn manual config path:** the latest shadcn CLI (4.x) replaced `init`'s style/base-color flags with an interactive preset picker (Nova/Vega/...). To honor the UI-SPEC's locked preset (new-york, zinc, CSS variables) non-interactively, components.json/lib/utils.ts/globals.css were written manually per shadcn's documented manual-installation path; `shadcn add` then worked non-interactively against that config.
- **Hybrid rewrite default 8001:** plan text showed the research-era default `http://localhost:8000`, but the recorded 01-02 decision moved the API's host port to 8001 — the fallback uses 8001 so host-mode `npm run dev` works without env vars (Next does not read the repo-root .env).
- **Registry-dependency interpretation of the package gate:** installing the approved components necessarily installs their registry-declared deps (radix-ui, react-hook-form, @hookform/resolvers, sonner, next-themes) plus registry-dependency components (sheet, tooltip, use-mobile). Treated as within the approved set since the user approved the components themselves; no new top-level packages beyond that were added.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] shadcn CLI flags from the plan no longer exist**
- **Found during:** Task 2 (`npx shadcn@latest init` step)
- **Issue:** Plan/UI-SPEC assumed `init` accepts style/base-color options; CLI 4.x only offers an interactive preset picker (defaults to "base-nova", not the locked zinc/new-york preset)
- **Fix:** Wrote components.json (new-york/zinc/cssVariables/lucide), lib/utils.ts, and the zinc dark globals.css manually per shadcn's documented manual install; installed base deps (clsx, tailwind-merge, class-variance-authority, tw-animate-css); `shadcn add` then ran non-interactively for all 14 components
- **Files modified:** apps/web/components.json, apps/web/lib/utils.ts, apps/web/app/globals.css
- **Commit:** c5c0b41

**2. [Rule 1 - Bug] Plan-literal hybrid rewrite port contradicted the recorded port decision**
- **Found during:** Task 2 (next.config.ts)
- **Issue:** Plan action text said default `http://localhost:8000`, but host 8000 belongs to an unrelated project (01-02 decision; STATE environment facts) — hybrid mode would proxy to the wrong app
- **Fix:** Fallback set to `http://localhost:8001` with an explanatory comment; compose container still sets API_URL=http://api:8000
- **Files modified:** apps/web/next.config.ts
- **Commit:** c5c0b41

**Total deviations:** 2 auto-fixed (1 tooling drift, 1 recorded-decision application)
**Impact on plan:** None on scope or contract; UI-SPEC preset delivered exactly despite the CLI change.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| "Register target" button disabled, no handler | apps/web/app/(dashboard)/targets/page.tsx | Intentional per plan — plan 01-06 wires the register dialog and real table |
| /targets body is empty-state copy only | apps/web/app/(dashboard)/targets/page.tsx | Intentional per plan — keeps the login redirect target real without scope creep; 01-06 replaces it |

Neither stub blocks this plan's goal (walking skeleton login flow), which is fully wired to live data.

## Issues Encountered

- create-next-app 16 now emits apps/web/AGENTS.md + CLAUDE.md agent-guidance stubs — committed as generated scaffold output.
- Pre-existing untracked runtime logs (alembic-run.log, uvicorn.log, verify-t2.log) and .claude/ remain out of scope (already logged in deferred-items for plan 01-08).

## User Setup Required

None — the stack self-builds; admin credentials already in .env.

## Next Phase Readiness

- Plan 01-05 (targets API) proceeds against the same auth contract; nothing here blocks it
- Plan 01-06 (targets UI) replaces the /targets stub body; sidebar/table/dialog/badge/skeleton components and the api client wrapper are ready
- Hybrid DX documented: `npm run dev` in apps/web on the host proxies to localhost:8001 with zero configuration; containerized web is the one-command promise (hot-reload in-container not promised — RESEARCH Pitfall 1)
- Exclusive-resource note honored: no other plan's compose/test commands ran during this plan

## Self-Check: PASSED

All 8 key artifact files exist on disk; commits c5c0b41 and 8be1d0f verified in git log; no unexpected file deletions in either commit; e2e suite 5/5 green against the live container.

---
*Phase: 01-foundation-dev-environment*
*Completed: 2026-06-13*
