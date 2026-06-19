---
phase: 05
plan: 03
subsystem: knowledge-graph
tags: [read-api, fastapi, auth-gate, nextjs, tanstack-query, zod, browse-ui, risk-badge, no-new-deps]
requires:
  - kg/reader.py list_pages/page_detail/element_repository/element_detail/graph_summary/flows_source (05-02)
  - kg/flows.py build_flows (05-02)
  - kg/risk.py risk_tier (05-02)
  - routers/executions.py read-router + router-level Depends(get_current_user) shape (03-02)
  - routers/stubs.py /flows + /coverage 501 handlers (03-04, removed here)
  - lib/api/client.ts same-origin /api wrapper + targets-table/targets page patterns (Phase 1)
  - components/app-sidebar.tsx NAV_ITEMS flat list (Phase 1)
provides:
  - app/schemas/kg.py (real KG read response models — FlowSchema w/ risk, CoverageResponse w/ measured, Page/Element/GraphSummary + detail)
  - app/routers/kg.py (read-only auth-gated GET /flows /coverage /graph /pages /elements + detail routes)
  - apps/web/lib/api/kg.ts (zod-at-boundary schemas + read fetchers)
  - the /graph browse section (Pages/Flows/Element repository views + Page/Flow/Element detail) + risk badge + view switcher + coverage stat
  - one "Knowledge graph" sidebar nav item
affects:
  - app/routers/stubs.py (flows()/coverage() 501 handlers removed; heal/create-defect/dashboard remain)
  - app/schemas/stub.py (dead FlowSummary/FlowsResponse/CoverageResponse seeds removed)
  - app/main.py (kg_router wired before stubs_router)
  - tests/functional/test_surface.py (PLAT-02 surface split updated: /flows + /coverage real, not stubs)
tech-stack:
  added: []
  patterns:
    - read-only router with router-level Depends(get_current_user) auth gate (V4 / T-05-09)
    - on-demand flow/coverage/graph computation in GET handlers (no write on read — single-write-path grep stays green)
    - honest coverage shape (measured=false until slice 04) — never a fabricated percent (D-08)
    - zod-at-boundary mirror of Pydantic response models (UX duplicate; Pydantic the authority)
    - tabular KG browse (NO graph-viz lib) reusing the targets-table structure verbatim
    - risk tier → --status-* token reuse; dot + mono score + tier WORD (WCAG 1.4.1, never color alone)
    - deep-linkable view switcher as composition over tokens (not a new tabs registry block)
    - percent-encoded element keys (# is a URL fragment char) on both client + {key:path} route
key-files:
  created:
    - apps/api/app/schemas/kg.py
    - apps/api/app/routers/kg.py
    - apps/api/tests/functional/test_kg_endpoints.py
    - apps/web/lib/api/kg.ts
    - apps/web/components/graph/risk-badge.tsx
    - apps/web/components/graph/graph-states.tsx
    - apps/web/components/graph/graph-shell.tsx
    - apps/web/components/graph/breadcrumb.tsx
    - apps/web/components/graph/pages-table.tsx
    - apps/web/components/graph/flows-table.tsx
    - apps/web/components/graph/elements-table.tsx
    - "apps/web/app/(dashboard)/graph/page.tsx"
    - "apps/web/app/(dashboard)/graph/flows/page.tsx"
    - "apps/web/app/(dashboard)/graph/elements/page.tsx"
    - "apps/web/app/(dashboard)/graph/pages/[fingerprint]/page.tsx"
    - "apps/web/app/(dashboard)/graph/flows/[id]/page.tsx"
    - "apps/web/app/(dashboard)/graph/elements/[key]/page.tsx"
    - apps/web/tests/e2e/kg-browse.spec.ts
  modified:
    - apps/api/app/routers/stubs.py
    - apps/api/app/schemas/stub.py
    - apps/api/app/main.py
    - apps/api/tests/functional/test_surface.py
    - apps/web/components/app-sidebar.tsx
decisions:
  - "Coverage endpoint returns the HONEST not-yet-measured shape (measured=false, zeros) this slice; the response MODEL is final and slice 04 swaps only the computed values + flag — routers/kg.py + schemas/kg.py are created here and EXTENDED (not blocked) by 05-04."
  - "kg_router included BEFORE stubs_router in main.py so its real /flows + /coverage win over any residual stub route."
  - "Element-detail keys are percent-encoded (encodeURIComponent on the client, quote(safe='') in the test) because element keys contain '#' (a URL fragment char) which silently truncates the path; the route uses {key:path} to accept the rest."
  - "Flows-view distinguishes 'no flows' from 'no graph' via GET /graph discovered flag (graph has nodes but mining produced none → no-flows; empty graph → no-graph)."
  - "Page-level list queries set retry:false so the inline error+Retry state renders immediately (react-query's default 3-retry backoff would otherwise hide the error past the e2e timeout)."
  - "Dead FlowSummary/FlowsResponse/CoverageResponse seed shapes removed from schemas/stub.py (superseded by schemas/kg.py; nothing imported them)."
metrics:
  duration: ~23min
  completed: 2026-06-19
---

# Phase 5 Plan 03: KG Read API + Tabular Browse UI Summary

Promoted the Phase-3 `GET /flows` + `/coverage` 501 stubs into REAL read-only, auth-gated endpoints and added `GET /graph`/`/pages`/`/elements` (+ page/flow/element detail) in a new `routers/kg.py` (computed on-demand via the slice-2 `kg/reader` + pure `kg/flows`), then built the `/graph` tabular browse section EXACTLY to 05-UI-SPEC — Pages / Flows (risk badges) / Element Repository with drill-in detail, honest coverage, and all empty/loading/error states — reusing only already-vendored shadcn (zero new deps, no graph-viz lib) plus one sidebar nav item.

## What Was Built

- **`schemas/kg.py`** — the real read response models: `FlowSchema`(risk_score 0-100 + risk_tier + signals), `FlowsResponse`, `FlowDetailSchema`(+ ordered `steps`), `CoverageResponse`(+ the honest `measured` flag), `PageSchema`/`PagesResponse`/`PageDetailSchema`(elements/forms/navigates_to), `ElementSchema`/`ElementsResponse`(locator_chain + locator_history), `GraphSummaryResponse`(counts + discovered). Field names aligned with the zod schemas.
- **`routers/kg.py`** — `APIRouter(prefix="/api", tags=["kg"], dependencies=[Depends(get_current_user)])` (router-level auth gate, V4/T-05-09). Read-only handlers: `GET /flows` (build_flows over the live graph, sorted risk-desc), `GET /flows/{flow_id}` (steps + risk breakdown), `GET /coverage` (honest measured=false until slice 4), `GET /graph` (label counts + discovered), `GET /pages` + `GET /pages/{fingerprint}`, `GET /elements` + `GET /elements/{key:path}`. No write-Cypher.
- **`stubs.py` / `stub.py` / `main.py`** — removed the `flows()` + `coverage()` 501 handlers (+ their imports + the dead seed shapes); left heal/create-defect/dashboard as honest 501s; wired `kg_router` before `stubs_router`.
- **`tests/functional/test_kg_endpoints.py`** — 401-unauth on every KG endpoint (8 parametrized, no graph) + a `/flows` `/coverage` non-501 check + seeded-graph shape assertions under `-m graph` (flows carry risk_score+risk_tier and sort risk-desc; coverage carries the `measured` flag; pages + graph summary; elements carry the deserialized chain + history; element-detail with a percent-encoded key).
- **Web `lib/api/kg.ts`** — zod schemas mirroring the Pydantic models + read fetchers (`listFlows`/`flowDetail`/`getCoverage`/`listPages`/`pageDetail`/`listElements`/`elementDetail`/`getGraphSummary`) over the same-origin `/api` client; keys `encodeURIComponent`'d.
- **Web components** — `risk-badge.tsx` (dot + mono score + tier WORD → `--status-fail/quarantine/pass/neutral`, unscored "—", breakdown tooltip); `pages-table` / `flows-table` (risk badge, default sort risk-desc, aria-sort) / `elements-table` (top-priority locator); `graph-states` (loading / no-graph / no-flows / no-elements / inline error+Retry incl. neo4j-down copy / stale Clock mark); `graph-shell` (header + honest coverage stat + deep-linkable view switcher); `breadcrumb`.
- **Web routes** — `/graph` (Pages + coverage), `/graph/flows`, `/graph/elements`, and the three detail pages (`pages/[fingerprint]`, `flows/[id]` with the **Risk breakdown** auditable section, `elements/[key]` with Locator chain + Locator history). One `Workflow` sidebar nav item → `/graph`.
- **`tests/e2e/kg-browse.spec.ts`** — mocked-API e2e (no backend/keys): tables render, risk badge shows score+word, coverage shows the mocked % and the "Not yet measured" state, the no-graph empty state, the inline error+Retry, and a drill-in navigation.

## Verification Results

- `tests/unit/test_single_write_path.py` — GREEN (2 passed): the router/schemas/reader add ZERO write-Cypher.
- `tests/functional/test_kg_endpoints.py -m "not graph"` — GREEN (8 passed): 401 unauth on every KG endpoint.
- `tests/functional/test_kg_endpoints.py -m graph` (under graph_mode, seeded graph) — GREEN (5 passed): flows risk + risk-desc sort; coverage `measured` flag; pages + page detail + graph summary; elements chain+history; element detail by percent-encoded key; the stub-removed (non-501) check.
- Full default backend gate `-m "not live_llm and not e2e and not graph"` — GREEN (229 passed, 31 deselected; was 226+2-failing before the surface-test fix).
- `cd apps/web && npx tsc --noEmit` — clean. `npx eslint app/(dashboard)/graph components/graph lib/api/kg.ts components/app-sidebar.tsx tests/e2e/kg-browse.spec.ts` — clean.
- `npx playwright test tests/e2e/kg-browse.spec.ts` — GREEN (6 passed) against the mocked API.
- `package.json` / `package-lock.json` unchanged — zero new frontend deps (D-05).
- graph_mode restored: web up + healthy, neo4j stopped (Pitfall 5).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Element-detail path broke on the '#' in element keys**
- **Found during:** Task 1 (graph endpoint test)
- **Issue:** Element keys look like `fp-inventory#button:Add to cart`. `#` is a URL fragment separator, so a raw `GET /api/elements/{key}` truncated the path at `#`, hitting the `{key:path}` route with only the fingerprint → 404.
- **Fix:** Percent-encode the key on every caller — `encodeURIComponent` in `lib/api/kg.ts` (and the drill-in `<Link>`s), `quote(safe='')` in the endpoint test. The route uses `{key:path}` to accept the decoded remainder.
- **Files modified:** apps/api/app/routers/kg.py (`{key:path}`), apps/api/tests/functional/test_kg_endpoints.py, apps/web/lib/api/kg.ts
- **Commit:** 9addd29 / d5ac30b

**2. [Rule 1 - Bug] Pre-existing surface test asserted the old /flows + /coverage 501 contract**
- **Found during:** post-task full default-gate run
- **Issue:** `test_surface.py` listed `/flows` + `/coverage` as STUB endpoints expecting authed→501; this slice intentionally made them real (authed→200/non-501), so those two parametrized cases failed.
- **Fix:** Moved `/flows` + `/coverage` to the REAL list (+ added `/graph`/`/pages`/`/elements`); shrank the STUB list to heal/create-defect/dashboard; updated the count assertion (10 real + 3 stub). Reflects the D-06 promotion.
- **Files modified:** apps/api/tests/functional/test_surface.py
- **Commit:** 8147456

**3. [Rule 3 - Blocking] retry:false on list queries so the error state renders**
- **Found during:** Task 2 (kg-browse e2e)
- **Issue:** react-query's default 3-retry exponential backoff kept the list queries in "loading" past the e2e's 5s assertion, so the inline error+Retry state never appeared in time.
- **Fix:** Set `retry: false` on the page-level list queries (these are static read snapshots; the UI-SPEC error state owns retry via the manual Retry button, not auto-retry).
- **Files modified:** apps/web/app/(dashboard)/graph/page.tsx, flows/page.tsx, elements/page.tsx
- **Commit:** d5ac30b

## Known Stubs

- **Coverage is the honest not-yet-measured shape this slice** — `GET /coverage` returns `measured=false` + zeros and the Pages view renders "Not yet measured" (never a fabricated percent, D-08). This is INTENTIONAL and documented in the plan: slice 04 wires the real `kg/coverage.py` ground-truth metric, swapping only the computed values + the `measured` flag (the response model + the UI honest-state are final). `routers/kg.py` + `schemas/kg.py` are created here so 05-04 extends, not blocks.

## Requirements

- **KG-02** — complete. The user can query and tabularly browse the knowledge graph: `GET /flows` (with risk) / `/coverage` (honest) / `/graph` / `/pages` / `/elements` (+ detail) are real, read-only, and auth-gated (401 unauth); the `/graph` UI renders Pages / Flows (risk badges) / Element Repository with drill-in links, exactly to 05-UI-SPEC, with zero new deps and no graph-viz lib. (The live ≥80% coverage proof is QUAL-01 / slice 04, key-gated.)

## Threat Surface

No new surface beyond the plan's threat register. T-05-09 (router-level auth gate + 401-unauth tests on every endpoint), T-05-10 (React default escaping only; no dangerouslySetInnerHTML), T-05-11 (honest coverage — measured=false, never a fabricated 0%), T-05-12 (LIMIT on reader queries from slice 2; no auto-polling, manual Retry), T-05-SC (zero new deps; package.json + lock unchanged) all mitigated as planned.

## Self-Check: PASSED

- apps/api/app/schemas/kg.py — FOUND
- apps/api/app/routers/kg.py — FOUND
- apps/api/tests/functional/test_kg_endpoints.py — FOUND
- apps/web/lib/api/kg.ts — FOUND
- apps/web/components/graph/risk-badge.tsx — FOUND
- apps/web/app/(dashboard)/graph/page.tsx — FOUND
- apps/web/app/(dashboard)/graph/flows/[id]/page.tsx — FOUND
- apps/web/tests/e2e/kg-browse.spec.ts — FOUND
- commit 9addd29 (read API) — FOUND
- commit d5ac30b (browse UI) — FOUND
- commit 8147456 (surface test fix) — FOUND
