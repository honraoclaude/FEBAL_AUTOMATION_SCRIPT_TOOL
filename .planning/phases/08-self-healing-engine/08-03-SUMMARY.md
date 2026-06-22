---
phase: 08-self-healing-engine
plan: 03
subsystem: testing
tags: [self-healing, heal-as-commit, heal-audit, migration, kg-write-back, page-object-rewrite, worker-ingest]

# Dependency graph
requires:
  - phase: 08-self-healing-engine
    provides: "plan 02 per-flow heal-journal (element_key/before_chain/after_chain/confidence/outcome/live_match_count) + reconcile_verdict pure helper"
  - phase: 07-execution-engine-workers
    provides: "worker/job.run_flow_job fresh-session write block + _discover_artifacts ingest analog; classifier.classify_retry"
  - phase: 05-knowledge-graph-flow-learning
    provides: "kg/writer.py single write path (_write read-back guard) + kg/reader._loads tolerant parse; explorer/locators.merge_locator_history"
  - phase: 06-bdd-playwright-generation
    provides: "codegen page_object.py.j2 (self.<attr> = page.locator(<literal>)) + selector_gate ast sink-walk; codegen project _TARGET subtree"
provides:
  - "apps/api/app/models/heal_audit.py — HealAudit model (element_key, before/after chain JSON, confidence, outcome, live_match_count, run/flow keys, reviewed_outcome)"
  - "apps/api/alembic/versions/0008_heal_audit.py — heal_audit table migration chaining down_revision=0007"
  - "apps/api/app/services/healing/ingest.py — parse_heal_journal (tolerant bounded) + rewrite_page_object_locator (ast-validated, attr-keyed) + ingest_heal_journal (audit rows + rewrite + KG write-back)"
  - "apps/api/app/services/kg/writer.append_element_history — the single-writer KG Element-history append (parameterized + read-back guarded)"
  - "worker/job.run_flow_job wiring: post-subprocess ingest + reconcile_verdict inside the fresh session"
affects: [08-04 mutation harness (heal_audit false-heal rate), 08-05 heal review/apply API (reviewed_outcome + applied/rejected outcomes), Phase 9 defect agent (product_failure verdicts from fail_as_defect)]

# Tech tracking
tech-stack:
  added: []  # ZERO new packages — stdlib (ast/re/json) + existing SQLAlchemy/Alembic/neo4j writer
  patterns:
    - "Heal-as-commit (D-03, NOT git): three durable side-effects per heal — Postgres heal_audit row + ast-validated page-object locator rewrite + KG Element-history append"
    - "Line-targeted, attr-keyed page-object rewrite: regex anchored to self.<attr> = page.locator(<lit>); literal re-quoted via json.dumps; ast.parse guard before persist (T-08-10)"
    - "MED-3 element_key->page-module resolution by SCAN (strategy a): walk pages/*.py for the assignment line — no re-opening 08-02's journal/template"
    - "append_element_history MATCHes (never MERGEs) on key -> read-back 0-count RAISE surfaces a heal against an unknown element loudly; routed through the single _write (single-write-path gate green)"
    - "Tolerant bounded journal parse (mirrors kg/reader._loads): size cap + per-entry key/outcome/confidence validation; malformed/oversized entries skipped, never crash (T-08-09)"
    - "Best-effort KG write-back inside ingest (try/except over the writer call): a down/raising neo4j never crashes the worker — the audit row + rewrite persist regardless (T-08-14)"

key-files:
  created:
    - apps/api/app/models/heal_audit.py
    - apps/api/alembic/versions/0008_heal_audit.py
    - apps/api/app/services/healing/ingest.py
    - apps/api/tests/unit/test_page_object_rewrite.py
    - apps/api/tests/integration/test_heal_ingest.py
    - apps/api/tests/integration/test_heal_kg_writeback.py
  modified:
    - apps/api/app/models/__init__.py
    - apps/api/alembic/env.py
    - apps/api/app/services/kg/writer.py
    - apps/api/app/services/worker/job.py
    - apps/api/pyproject.toml

key-decisions:
  - "MED-3 resolved by SCAN (strategy a): _resolve_page_module walks pages/*.py for the single `self.<element_key> = page.locator(` line rather than threading the module name into the heal-journal — avoids re-opening the 08-02 in-spec template; the template's one-line-per-attr guarantee makes the scan unambiguous"
  - "ingest_heal_journal takes BOTH project_root (pages/ home, run_dir/<target>) and journal_dir (per-flow out_dir, run_dir/<flow_id>) explicitly — they are siblings under run_dir, both run_id-derived; passing them separately is cleaner + safer than deriving one from the other (T-08-12)"
  - "HealAudit.after_chain JSON(none_as_null=True) so a fail_as_defect (no healed chain) persists SQL NULL, not JSON 'null' — keeps the 'no after' state cleanly distinguishable when the before/after diff renders from the record"
  - "rewrite re-quotes the healed selector via json.dumps (always a valid escaped Python string literal) rather than string-concatenation — no raw journal/page text is ever spliced into code (T-08-10)"
  - "the rewrite swaps only the page.locator(<lit>) SINK line, not the _chains DATA dict (which carries the same value string) — the regex is anchored to `self.<attr> = page.locator(`, asserted by a fixture test"

metrics:
  duration: 26min
  completed: 2026-06-22
---

# Phase 8 Plan 03: Heal-as-Commit — heal_audit + Page-Object Rewrite + KG Write-Back Summary

**After the in-spec subprocess exits, the worker now ingests the per-flow heal-journal and performs the three durable side-effects of heal-as-commit (D-03, NOT git): one Postgres `heal_audit` row per entry (before/after chain + confidence + outcome — the auditable diff source), an ast-validated attr-keyed page-object locator rewrite for `auto_heal` ONLY, and a KG Element-history append through a NEW single-writer `append_element_history` (parameterized + read-back guarded) — all riding the worker's fresh session+commit, with the verdict reconciled so a journal'd heal becomes `auto_healed` (a heal is NOT a flake).**

## Performance
- **Duration:** ~26 min
- **Started:** 2026-06-22T22:43:16Z
- **Completed:** 2026-06-22T23:09:39Z
- **Tasks:** 3 (all type=auto; Task 1 tdd)
- **Files:** 11 (6 created, 5 modified)

## Accomplishments
- **HealAudit model + migration 0008 (HEAL-03):** `heal_audit` table (element_key, run_id, flow_id, before_chain/after_chain JSON, confidence Float, outcome String(16), live_match_count Integer, reviewed_outcome nullable for HEAL-04, created_at) mirroring the execution-history style; migration 0008 chains `down_revision='0007'` and round-trips cleanly (upgrade→0008 / downgrade→0007 / upgrade→0008). Chains are JSON, never blobs (T-08-13). Registered in `app/models/__init__.py` + `alembic/env.py`.
- **ast-validated page-object rewrite (T-08-10):** `rewrite_page_object_locator(source, *, element_key, new_selector)` — a line-targeted, attr-keyed replace anchored to the single `self.<attr> = page.locator(<literal>)` line the template guarantees; the new selector is re-quoted via `json.dumps` (always a valid escaped Python string literal — never raw text spliced into code) and the whole result is `ast.parse`-validated before return. An unknown key is a no-op; a non-parsing result raises (never persists broken source). Other attrs' literals and the `_chains` data dict are untouched (asserted by a multi-attr fixture test).
- **Single-writer KG append (T-08-11):** `kg/writer.append_element_history(*, key, history_json, chain_json, now, driver)` — `MATCH (e:Element {key:$key}) SET ... RETURN count(*) AS n`, parameterized ONLY, routed through the existing `_write` read-back guard so a 0-count (unknown key) RAISES loudly. The ONLY new graph write — the single-write-path grep gate stays green.
- **Tolerant journal ingest (T-08-09):** `parse_heal_journal(out_dir)` — bounded (1 MB file cap, 1000-entry cap, 255-char key cap, 50-entry chain cap) + per-entry validation (non-empty key, recognized outcome, numeric confidence); malformed/oversized/non-list payloads yield fewer-or-zero entries, never raise (mirrors `kg/reader._loads`). `ingest_heal_journal(db, run_id, flow_id, *, project_root, journal_dir, driver)` adds one `HealAudit` per valid entry (no commit — the worker owns it), rewrites the owning page object for `auto_heal` ONLY (MED-3 scan resolution), and appends KG history best-effort for `auto_heal`/`applied`.
- **Worker wiring + verdict reconcile (Pitfall 2/4):** `run_flow_job` calls `ingest_heal_journal` then `reconcile_verdict` INSIDE the existing fresh `SessionLocal` block — the HealAudit rows ride the SAME session+commit as the TestResult; a journal'd `auto_heal` makes the persisted verdict `auto_healed` (a heal is NOT a flake). SC3 NO-LLM worker gate stays green over the extended job.py.
- **Best-effort KG write-back (T-08-14):** the KG append is try/except-wrapped inside ingest — a down/raising neo4j during a keyless run never crashes the worker; the audit row + page-object rewrite persist regardless (proven by `test_ingest_best_effort_kg_writeback_with_raising_driver`).
- **Graph-marked KG proof:** `test_heal_kg_writeback -m graph` seeds an `:Element`, appends a healed `{step, chain}` snapshot via the single writer, and reads it back (new top chain + retained prior snapshot + bumped last_verified); an unknown key MATCHes nothing → the read-back guard RAISES.

## CHECKER MED-3 (ingest element_key→page-module mapping) — HONORED
Resolved by **strategy (a) — SCAN**: `_resolve_page_module(pages_dir, element_key)` walks `project_root/pages/*.py` for the single `self.<element_key> = page.locator(` assignment line (the page_object.py.j2 template guarantees exactly one such line per attr across the project). This avoids re-opening the 08-02 in-spec template/journal to thread a module name. Tested by `test_ingest_writes_audit_rows_and_rewrites_auto_heal_only`: the auto_heal entry's element resolves to `pages/inventory_page.py` and is rewritten; the quarantine entry's element is untouched.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ingest_heal_journal needed an explicit `journal_dir` param**
- **Found during:** Task 2 (wiring the ingest signature).
- **Issue:** the plan's signature passed only `project_root` (the pages/ home, `run_dir/<target>`), but the heal-journal lives at the sibling `run_dir/<flow_id>/heal-journal.json` (the in-spec layer's per-flow out_dir). A heuristic to derive one from the other would be fragile.
- **Fix:** added an explicit `journal_dir` keyword param; the worker passes `journal_dir=out_dir` (the per-flow dir it already computed for `_discover_artifacts`) and `project_root=run_dir(run_id)/_TARGET`. Both are run_id-derived (T-08-12).
- **Files:** `app/services/healing/ingest.py`, `app/services/worker/job.py`.
- **Commit:** `c6a9c9c` / `3218c76`

**2. [Rule 1 - Bug] after_chain persisted JSON 'null' instead of SQL NULL for fail_as_defect**
- **Found during:** Task 2 (the first integration test asserted `after_chain is None` but read back the string `'null'`).
- **Issue:** SQLAlchemy's `JSON` type serializes Python `None` to JSON `null` by default, so a fail_as_defect (no healed chain) stored JSON `'null'` rather than a true SQL NULL — muddying the "no after" diff-render state.
- **Fix:** `after_chain: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)` so `None` persists as SQL NULL. Migration unaffected (column already nullable).
- **Files:** `app/models/heal_audit.py`.
- **Commit:** `c6a9c9c`

**3. [Rule 3 - Blocking] `integration` pytest marker unregistered**
- **Found during:** Task 2 (PytestUnknownMarkWarning on the new integration tests).
- **Fix:** registered `integration` in `pyproject.toml` markers; moved the per-async-test `asyncio(loop_scope="module")` mark off the module-level pytestmark so the pure parse tests stay sync (no spurious asyncio-mark warning).
- **Files:** `apps/api/pyproject.toml`, `tests/integration/test_heal_ingest.py`.
- **Commit:** `c6a9c9c`

## Environmental Note (NOT a code issue)
Toggling `graph_mode up`/`down` to run the graph-marked test restarted the `api`/`web` containers. A subsequent ad-hoc `docker compose up -d api` (run from `infra/` without `--env-file ../.env`) recreated `api` with an EMPTY-interpolated `DATABASE_URL` (`postgresql+asyncpg://:@postgres:5432/`), so its startup alembic failed with `password authentication failed for user "root"`. This is a compose env-file invocation detail (the repo `.env` lives at root, compose runs from `infra/`), NOT a defect in this plan. Recreating with `docker compose --env-file ../.env up -d api` restored the correct DSN and the api came up healthy at alembic head `0008`. The in-container entrypoint applied migration 0008 cleanly.

## Verification
- **Task 1:** `test_page_object_rewrite.py` — **6 passed**; migration `upgrade head`→0008 / `downgrade -1`→0007 / `upgrade head`→0008 round-trip clean; `grep -c HealAudit app/models/__init__.py` = 2.
- **Task 2:** `test_heal_ingest.py` + `test_no_llm_in_worker.py` + `test_single_write_path.py` — **all passed**; `grep -rn execute_write app/services/healing/*.py` = NONE; `append_element_history` uses `$key/$history_json/$chain_json/$now` placeholders exclusively.
- **Task 3:** `test_no_llm_in_worker.py` + `test_heal_ingest.py` — **passed** (SC3 gate green over extended job.py); `grep -cE 'ingest_heal_journal|reconcile_verdict' job.py` = 4; `test_heal_kg_writeback -m graph` — **2 passed** with neo4j up.
- **Full deterministic suite** (`-m "not live_llm and not graph and not e2e"`): **427 passed, 46 deselected** in 251s — the 4 pre-existing Phase-7 RabbitMQ functional failures (logged in deferred-items during 08-01/08-02) are now GREEN since the broker is up; zero regressions.
- **Graph suite** (`-m graph`, under graph_mode): the KG write-back proof passes; graph_mode brought neo4j healthy at ~1.1GB total under the 3GB cap, web stopped during graph work (per the Phase-3 environment strategy).

## Known Stubs
None — heal-as-commit is fully implemented end-to-end (journal → audit row + page-object rewrite + KG write-back, with the verdict reconciled in the worker). The `reviewed_outcome` column + the `applied`/`rejected` outcomes are scaffolded (in the model + the outcome allow-list) for the Plan-05 heal review/apply API (HEAL-04) but are not written by this plan's ingest — by design (Open Q3: quarantine/fail STAGE the proposal in the audit row; Plan 05 owns the apply/reject mutation).

## Next Phase Readiness
- **Plan 08-04 (mutation harness):** the `heal_audit` table is the false-heal-rate ground truth — a mutation that auto-heals onto the wrong element is now an auditable row to score against.
- **Plan 08-05 (heal review/apply API):** reads `heal_audit` for the before/after diff render; sets `reviewed_outcome` + writes `applied`/`rejected` rows; an `applied` reuses `_apply_page_object_rewrite` + `append_element_history` (already outcome-gated for `applied`).
- **Phase 9 (defect agent):** `reconcile_verdict`'s `fail_as_defect`→`product_failure` verdicts feed the defect classifier.

## Threat Surface
All threat-register mitigations applied: T-08-09 (tolerant bounded parse), T-08-10 (attr-keyed + ast-validated rewrite, json.dumps re-quote), T-08-11 (parameterized-only single-writer append), T-08-12 (run_id-derived project_root + journal_dir, never journal-supplied), T-08-13 (JSON chains, no blobs), T-08-14 (best-effort KG write-back). No new security surface beyond the threat model.

## Self-Check: PASSED

All 6 created + 5 modified files exist on disk; all 3 task commits present in git history (a2866ad, c6a9c9c, 3218c76).

---
*Phase: 08-self-healing-engine*
*Completed: 2026-06-22*
