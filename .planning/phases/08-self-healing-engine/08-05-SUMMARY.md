---
phase: 08-self-healing-engine
plan: 05
subsystem: api
tags: [self-healing, heal-stats, quarantine-api, heal-review, auth-gated-router, HEAL-04, D-05]

# Dependency graph
requires:
  - phase: 08-self-healing-engine
    provides: "plan 03 heal_audit model (element_key/before_chain/after_chain/confidence/outcome/reviewed_outcome) + ingest._apply_page_object_rewrite (ast-validated) + kg/writer.append_element_history (single writer)"
  - phase: 07-execution-engine-workers
    provides: "exec_history.py SQLAlchemy 2.0 select/func/group_by aggregation style + executions.py auth-gated APIRouter pattern (get_current_user)"
  - phase: 01-foundation
    provides: "app.core.security.get_current_user (cookie auth gate, 401 unauth)"
provides:
  - "apps/api/app/services/healing/stats.py — per_element_heal_stats: per-element heal-success + false-heal rates over heal_audit (HEAL-04)"
  - "apps/api/app/schemas/heal.py — HealAuditResponse (before/after diff + confidence, from_attributes) + HealStatsResponse"
  - "apps/api/app/routers/heals.py — auth-gated GET /api/heals + POST /{id}/apply + POST /{id}/reject + GET /api/heals/stats"
affects: [Phase 10 dashboards (the heal review SCREEN + heal-trend charts consume this API), Phase 9 defect agent (reviewed_outcome rejected feeds false-heal scoring)]

# Tech tracking
tech-stack:
  added: []  # ZERO new packages — existing SQLAlchemy/FastAPI/Pydantic + Plan-03 ingest reuse
  patterns:
    - "Per-element heal-stats: one SELECT with conditional case()/func.sum aggregations grouped by element_key (mirrors exec_history.py) — ORM-parameterized, no string-built SQL (T-08-19)"
    - "A rejected heal is a FALSE heal, never a success: heal_success_rate numerator excludes rows whose reviewed_outcome='rejected' (is_distinct_from, NULL-safe)"
    - "Divide-by-zero guard by construction: group_by yields only elements with >=1 attempt (zero-attempt elements absent); false_heal_rate guarded to 0.0 when auto_heal denominator is 0"
    - "Apply reuses the SAME Plan-03 ast-validated rewrite path (ingest._apply_page_object_rewrite) + single-writer KG append (ingest._append_kg_history) — NOT reimplemented (T-08-20/T-08-21)"
    - "Router-level Depends(get_current_user) gates EVERY endpoint incl. state-changing apply/reject (T-08-18); no require_role DI invented (RESEARCH A6)"
    - "In-process router test via httpx ASGITransport + app.dependency_overrides[get_current_user] — deterministic auth (401 + authed) with the real handlers over real Postgres, no live login round-trip"

key-files:
  created:
    - apps/api/app/services/healing/stats.py
    - apps/api/app/schemas/heal.py
    - apps/api/app/routers/heals.py
    - apps/api/tests/integration/test_heal_stats.py
    - apps/api/tests/integration/test_heals_router.py
  modified:
    - apps/api/app/main.py

key-decisions:
  - "Rule-1 fix: the list filter `status` default is 'quarantine' (the audit `outcome` vocabulary value), NOT the plan's past-tense 'quarantined' — the column stores 'quarantine', so the documented default would have matched zero rows. `status` is the outcome value bound directly via the ORM."
  - "heal_success_rate excludes rejected heals from the numerator (a rejected auto_heal keeps outcome='auto_heal' but reviewed_outcome='rejected') — so the plan's stated '8 auto_heal + 1 applied + 1 rejected -> 0.9' holds: 9 landed / 10 attempts."
  - "Apply resolves the run's pages dir as run_dir(heal.run_id)/target/pages (the Plan-03 ingest project_root layout) — run_id-derived, NEVER a request path (T-08-12 carry); the rewrite + KG append are reused verbatim from ingest, both tolerant/best-effort."
  - "Reject is a pure flag flip (reviewed_outcome='rejected') — quarantine STAGED the proposal in the audit row and wrote no file (Plan-03 Open Q3), so there is nothing to revert."
  - "HealAudit registered in main.py's noqa model-import block for Base.metadata/Alembic discovery (mirrors the other models); the table + migration already existed from Plan 03 (no new migration)."

metrics:
  duration: ~20min
  completed: 2026-06-27
---

# Phase 8 Plan 05: Per-Element Heal Stats + Quarantine Review API Summary

**The heal_audit ledger (Plan 03) is now aggregated into the two HEAL-04 rates and exposed for review through a MINIMAL auth-gated API (D-05 — API only, no UI): `per_element_heal_stats` computes per-element heal-success and false-heal rates with one ORM-parameterized `case()/func.sum` SELECT grouped by element_key (mirroring the Phase-7 execution-history queries), and `/api/heals` serves the quarantine queue with the before/after diff + confidence straight off the audit record — list / apply (the DEFERRED Plan-03 ast-validated page-object rewrite + single-writer KG append, then outcome=applied) / reject (reviewed_outcome=rejected, the false-heal signal) / stats — every endpoint router-level auth-gated via get_current_user.**

## Performance
- **Duration:** ~20 min
- **Tasks:** 2 (Task 1 tdd; Task 2 auto)
- **Files:** 6 (5 created, 1 modified)

## Accomplishments
- **Per-element heal stats (HEAL-04):** `per_element_heal_stats(db, *, element_key=None)` — one SELECT with conditional `case()/func.sum` aggregations grouped by `element_key` (mirrors `exec_history.pass_rate_trend`): `heal_success_rate = landed / attempts` (landed = outcome IN (auto_heal, applied) AND reviewed_outcome != 'rejected' — a rejected heal is a FALSE heal, never a success), `false_heal_rate = rejected_heals / auto_heals` (0.0 when there were no auto_heals). Zero-attempt elements are absent (group_by over existing rows only — no divide-by-zero). Optional `element_key` filter, element-ordered. ORM-parameterized (no f-string SQL).
- **Heal schemas:** `HealAuditResponse` (id, element_key, run/flow keys, before_chain, after_chain nullable, confidence, outcome, live_match_count, reviewed_outcome, created_at; `from_attributes=True` — the before/after diff renders from this ORM row) + `HealStatsResponse` (element_key, attempts, heal_success_rate, false_heal_rate).
- **Auth-gated quarantine API (D-05 / HEAL-03 review):** `app/routers/heals.py` — `APIRouter(prefix="/api/heals", dependencies=[Depends(get_current_user)])` so EVERY endpoint (especially state-changing apply/reject) 401s an unauthenticated request (T-08-18, V4). `GET ""` (default `status=quarantine`) → the quarantine queue with diff+confidence; `POST /{id}/apply` → reuses the Plan-03 ast-validated `ingest._apply_page_object_rewrite` on the run-id-derived pages dir + best-effort single-writer KG append, then `outcome='applied'` (404 unknown id); `POST /{id}/reject` → `reviewed_outcome='rejected'` (the HEAL-04 false-heal signal; quarantine wrote no file so it is a flag flip; 404 unknown id); `GET /stats` (`?element=<key>`) → `per_element_heal_stats`. `heal_id` is an int PK + `element` a string filter, both ORM-bound (no string-built SQL, T-08-19). Registered in `main.py` before `stubs_router` (mirrors kg/scenarios so the real routes win); `HealAudit` added to the model-discovery import block.
- **Deterministic, keyless tests:** `test_heal_stats.py` seeds heal_audit rows over the module SessionLocal and asserts the two rates (Element A: 8 auto_heal + 1 applied + 1 rejected → success 0.9, false_heal 1/9; Element B: quarantine + fail_as_defect → 0.0/0.0), the zero-attempt-element skip, the element filter, and `HealAuditResponse.model_validate` over an ORM row. `test_heals_router.py` drives the real app in-process via httpx ASGITransport: every endpoint 401s unauthenticated (parametrized GET/apply/reject/stats), and authed → list quarantine (diff+confidence), apply (outcome=applied + the page object's broken literal replaced by the healed selector, ast-valid), reject (reviewed_outcome=rejected), stats, and unknown-id → 404.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] list `status` default was the non-matching past-tense 'quarantined'**
- **Found during:** Task 2 (the authed list returned zero rows).
- **Issue:** the plan specified `GET ?status=quarantined` (default), but the heal_audit `outcome` vocabulary value is `quarantine` (no 'd'). The default filter `outcome == 'quarantined'` matched zero rows — the quarantine queue would always be empty.
- **Fix:** the `status` query param defaults to `'quarantine'` (the actual outcome value) and is matched directly against the `outcome` column via the ORM. The API now surfaces the staged proposals.
- **Files:** `app/routers/heals.py`, `tests/integration/test_heals_router.py`.
- **Commit:** `374020b`

**2. [Clarification - not a code change] heal_success_rate must exclude rejected heals**
- **Found during:** Task 1 (the test expected 0.9 but got 1.0).
- **Issue:** a rejected heal keeps `outcome='auto_heal'` (the reject API only flips `reviewed_outcome`), so a naive `outcome IN (auto_heal, applied)` numerator counted the rejected row as a success → 1.0, contradicting the plan's stated 0.9.
- **Fix:** the numerator excludes rows whose `reviewed_outcome='rejected'` (`is_distinct_from`, NULL-safe). Now 9 landed / 10 attempts = 0.9 exactly as the plan states. This is the correct reading of the plan's "8 auto_heal + 1 applied + 1 rejected → 0.9".
- **Files:** `app/services/healing/stats.py`.
- **Commit:** `bf2e729`

## Known Stubs
None — the stats aggregation + the four-endpoint review API are fully implemented and integration-tested. No heal UI is added (D-05 — API only; the review SCREEN + heal-trend dashboards are deferred to Phase 10, by design).

## Verification
- **Task 1:** `tests/integration/test_heal_stats.py` — **2 passed**; `grep -ciE 'select|func' stats.py` = 8 (>=1); no f-string SQL.
- **Task 2:** `tests/integration/test_heals_router.py` — **6 passed** (5 unauth-401 parametrized + the authed lifecycle); `grep -c 'heals' main.py` = 3 (>=1); no f-string SQL in heals.py; no `execute_write`/`tx.run` in the new files; no apps/web changes.
- **Heal integration suite together:** `test_heal_stats.py + test_heals_router.py + test_heal_ingest.py` — **13 passed**.
- **Single-write-path + no-LLM gates:** `test_single_write_path.py + test_no_llm_in_worker.py` — **3 passed** (SC1/SC3 stay green — apply routes its KG write through kg/writer; no LLM in the new modules).
- **Full deterministic suite** (`-m "not live_llm and not graph and not e2e"`): **429 passed, 9 failed, 46 deselected**. ALL 9 failures are `AMQPConnectionError [WinError 1225]` — the RabbitMQ broker is DOWN on this host right now (test_artifact_capture, test_determinism, test_execute_tier, test_inspec_heal, test_kill_drain, test_worker_consume — the same broker-dependent Phase-7 functional tests the 08-03 SUMMARY recorded as green only when the broker is up). NONE touch heals/stats; zero regressions from this plan.

## Threat Surface
All threat-register mitigations applied: T-08-18 (router-level get_current_user gates every endpoint incl. apply/reject — 5 parametrized 401 assertions), T-08-19 (heal_id int PK + element string filter ORM-bound, no string-built SQL — grep gate clean), T-08-20 (apply reuses the Plan-03 ast-validated `rewrite_page_object_locator` path — a non-parsing rewrite raises, never persisted), T-08-21 (apply's KG write-back routes through the single-writer `append_element_history` — single-write-path gate green). No new security surface beyond the threat model.

## Self-Check: PASSED

All 5 created + 1 modified files exist on disk; both task commits present in git history (bf2e729, 374020b).

---
*Phase: 08-self-healing-engine*
*Completed: 2026-06-27*
