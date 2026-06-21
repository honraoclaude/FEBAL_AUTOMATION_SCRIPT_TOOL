---
phase: 07-execution-engine-workers
plan: 04
subsystem: fullstack
tags: [execution-engine, live-view, sse, graceful-kill, drain, queue-purge, artifacts, path-traversal-guard, recharts, executions-ui, flaky-vs-failed, wcag, exec-06, d-07, keyless]

# Dependency graph
requires:
  - phase: 07-execution-engine-workers
    plan: 01
    provides: "worker/progress.py publish_test_event + build_counters; TestRun/TestResult/TestArtifact models; shared/events ExploreProgressEvent to mirror"
  - phase: 07-execution-engine-workers
    plan: 03
    provides: "routers/executions.py SINGLE owner of /api/executions (POST ''/GET ''/GET '/{run_id}'); exec_history.get_run_status + list_runs + trend queries; worker/job.py retry loop; run-relative multi-segment TestArtifact paths; I1 cookie-or-ci-token gate"
  - phase: 04-explorer-agent
    plan: 03
    provides: "Live Exploration View template (explore/[runId]/page.tsx), lib/api/explore.ts SSE zod + screenshotUrl, components/explore/{status-pill,counter-tile,terminal-banner}, the EventSource reconnect contract"
provides:
  - "shared/events.ExecutionProgressEvent: per-test live-progress model (absolute run counters + per-test delta) mirroring ExploreProgressEvent (committed in Task 1)"
  - "worker kill-flag drain (job.py reads run:{run_id}:kill BETWEEN attempts -> aborted, no SIGKILL) + exec_service.kill_run (set flag + aio-pika queue.purge) (Task 1)"
  - "routers/executions.py: GET /{run_id}/events (EventSourceResponse + current-counter reconnect snapshot W3), POST /{run_id}/kill, GET /{run_id}/artifacts/{flow_id}/{name:path} (multi-segment realpath containment guard) (Task 1)"
  - "lib/api/executions.ts: zod executionProgressEventSchema (1:1 with backend), listRuns/getRun/startRun/killRun, artifactUrl from run-relative segments, deriveTrends from server runs"
  - "Executions UI: /executions launcher (styled-native tier picker, zero new shadcn) + history table + Recharts trends; /executions/[runId] live per-test view (absolute counters, SSE snapshot reconnect, honest Stopping… draining) + terminal run-detail with auth-gated Screenshot/Trace/Video links"
  - "components/executions/{status-pill (stopping=amber),verdict-badge (flaky amber/failed red, WCAG words+icons),runs-table,trend-charts}"
  - "Executions sidebar nav entry (after Scenarios)"
affects: [07-05, 10]

# Tech tracking
tech-stack:
  added:
    - "recharts@^3.8.1 — the ONE sanctioned frontend dep (CLAUDE.md locked stack, the frontend analogue of aio-pika), gated + human-approved; pass-rate + duration trend charts"
  patterns:
    - "Per-test SSE seam mirrors the Phase-4 explorer: worker publishes ExecutionProgressEvent model_dump_json() to Redis exec:{run_id}; executions.py re-emits via EventSourceResponse; the live page parses with a zod schema (no fabricated/optimistic status crosses the boundary, T-07-17)"
    - "Current-counter reconnect snapshot (W3): _exec_snapshot_event builds the snapshot from the test_run row + test_results aggregate (build_counters) so a MID-RUN reconnect sees live counters — RICHER than explore's terminal-only snapshot"
    - "Graceful cooperative kill (D-07): exec_service.kill_run sets run:{run_id}:kill + connect_robust -> queue.purge (one-run-at-a-time assumption A6); the worker drains (remaining flows -> aborted, not product_failure); NO os.kill/SIGKILL (grep gate)"
    - "Multi-segment artifact route (B2): {name:path} converter; each segment of flow_id+'/'+name rejected if empty/./../backslash; realpath containment base/flow_id/name MUST stay under run_dir(run_id) (the flow_id segment participates) — adapted from explore.py's bare-filename guard, NOT copied"
    - "Styled-native discipline carried to the executions section: the tier picker is a token-styled native <select> (reusing input.tsx classes) and the progress bar is a role=progressbar div over --status-* tokens — ZERO new shadcn add (git diff confirms only recharts in package.json)"
    - "Flaky-vs-failed honesty (D-05, WCAG 1.4.1): verdict-badge renders flaky AMBER (--status-quarantine) and failed RED (--status-fail), each ALWAYS with its WORD + a distinct icon (never color-only); the runs-table results cell carries the words too"
    - "Trends DERIVED client-side from the server-authoritative runs list (deriveTrends) — the backend exposes no trends route and Task 1 finalized executions.py; the runs table is the source of truth, the Recharts cards are supplementary with sr-only/aria-label summaries"
    - "Artifact URLs built from run-relative segments via artifactUrl (mirrors screenshotUrl) — never a raw absolute path in the DOM; W4 renders ONE Trace link + 'console + network captured in the trace' note (no separate console/network links) and the honest 'Video captured on failure only.' for passed/flaky"

# Key files
key-files:
  created:
    - apps/web/lib/api/executions.ts
    - apps/web/app/(dashboard)/executions/page.tsx
    - apps/web/app/(dashboard)/executions/[runId]/page.tsx
    - apps/web/components/executions/status-pill.tsx
    - apps/web/components/executions/verdict-badge.tsx
    - apps/web/components/executions/runs-table.tsx
    - apps/web/components/executions/trend-charts.tsx
    - apps/web/tests/e2e/executions.spec.ts
  modified:
    - apps/web/package.json
    - apps/web/package-lock.json
    - apps/web/components/app-sidebar.tsx
    - shared/events/__init__.py
    - apps/api/app/services/worker/progress.py
    - apps/api/app/services/worker/job.py
    - apps/api/app/services/exec_service.py
    - apps/api/app/routers/executions.py
    - apps/api/tests/functional/test_live_exec.py
    - apps/api/tests/functional/test_kill_drain.py

# Decisions
decisions:
  - "Trends are derived client-side from the server runs list (deriveTrends) rather than adding a backend trends route — Task 1 finalized executions.py and the runs table is the WCAG source of truth; the chart stays supplementary"
  - "Artifact basenames follow the conventional Playwright per-test capture layout (test-failed-1.png / trace.zip / video.webm); artifactUrl builds the auth-gated run-relative URL the server's containment guard resolves"
  - "recharts elected over the native-sparkline fallback (human-approved gate) — it is the CLAUDE.md-locked chart lib for these dashboards; clean package.json diff (recharts only)"

# Metrics
metrics:
  duration: "continuation session (Tasks 2-3)"
  completed: 2026-06-22
  tasks_completed: 3
  files_created: 8
  files_modified: 10
---

# Phase 7 Plan 04: Executions Live View, Graceful Kill & UI Summary

A run is now WATCHABLE and STOPPABLE end-to-end: the worker publishes per-test progress over the Redis→SSE seam, the API (on `executions.py`, the single owner of `/api/executions`) re-emits via SSE with a current-counter reconnect snapshot and owns a graceful Redis-flag-drain-plus-queue-purge kill (no SIGKILL), and the Executions UI delivers the tier launcher, history + Recharts trends, the live per-test view with an honest "Stopping…" draining state, and a terminal run-detail with auth-gated Screenshot/Trace/Video links — all server-authoritative with flaky-vs-failed visually and textually distinct.

## What was built

**Task 1 (backend — committed `2b21c00` in the prior session):** the `ExecutionProgressEvent` per-test model in `shared/events`; the worker kill-flag drain in `job.py` (reads `run:{run_id}:kill` between attempts → `aborted`, never SIGKILL) + `progress.py` publish; `exec_service.kill_run` (set flag + `aio-pika` `queue.purge`); and the SSE/kill/multi-segment-artifact routes on `executions.py` with the current-counter reconnect snapshot (W3) and the realpath-containment artifact guard (B2). Proven by `test_live_exec.py` + `test_kill_drain.py` against the real queue-profile broker.

**Task 2 (gated dep — committed `bc47b9b`):** `recharts@^3.8.1` installed via npm after the human cleared the gate. `git diff apps/web/package.json` shows ONLY recharts added; transitives live in `package-lock.json`. No other frontend package added.

**Task 3 (Executions UI — committed `f15233c`):** the `/executions` launcher (styled-native tier picker, zero new shadcn) + history table (flaky amber / failed red, each with its word) + Recharts pass-rate & duration trend cards (derived from server runs, with accessible summaries); the `/executions/[runId]` live per-test view (absolute counters from the latest SSE frame, snapshot-driven reconnect, focus-trapped Kill dialog, the honest amber "Stopping…" draining state with a disabled Kill button — never a fake-instant kill) that freezes into the terminal run-detail (failures-first table, auth-gated Screenshot/Trace/Video links built from run-relative segments, the "console + network captured in the trace" note, the honest "Video captured on failure only." caption); the `components/executions` set; and the "Executions" sidebar entry after Scenarios.

## Verification

- `cd apps/web && npx tsc --noEmit` — clean.
- `cd apps/web && npx eslint "app/(dashboard)/executions" lib/api/executions.ts components/executions components/app-sidebar.tsx tests/e2e/executions.spec.ts` — clean (the parens path quoted so POSIX sh does not break, W2).
- `cd apps/web && npx playwright test tests/e2e/executions.spec.ts` — 8/8 green against the mocked API + SSE (no keys, no neo4j): launcher start-error, populated history (flaky amber + failed red with words), running per-test events → Stopping… draining on kill, terminal failed (Screenshot/Trace/Video only, no console/network link, video-on-failure caption), terminal killed, reconnecting, empty (no runs + no trends), 404.
- `cd apps/api && uv run pytest tests/unit/test_no_llm_in_worker.py -q` — green (cooperative-kill gate; no LLM in the worker).
- Zero new shadcn: `git status --short apps/web/components/ui/` is empty; the only `package.json` change is recharts.

## Deviations from Plan

**1. [Rule 3 - Blocking] Trends derived client-side instead of via a `getTrends()` backend route.**
- **Found during:** Task 3 (writing `lib/api/executions.ts`).
- **Issue:** the plan's Task 3 action mentions a `getTrends()` fetcher, but the backend exposes no trends route — `executions.py` (finalized and committed in Task 1) owns only POST/GET list/GET status/events/kill/artifacts, and the `pass_rate_trend`/`durations_by_flow` queries in `exec_history.py` are not wired to any endpoint. Adding a route would mean re-touching the Task-1-committed file outside this task's scope.
- **Fix:** `deriveTrends(runs)` computes the pass-rate and duration series from the server-authoritative runs list (each `TestRunResponse` carries `total/passed/failed` + `started_at`/`finished_at`). This keeps trends server-authoritative, honors the UI-SPEC "runs table is the source of truth, chart is supplementary" rule, and avoids a second owner of `/api/executions`.
- **Files modified:** `apps/web/lib/api/executions.ts`, `apps/web/components/executions/trend-charts.tsx`.
- **Commit:** `f15233c`.

## Known Stubs

None. Artifact URLs use the conventional Playwright per-test capture basenames (`test-failed-1.png` / `trace.zip` / `video.webm`) resolved against the server's run-relative containment guard — they are real auth-gated links, not placeholders. (A non-blocking note: the live per-test feed currently auto-orders by verdict rather than tracking a scroll-position "Jump to latest" affordance like the Phase-4 feed; a full suite is normally small enough that this is acceptable, and the absolute-counter contract is fully honored.)

## Self-Check: PASSED

- Created files verified present on disk: `lib/api/executions.ts`, `app/(dashboard)/executions/page.tsx`, `app/(dashboard)/executions/[runId]/page.tsx`, the four `components/executions/*` files, `tests/e2e/executions.spec.ts`.
- Commits verified in `git log`: `2b21c00` (Task 1), `bc47b9b` (Task 2 recharts), `f15233c` (Task 3 UI).
