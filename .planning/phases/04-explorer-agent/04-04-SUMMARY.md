---
phase: 04-explorer-agent
plan: 04
subsystem: fullstack
tags: [sse, live-progress, redis-pubsub, eventsource, cooperative-stop, screenshot-route, path-traversal, ui-spec, react, next16, playwright-e2e, explorer, EXPL-01]

# Dependency graph
requires:
  - phase: 04-explorer-agent (04-01)
    provides: "explorer/ package (nodes, graph, driver, ExplorerState + STOP_REASONS, run_id threading, refused feed lines, converge/act path)"
  - phase: 04-explorer-agent (04-03)
    provides: "act-node refusal feed lines (destructive / off-origin) that flow through feed_line"
  - phase: 01-foundation-dev-environment
    provides: "redis_client.get_redis() lifespan client; web design system (shadcn vendored), targets-table DropdownMenu + DeactivateDialog pattern, app-sidebar NAV_ITEMS, next.config rewrite, proxy.ts cookie gate, lib/api/client"
  - phase: 02/03 (llm gateway)
    provides: "per-run USD cost counter (llm:budget:run:{run_id}:usd)"
provides:
  - "shared/events.ExploreProgressEvent — the 11-field Pydantic-v2 live-progress contract (run_id, step, pages_found, actions_taken, current_url, current_title, screenshot_path, feed_line, cost_usd, elapsed_s, stop_reason); schemas-only, in __all__"
  - "explorer/progress.py — publish_progress (get_redis().publish to explore:{run_id}) + build_progress_event (cost_usd sourced from the gateway counter, D-06; screenshot reduced to run-relative basename, M-1)"
  - "explorer/nodes.check_cancel (L-3 loop-top cooperative stop) + per-step progress publish wired into converge; graph.py runs check_cancel as the loop entry/back-edge node"
  - "llm_gateway.get_run_cost_usd(run_id) — reads the per-run USD counter (single source of run spend)"
  - "routers/explore.py — GET /explore/{run_id}/events (EventSourceResponse over Redis pub/sub, snapshot-on-subscribe, finally-unsubscribe, auth-gated); GET /explore/{run_id}/screenshot/{name} (M-1, traversal-safe FileResponse PNG); POST /explore/{run_id}/stop (L-3 cancel flag)"
  - "Live Exploration View at app/(dashboard)/explore/[runId]/page.tsx — all 9 UI-SPEC states from the SSE stream; lib/api/explore.ts (zod boundary + startExplore/stopExplore/screenshotUrl); explore/ plain-composition components (counter-tile, feed-row, status-pill, terminal-banner)"
  - "targets Explore row-action + Explorations sidebar nav item; /explore index placeholder; first Playwright e2e harness for apps/web (mocked-SSE explore-live.spec.ts)"
affects: [05-knowledge-graph, 07-orchestration-durability, 08-self-healing]

# Tech tracking
tech-stack:
  added:
    - "@playwright/test 1.60.0 (devDependency, apps/web) — first frontend e2e harness"
  patterns:
    - "Redis pub/sub for live SSE fan-out (NEW Redis usage vs Phase 1-3 GET/SET/MGET) — reuses the SAME lifespan get_redis() client, never a second client"
    - "SSE = EventSourceResponse over a pubsub.listen() generator; current-state SNAPSHOT emitted first on (re)subscribe so reconnection reconciles without full replay; pubsub unsubscribed + closed in a finally (T-04-18)"
    - "Cooperative cancellation = a Redis flag (explore:cancel:{run_id}) read at the TOP of each LangGraph loop iteration by a dedicated check_cancel node, short-circuiting to stop_reason=stopped; flag cleared in the driver teardown finally (durable/forceful cancel deferred to Phase 7)"
    - "Path-traversal-safe file serving: reject any name with a separator/.., resolve within WORKSPACES_DIR/<run_id>, containment-check resolved target against the run base before FileResponse (T-04-17)"
    - "Live-view publish gated on a registered browser handle so the pure convergence unit harness (no browser, no Redis) never opens a cross-loop Redis connection"
    - "EventSource over the same-origin /api rewrite carries the httpOnly cookie automatically — no token handling in the page (consistent with lib/api/client.ts); proxy.ts cookie-presence gate satisfied in e2e via a placeholder access_token cookie"

# Key files
key-files:
  created:
    - apps/api/app/services/explorer/progress.py
    - apps/api/tests/functional/test_explore_events.py
    - apps/web/lib/api/explore.ts
    - apps/web/app/(dashboard)/explore/[runId]/page.tsx
    - apps/web/app/(dashboard)/explore/page.tsx
    - apps/web/components/explore/counter-tile.tsx
    - apps/web/components/explore/feed-row.tsx
    - apps/web/components/explore/status-pill.tsx
    - apps/web/components/explore/terminal-banner.tsx
    - apps/web/playwright.config.ts
    - apps/web/tests/e2e/explore-live.spec.ts
  modified:
    - shared/events/__init__.py
    - apps/api/app/services/explorer/nodes.py
    - apps/api/app/services/explorer/graph.py
    - apps/api/app/services/explorer/driver.py
    - apps/api/app/routers/explore.py
    - apps/api/app/services/llm_gateway.py
    - apps/api/tests/unit/test_explore_events.py
    - apps/web/components/targets/targets-table.tsx
    - apps/web/app/(dashboard)/targets/page.tsx
    - apps/web/components/app-sidebar.tsx
    - apps/web/.gitignore

# Decisions
decisions:
  - "L-2 stop_reason -> UI-state mapping lives in ONE function (mapStopReason): max_steps/max_depth/wall_clock/budget -> amber Budget reached; saturation/converged -> green Complete; failed -> red; stopped -> neutral — no terminal value falls through to no-banner"
  - "Progress publish is wired into the converge node (the step boundary that owns the new step counter + stop_reason) rather than a separate node, and is best-effort (never crashes the crawl)"
  - "build_progress_event takes cost_usd as an INPUT read from llm_gateway.get_run_cost_usd — the explorer NEVER computes spend (D-06)"
  - "The e2e is fully self-contained (mocks /api/auth/me + executions + the SSE stream + screenshots, sets the access_token cookie for proxy.ts) so it needs no backend and no provider keys — the live-exploration proof stays the manual phase gate"

# Metrics
metrics:
  duration: "~1h (continuation of an interrupted run)"
  completed: "2026-06-15"
  tasks: 3
  files_created: 11
  files_modified: 11
  commits: 3
  requirements: [EXPL-01]
---

# Phase 4 Plan 04: Live Exploration View (EXPL-01) Summary

Watchable live exploration end to end: the explorer publishes an `ExploreProgressEvent` to Redis pub/sub (`explore:{run_id}`) after each step, an auth-gated sse-starlette `EventSourceResponse` streams it (with a current-state snapshot on subscribe and finally-unsubscribe cleanup), and a new authenticated Next.js Live Exploration View consumes it via same-origin `EventSource`, rendering all 9 UI-SPEC states (connecting / running / reconnecting / converged / failed / budget / stopped / stream-lost / 404) with a 200-row feed cap, auto-scroll discipline, a ≤150ms screenshot cross-fade, and the full accessibility contract — plus a path-traversal-safe screenshot route (M-1), a cooperative Stop (L-3), the targets "Explore" row-action, and an "Explorations" sidebar item. Zero new shadcn components.

## What was built

**Task 1 — backend seam (commit ff8066d):**
- `ExploreProgressEvent` (11 fields, in `__all__`) — verified/kept the interrupted-run schema.
- `explorer/progress.py`: `publish_progress` (reuses the lifespan `get_redis().publish`) + `build_progress_event` (cost from the gateway counter, screenshot reduced to run-relative basename).
- `explorer/nodes.py`: `check_cancel` loop-top node (L-3) + per-step progress publish in `converge` (gated on a registered browser handle so the pure convergence harness never opens Redis).
- `explorer/graph.py`: `check_cancel` as the loop entry + back-edge node.
- `explorer/driver.py`: clears the cancel flag in teardown `finally`.
- `llm_gateway.get_run_cost_usd` — reads the per-run USD counter.
- `routers/explore.py`: SSE events route + M-1 traversal-safe screenshot route + L-3 stop route.
- Tests: 7 unit (event shape, publish, build, cancel) + 3 functional (SSE in-order, 401 unauth, screenshot 200/401/traversal-rejected/404).

**Task 2 — live page (commit b4572dd):**
- `lib/api/explore.ts` (zod `exploreProgressEventSchema`, `startExplore`, `stopExplore`, `screenshotUrl`).
- `components/explore/*`: counter-tile (aria-label value), feed-row (verb icons + amber refused rows with the meaning in TEXT not color), status-pill (`role="status"`, green pulse respecting reduced-motion), terminal-banner (exact UI-SPEC copy, 4 terminal variants + stream-lost).
- `explore/[runId]/page.tsx`: `EventSource` over the same-origin proxy; all 9 states; L-2 mapping; 200-row cap + "Showing the latest 200 steps"; "Jump to latest"; cross-fade screenshot via the M-1 URL; Stop confirm dialog (DeactivateDialog pattern); `role="log"` feed; on-mount `GET /executions` for the 404 state.

**Task 3 — entry points + e2e (commit fcd3762):**
- targets-table "Explore" item above Edit (disabled + tooltip when inactive); targets page wires `onExplore` -> toast -> navigate.
- app-sidebar "Explorations" item (lucide `Radar`); `/explore` index placeholder.
- First Playwright e2e harness for apps/web + `explore-live.spec.ts` (mocked SSE: counters, feed row, refused row, terminal banner).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] No Playwright e2e harness existed in apps/web**
- **Found during:** Task 3
- **Issue:** The plan instructed to "extend the existing Playwright e2e harness", but apps/web had no Playwright install, no `playwright.config.ts`, and no `tests/` directory — the Task 3 acceptance criteria (`npx playwright test tests/e2e/explore-live.spec.ts`) could not run.
- **Fix:** Installed `@playwright/test@1.60.0` (the canonical, CLAUDE.md-stack-named package — not a hallucinated name, so not subject to the package-legitimacy checkpoint) as a devDependency + chromium browser; created `playwright.config.ts` (dedicated :3100 dev server, self-contained mocks) and the spec. Added playwright artifact dirs to `.gitignore`.
- **Files:** apps/web/playwright.config.ts, apps/web/package.json, apps/web/package-lock.json, apps/web/.gitignore
- **Commit:** fcd3762

**2. [Rule 3 — Blocking] e2e redirected to /login (Next 16 proxy.ts cookie gate)**
- **Found during:** Task 3 e2e debugging
- **Issue:** `/explore/{runId}` (and all dashboard routes) 307-redirect to `/login` server-side when no `access_token` cookie is present — Next 16 replaces `middleware.ts` with `proxy.ts`, which does a coarse cookie-presence check.
- **Fix:** The e2e sets a placeholder `access_token` cookie via `context.addCookies` before navigating. The value is never verified (JWT secret lives in the API tier; every `/api` call is mocked), so a placeholder satisfies the presence gate.
- **Files:** apps/web/tests/e2e/explore-live.spec.ts
- **Commit:** fcd3762

**3. [Rule 1 — Bug] converge stop_reason path swallowed the live publish**
- **Found during:** Task 1
- **Issue:** The original `converge` returned early when `stop_reason` was already set (budget path), which would have skipped the per-step/terminal progress publish.
- **Fix:** Restructured the precedence block so `out["stop_reason"]` is set on every path and the publish runs once at the end (covering both running and terminal events).
- **Files:** apps/api/app/services/explorer/nodes.py
- **Commit:** ff8066d

### Auth gates
None — the SSE/screenshot/stop routes are cookie-gated by the existing router-level `Depends(get_current_user)`; the e2e mocks all auth. No interactive auth step was required.

## Known Stubs
None. All live-view data flows from the SSE stream (counters, feed, screenshot, cost from the gateway counter); no hardcoded/placeholder data feeds the UI. The `/explore` index is an intentional placeholder (run-less listing is out of scope this phase per UI-SPEC §3 — a future phase may add a listing).

## Verification
- Backend unit: `uv run pytest tests/unit/test_explore_events.py -q` -> 7 passed; full unit suite -> 145 passed.
- Backend functional (live stack): `uv run pytest -m functional tests/functional/test_explore_events.py` -> 3 passed (SSE in-order, 401 unauth, screenshot 200/401/traversal-rejected/404).
- Frontend: `npx tsc --noEmit` clean; `npx eslint` on all touched paths clean; `npx playwright test tests/e2e/explore-live.spec.ts` -> 1 passed.
- Zero new shadcn: no `components/ui/` diff; no `shadcn add` references in apps/web.
- Manual (phase gate, deferred): under graph_mode with provider keys, start a real exploration from the targets row and watch the live view — counters/feed/screenshot update live; terminal banner renders on convergence.

## Self-Check: PASSED
- All 10 created files verified present on disk.
- All 3 task commits (ff8066d, b4572dd, fcd3762) verified in git log.
