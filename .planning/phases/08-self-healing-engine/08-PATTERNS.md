# Phase 8: Self-Healing Engine - Pattern Map

**Mapped:** 2026-06-22
**Files analyzed:** 18 new/modified
**Analogs found:** 16 / 18 (2 NET-NEW mechanisms with nearest-only references)

> Phase 8 is overwhelmingly an ASSEMBLY of existing seams. Two genuinely net-new mechanisms
> (the in-spec `_healing.py` accessor + file-journal handoff, and the deterministic 4-strategy
> scorer) have no exact analog and are flagged in **NET-NEW Mechanisms** below; everything else
> is DIRECT REUSE of a proven pattern. The single most likely planning mistake is healing in the
> worker — the worker has NO live page handle (see RESEARCH Pitfall 1).

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/services/healing/confidence.py` | service (pure) | transform | `app/services/kg/risk.py` | exact |
| `app/services/healing/candidates.py` | service (pure) | transform | `app/services/explorer/locators.py` (`build_locator_chain`) | exact |
| `app/services/healing/geometry.py` | service (pure) | transform | `app/services/kg/risk.py` (pure-stdlib shape) | role-match |
| `app/services/healing/ingest.py` | service | file-I/O → CRUD + KG-write | `app/services/worker/job.py` (`_discover_artifacts`) | role-match |
| `app/templates/healing/_healing.py.j2` | template (in-spec) | event-driven (live-page) | `app/templates/pages/page_object.py.j2` | role-match (NET-NEW logic) |
| `app/services/codegen/project.py` (EXTEND) | service | transform/file-I/O | itself (existing render loop) | exact (extend) |
| `app/models/heal_audit.py` | model | CRUD | `app/models/execution_history.py` | exact |
| `apps/api/alembic/versions/0008_heal_audit.py` | migration | DDL | `alembic/versions/0007_execution_history.py` | exact |
| `app/services/kg/writer.py` (EXTEND: `append_element_history`) | service | KG-write | `app/services/kg/writer.py` (`upsert_element`) | exact (extend) |
| `app/routers/heals.py` | router | request-response / CRUD | `app/routers/executions.py` | exact |
| `app/schemas/heal.py` | schema | request-response | `app/schemas/execution.py` | exact |
| `app/services/worker/job.py` (EXTEND: journal ingest + verdict) | service | event-driven | itself + `worker/classifier.py` | exact (extend) |
| `app/core/config.py` (EXTEND: heal thresholds) | config | — | itself (`stability_runs`) | exact (extend) |
| `infra/targets/saucedemo/Dockerfile` (EXTEND: mutation catalog) | config/infra | transform | itself (`SEED_BUG` build-arg) | exact (extend) |
| `infra/docker-compose*.yml` (EXTEND: mutation services) | config/infra | — | existing `saucedemo-bug` profile | role-match |
| `tests/functional/test_healing_mutations.py` | test | functional | `tests/functional/test_seeded_bug.py` | exact |
| `tests/unit/test_heal_confidence.py` (+ candidates/outcome/geometry/rewrite) | test | unit | (pure-scorer table tests, kg/risk discipline) | exact |
| `tests/integration/test_heal_ingest.py` (+ kg_writeback/stats/heals_router) | test | integration | (mirrors execution-history queries / router tests) | role-match |

---

## Pattern Assignments

### `app/services/healing/confidence.py` (service, pure transform)

**Analog:** `app/services/kg/risk.py` — copy the `@dataclass(frozen=True)` weights + pure clamped blend + tier-function shape VERBATIM. This is the single closest analog in the codebase.

**Frozen weights + DEFAULT** (`risk.py:23-38`):
```python
@dataclass(frozen=True)
class RiskWeights:
    destructive_action: int = 40   # ... exact values are RESEARCH A1 starting points
    per_state_change: int = 8
    auth_gated_step: int = 6
    per_form: int = 5
    depth: int = 3

DEFAULT_WEIGHTS = RiskWeights()
```
→ Heal version: `HealWeights(dom=0.30, visual=0.20, a11y=0.30, history=0.20)` + `DEFAULT_WEIGHTS` (RESEARCH Pattern 2 / A1).

**Pure clamped blend** (`risk.py:41-58`) — copy the clamp discipline:
```python
def risk_score(signals: dict, w: RiskWeights = DEFAULT_WEIGHTS) -> int:
    raw = ((w.destructive_action if signals.get("has_destructive") else 0)
        + w.per_state_change * int(signals.get("state_change_edges", 0)) + ...)
    return max(0, min(100, raw))   # clamp guarantees the range regardless of weights
```
→ Heal `confidence(signals, w)` returns `max(0.0, min(1.0, raw / total))` where `total = sum(weights) or 1.0` (RESEARCH Pattern 2, lines 250-257).

**Tier/band function** (`risk.py:61-67`) — copy for `heal_outcome`:
```python
def risk_tier(score: int) -> str:
    if score >= _HIGH_THRESHOLD: return "high"
    if score >= _MEDIUM_THRESHOLD: return "medium"
    return "low"
```
→ `heal_outcome(conf, live_match_count, *, high, med)` adds the HARD uniqueness gate FIRST: `if live_match_count != 1: return "fail_as_defect"` BEFORE the band checks (RESEARCH Pattern 3, lines 264-277). This is the structural false-heal guard — never score-gated.

**Module-doc invariant to carry** (`risk.py:1-12`): "imports NOTHING from the graph driver / the metered LLM path / the DB session factory — it is stdlib-only (dataclasses)." The heal scorer MUST hold the same import constraint (no browser, no I/O, no LLM) so it is table-testable AND can be vendored byte-for-byte into `_healing.py.j2`.

---

### `app/services/healing/candidates.py` (service, pure transform)

**Analog:** `app/services/explorer/locators.py` — REUSE `build_locator_chain` (the priority ordering the candidate enumeration + tie-break must follow), `merge_locator_history` (for the KG write-back history list), and `_XPATH_JS` **verbatim** for the in-spec live xpath read.

**Pure priority chain** (`locators.py:41-79`) — the healing-priority order candidate scoring mirrors:
```python
def build_locator_chain(attrs: dict) -> list[dict]:
    # data-testid (BOTH data-testid AND data-test) → aria-label → role(+name) → text → xpath(last)
```
Candidate enumeration + tie-break in the engine follow this SAME order (RESEARCH Pattern 2 "Priority chain", line 236). A candidate matching on a higher tier scores higher, all else equal.

**Append-only history merge** (`locators.py:82-91`) — REUSE to build the new history before serializing for the KG write-back:
```python
def merge_locator_history(existing: list, new_chain: list, *, step: int) -> list:
    history = list(existing or [])
    history.append({"step": step, "chain": list(new_chain)})
    return history
```

**Verbatim xpath JS** (`locators.py:20-38`) — vendor `_XPATH_JS` into `_healing.py.j2` for the live `page.evaluate(_XPATH_JS)` read (RESEARCH "Don't Hand-Roll": REUSE verbatim, do NOT write a new xpath generator).

**Pure/IO split discipline** (`locators.py:1-15`): "The PURE logic (priority ordering + history merge) is split from the async handle reads so it is unit-testable on plain fixture dicts — no browser, no spend." Candidate sub-scores (DOM Jaccard, a11y `difflib.SequenceMatcher.ratio`) MUST be pure-on-fixture-dicts the same way.

---

### `app/services/healing/geometry.py` (service, pure transform)

**Analog:** `kg/risk.py` for the stdlib-only / pure-fixture-testable shape. The IoU body itself is given in RESEARCH Code Examples (lines 413-423). Box = `{"x","y","width","height"}` as returned by Playwright `locator.bounding_box()`. NO Playwright import here (pure math on dicts); `None` (off-screen) → `0.0`. NO new image package (RESEARCH Pitfall 7 / Anti-Patterns).

---

### `app/services/healing/ingest.py` (service, file-I/O → CRUD + KG-write)

**Analog:** `app/services/worker/job.py` `_discover_artifacts` (`job.py:107-126`) — the post-subprocess output-dir walk this mirrors. The journal ingest is the heal sibling of artifact discovery.

**Post-run output-dir walk** (`job.py:107-126`):
```python
def _discover_artifacts(run_id: str, out_dir: Path) -> list[tuple[str, str]]:
    base = run_dir(run_id)
    if not out_dir.exists(): return artifacts
    for path in sorted(out_dir.rglob("*")):
        ...
        rel = path.relative_to(base).as_posix()   # RUN-RELATIVE, POSIX, never absolute
```
→ Ingest reads `workspaces/<run_id>/<flow_id>/heal-journal.json` (run_id-derived path via `app.core.workspaces.run_dir` — NEVER a path from the journal body; carry T-07-11).

**Tolerant parse** (REUSE `kg/reader._loads`, `reader.py:42-50`) — the journal parse must be tolerant (malformed entry → skip, never crash the worker; RESEARCH Security "Malformed heal-journal crashing ingest"):
```python
def _loads(raw: str | None) -> list:
    if not raw: return []
    try: val = json.loads(raw)
    except (ValueError, TypeError): return []
    return val if isinstance(val, list) else []
```

**Three side-effects** (RESEARCH Pattern 4, lines 292-298): (1) INSERT `HealAudit` rows in a FRESH `SessionLocal` (see job.py Pitfall-2 pattern below), (2) page-object rewrite by element key (auto_heal immediate; quarantine/fail STAGED — Open Q3), (3) `kg/writer.append_element_history` (single writer).

**AST-validate the rewrite** (REUSE the `selector_gate.py` ast pattern + `codegen/project.py` `_render_checked_py` discipline, `project.py:89-103`): after a line-targeted locator replace, `ast.parse` the rewritten page object BEFORE persisting (RESEARCH Open Q1). `selector_gate.assert_page_object_literals_are_repo_sourced` (`selector_gate.py:155-178`) is the existing ast-walk that finds the `page.locator(<literal>)` sink to rewrite.

---

### `app/templates/healing/_healing.py.j2` (template, in-spec, event-driven) — **NET-NEW logic**

**Nearest analog:** `app/templates/pages/page_object.py.j2` (the Jinja2 structure-owns-everything discipline) + `codegen/project.py` (how a template is rendered + gated). The HEAL LOGIC is net-new (no exact analog).

**Template discipline to carry** (`page_object.py.j2:1-10`): the template owns ALL structure; selectors/chains are repo-sourced inputs, never LLM slots. The locator-emit line is the rewrite target:
```jinja
{% for attr, selector in locators.items() %}        self.{{ attr }} = page.locator({{ selector | tojson }})
{% endfor %}
```
→ `_healing.py.j2` vendors the pure scorer (`confidence`/`heal_outcome`/`iou`/sub-scores) INTO the template so the generated project is self-contained (it cannot `import app.services`). Keep the canonical copy in `app/services/healing/`; add a byte-equivalence drift-guard test (RESEARCH Open Q2). The in-spec `heal()` body is given in RESEARCH Code Examples (lines 430-449): enumerate live candidates → score → HARD `page.locator(selector).count()==1` re-validation → band → append journal → return healed Locator OR raise `HealFailed`. NEVER touches `expect(...)` assertions (RESEARCH Pattern 1, lines 219-221).

**Render wiring** — EXTEND `codegen/project.py` `generate_project` (`project.py:121-258`): add `files["_healing.py"] = ...` to the in-memory `files` dict (rendered + ast-checked like every other file, lines 233-247) and wire the page-object `_resolve(element_key)` accessor (RESEARCH Pattern 1 pseudo, lines 200-221). It is written in the same no-partial-write block (`project.py:249-254`).

---

### `app/models/heal_audit.py` (model, CRUD)

**Analog:** `app/models/execution_history.py` — copy the `Mapped[...] = mapped_column(...)` style, String widths, `server_default=func.now()` timestamp, indexed `run_id`/`flow_id` VERBATIM (`execution_history.py:58-93`):
```python
class TestResult(Base):
    __tablename__ = "test_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    flow_id: Mapped[str] = mapped_column(String(255), index=True)
    verdict: Mapped[str] = mapped_column(String(16))
    exit_codes: Mapped[list] = mapped_column(JSON)        # JSON list, NEVER a blob
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```
→ `HealAudit` columns (RESEARCH Pattern 4 journal shape, lines 289-290): `element_key` (String, indexed), `before_chain`/`after_chain` (`JSON` — chains as JSON, NEVER a blob; carry the execution-history rule), `confidence` (Float/Integer), `outcome` (String(16): auto_heal|quarantine|fail_as_defect|applied|rejected), `live_match_count` (Integer), `run_id`/`flow_id` (indexed), `reviewed_outcome` (nullable String — set by the reject API for false-heal tracking, HEAL-04), `created_at`. Register it in `app/models/__init__.py` like the others.

---

### `apps/api/alembic/versions/0008_heal_audit.py` (migration, DDL)

**Analog:** `alembic/versions/0007_execution_history.py` — copy the revision-chain header + `op.create_table`/`op.create_index` style EXACTLY. **Migrations live in `apps/api/alembic/versions/`, NOT `app/alembic`.**

**Revision chain** (`0007:22-25`) — 0008 chains down to 0007:
```python
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
```

**Table + index shape** (`0007:30-76`) — copy column/index DDL style; mirror the `JSON`/`String`/`DateTime(timezone=True, server_default=sa.text('now()'))` columns and `op.create_index(op.f('ix_heal_audit_run_id'), ...)`. `downgrade()` drops indexes then table in reverse (`0007:79-89`).

---

### `app/services/kg/writer.py` (EXTEND: `append_element_history`) (service, KG-write)

**Analog:** `kg/writer.py` itself — `_UPSERT_ELEMENT` + the `_write` read-back guard. **This is the ONLY sanctioned write path (the single-write-path grep gate, RESEARCH Pitfall 5).**

**Managed write + read-back guard** (`writer.py:29-46`) — the new fn routes through `_write` like every other:
```python
async def _write(cypher, params, *, driver, what) -> dict:
    async with drv.session() as session:
        rec = await session.execute_write(_tx)
    if not rec or int(rec.get("n", 0)) < 1:
        raise RuntimeError(f"kg_writer.{what} persisted nothing to Neo4j")
    return rec
```

**Element upsert** (`writer.py:75-94`) — the chain_json/history_json SET shape to mirror; the new fn appends a history snapshot:
```python
_UPSERT_ELEMENT = ("MERGE (e:Element {key:$key}) ... "
    "SET e.last_verified=coalesce(...), e.chain_json=$chain_json, e.history_json=$history_json "
    "RETURN count(*) AS n")
```
→ `append_element_history` body is given in RESEARCH Code Examples (lines 455-463): `MATCH (e:Element {key:$key}) SET e.history_json=$history_json, e.chain_json=$chain_json, e.last_verified=$now RETURN count(*) AS n`. Parameterized ONLY; labels/edge-types are `kg/schema` constants (carry T-04-14 / T-05-01; RESEARCH Security "Cypher injection"). Build the new history list with `explorer/locators.merge_locator_history` (pure) before serializing.

---

### `app/routers/heals.py` (router, request-response / CRUD)

**Analog:** `app/routers/executions.py` — copy the `APIRouter(prefix=..., dependencies=[Depends(...)])` auth-gated pattern. **NOTE: no `require_role` 4-role DI exists yet — reuse `get_current_user` (RESEARCH A6 / "Don't Hand-Roll": don't invent it here).** D-05: list / apply / reject + stats only; no UI.

**Auth-gated router** (`executions.py:89-94`):
```python
router = APIRouter(
    prefix="/api/executions", tags=["executions"],
    dependencies=[Depends(require_user_or_ci_token)],   # cookie OR ci_token — unauth -> 401
)
```
→ `app/routers/heals.py`: `APIRouter(prefix="/api/heals", dependencies=[Depends(get_current_user)])` (or reuse `require_user_or_ci_token` if CI access is wanted). EVERY mutating endpoint (apply/reject) MUST be auth-gated (RESEARCH Security V4 — state-changing, not public).

**Handler shape** (`executions.py:123-138`): GET returns `response_model=list[...]`; per-id GET 404s on unknown via `HTTPException(status_code=404, ...)`. → `GET /heals?status=quarantined`, `POST /heals/{id}/apply`, `POST /heals/{id}/reject`, `GET /heals/stats?element=...` (HEAL-04). `heal_id` is an int PK + `element` is a string filter — parameterize via the ORM (RESEARCH Security V5). The reject handler flips `reviewed_outcome` (false-heal capture, HEAL-04). Register the router in the app factory like `executions`.

---

### `app/schemas/heal.py` (schema, request-response)

**Analog:** `app/schemas/execution.py` (the `ExecuteTierRequest`/`TestRunResponse` Pydantic shapes the router returns). Mirror Pydantic v2 `model_validate`. Define `HealAuditResponse` (before/after diff + confidence + outcome from the audit record) + `HealStatsResponse` (per-element success/false-heal).

---

### `app/services/worker/job.py` (EXTEND: journal ingest + verdict) (service, event-driven)

**Analog:** `job.py` itself + `worker/classifier.py`. Add the journal INGEST right after `_discover_artifacts` (`job.py:169`) and BEFORE/at the TestResult write (RESEARCH diagram lines 145-149). The heal-journal verdict takes PRECEDENCE over `classify_retry`.

**Fresh-session write block** (`job.py:171-187`) — heal_audit rows + the TestResult write go in this SAME fresh session (Pitfall-2: the worker owns its own session):
```python
async with SessionLocal() as db:
    db.add(TestResult(run_id=..., verdict=verdict["verdict"], ...))
    for kind, rel_path in artifacts: db.add(TestArtifact(...))
    await db.commit()
```
→ Add `db.add(HealAudit(...))` per journal entry here; rewrite page objects + call `kg/writer.append_element_history` (Open Q3: auto_heal rewrites immediately).

**Verdict reconciliation** (`classifier.py:22-46`) — the journal overrides the exit-code classifier (RESEARCH Pattern 1 reconciliation, lines 223-225 + Pitfall 4):
```python
def classify_retry(attempt_exit_codes: list[int]) -> dict:
    if passed: verdict = "flaky" if retried else "passed"
    else: verdict = "product_failure"
```
→ If the journal has an `auto_heal` event for the flow → verdict `auto_healed` (overrides `passed`/`flaky` — a heal is NOT a flake). A `quarantine` event → `quarantined`; a `fail_as_defect` event → `product_failure` (feeds Phase 9). These are ADDITIVE to the existing `String(16)` verdict column (RESEARCH A5 — no schema change). Implement the override as a small pure helper next to `classify_retry` (table-testable), do NOT inline it.

---

### `app/core/config.py` (EXTEND: heal thresholds) (config)

**Analog:** the `stability_runs` / `seeded_bug_base_url` settings (`config.py:96-97`):
```python
stability_runs: int = 3  # env STABILITY_RUNS
seeded_bug_base_url: str | None = None  # env SEEDED_BUG_BASE_URL
```
→ Add `heal_high_threshold: float = 0.85`, `heal_med_threshold: float = 0.60`, `heal_enabled: bool = True` (RESEARCH Pattern 3 + Runtime State Inventory). Compose does NOT pass the whole `.env` — add each to the compose env explicitly (carry the Phase-2 lesson, RESEARCH Runtime State Inventory).

---

### `infra/targets/saucedemo/Dockerfile` (EXTEND: mutation catalog) (config/infra)

**Analog:** the existing `SEED_BUG` build-arg (`Dockerfile:42-46`):
```dockerfile
ARG SEED_BUG=0
RUN if [ "$SEED_BUG" = "1" ]; then \
      grep -rl 'inventory_list' /usr/share/nginx/html \
        | xargs -r sed -i 's/inventory_list/inventory_list_BROKEN/g'; \
    fi
```
→ Add BENIGN build-args (rename `data-test`, change visible text, change tag, reorder/wrap) that MUST heal, alongside more BREAKING args (remove/duplicate/semantics) that MUST still fail. Each is one deterministic `sed` rewrite gated by a build-arg (RESEARCH Pattern 6 catalog table, lines 312-322). Default 0 so the standard build stays byte-identical (T-06-21 — no drift). Add matching compose profile services (mirror `saucedemo-bug`).

---

### `tests/functional/test_healing_mutations.py` (test, functional)

**Analog:** `tests/functional/test_seeded_bug.py` — copy the accept/reject assertion shape exactly, extended to a catalog. Keyless, `pytestmark = [pytest.mark.functional, pytest.mark.graph]`, REUSE the `_plant` / `_WORKSPACES_ROOT` / host-URL fixtures from `test_stability.py` (`test_seeded_bug.py:36-46`).

**Assertion shape** (`test_seeded_bug.py:49-63`):
```python
result = await run_seeded_bug(spec_path, base_url=SEEDED_BUG_HOST_URL)
assert result["detected_breakage"] is True, ...
```
→ For each BENIGN build: assert the journal records `auto_heal` AND the spec passes (`benign_heal_rate >= 0.90`). For each BREAKING build: assert the spec FAILS AND the journal records `fail_as_defect`/`quarantine`, NEVER `auto_heal` (`false_heal_rate ~= 0`). The subprocess runner is `stability._run_spec_once` (RESEARCH "Don't Hand-Roll").

**3GB sequencing** (`test_seeded_bug.py:18-22` + `stability.py:21-32`): stop neo4j before the harness — the RUN phase needs NO neo4j (chains/history are vendored into `_healing.py` at codegen; RESEARCH Pitfall 6 / A7).

### `tests/unit/test_heal_*.py` (test, unit)

**Analog:** the pure-scorer table-test discipline of `kg/risk.py` / `build_locator_chain` / `classify_retry` — fixture dicts, sub-second, no browser/DB. Covers HEAL-01 (confidence blend + candidate sub-scores + geometry IoU), HEAL-02 (bands + uniqueness gate + `test_assertion_never_healed`), HEAL-03 (page-object rewrite ast-valid).

### `tests/integration/test_heal_*.py` (test, integration)

**Analog:** execution-history aggregation queries (HEAL-04 stats) + router tests (D-05). `test_heal_kg_writeback.py` is `-m graph` (single-writer append). `test_heal_ingest.py` covers journal → audit rows.

---

## Shared Patterns

### Single-writer KG access (HEAL-03)
**Source:** `app/services/kg/writer.py` (`_write`, `writer.py:29-46`; `upsert_element`, `writer.py:75-94`)
**Apply to:** `kg/writer.append_element_history` (the ONLY new graph write). Managed `execute_write` + parameterized Cypher + `RETURN count(*) AS n` read-back guard. The grep gate scans for `execute_write`/`tx.run(...MERGE...)` outside this file — keep it green.

### Fresh SessionLocal per background task (HEAL-03)
**Source:** `app/services/worker/job.py:171-187`
**Apply to:** `healing/ingest.py` + the `job.py` ingest extension. `async with SessionLocal() as db:` — the worker owns its own session, never a request's (Pitfall 2).

### Pure-logic split + fixture-table tests (HEAL-01/02)
**Source:** `app/services/kg/risk.py:1-12` + `app/services/explorer/locators.py:1-15` + `worker/classifier.py:1-17`
**Apply to:** `healing/confidence.py`, `candidates.py`, `geometry.py`, and the verdict-override helper. Stdlib-only, no I/O / no browser / no LLM, table-testable on fixture dicts. Enables byte-for-byte vendoring into `_healing.py.j2`.

### run_id-derived paths (no path from message/journal body) (HEAL-03)
**Source:** `app/services/worker/job.py:148-150` (`spec_path(run_id)`, `run_dir(run_id)`) + `routers/executions.py:235-258` (multi-segment path-traversal guard)
**Apply to:** journal read in `ingest.py` and the page-object rewrite. All paths via `app.core.workspaces` helpers; NEVER trust a path from the journal body (T-07-11).

### Subprocess spec runs (never in-process) (QUAL-02)
**Source:** `app/services/stability.py:58-105` (`_run_spec_once` — argv LIST, no shell, isolated)
**Apply to:** the mutation harness. Sync Playwright in-process deadlocks (Pitfall 2 / T-06-19).

### ast-validate generated/rewritten Python (HEAL-03)
**Source:** `app/services/codegen/project.py:89-103` (`_render_checked_py`) + `app/services/gates/selector_gate.py` (`ast.parse` + sink-walk)
**Apply to:** the page-object locator rewrite — `ast.parse` after the line-targeted replace; reuse `assert_page_object_literals_are_repo_sourced` to locate the `page.locator(<literal>)` sink.

### Auth-gated router (D-05)
**Source:** `app/routers/executions.py:74-94` (`get_current_user` / `require_user_or_ci_token`)
**Apply to:** `routers/heals.py`. Reuse `get_current_user` — `require_role` does NOT exist (RESEARCH A6).

### Tolerant JSON deserialize (HEAL-03)
**Source:** `app/services/kg/reader.py:42-50` (`_loads`)
**Apply to:** heal-journal parse in `ingest.py` (malformed entry → skip, never crash; RESEARCH Security DoS).

---

## NET-NEW Mechanisms (no exact analog — flagged for the planner)

| Mechanism | Why net-new | Nearest reference | Risk |
|-----------|-------------|-------------------|------|
| **In-spec `_healing.py` heal accessor + file-journal handoff** | The worker has NO live page handle (subprocess isolation); heal MUST run inside the generated spec, which has no DB/Neo4j. No prior phase generates executable interception logic into the project tree or hands off via a journal. | `templates/pages/page_object.py.j2` (template structure) + `codegen/project.py` (render loop) + `worker/job.py` `_discover_artifacts` (post-run dir walk = the journal-ingest analog) | HIGH — RESEARCH Pitfall 1 (don't heal in the worker); Open Q1/Q2/Q3 (rewrite precision, vendoring, stage-vs-apply) |
| **Deterministic 4-strategy similarity scorer** | DOM-Jaccard + bbox-IoU + a11y-`difflib` + history-match blend is new logic, even though its SHAPE clones `kg/risk.py`. The four metrics themselves have no prior implementation. | `kg/risk.py` (frozen-weights + clamped-blend + tier shape) + `explorer/locators.build_locator_chain` (priority order) + RESEARCH Code Examples (IoU body, heal() body) | MEDIUM — weights/bands are config-tunable starting points (A1/A2); the uniqueness gate provides the structural false-heal guarantee independent of thresholds |
| **Benign-vs-breaking mutation catalog** | Extends the SEED_BUG single-mutation toggle to a multi-mutation catalog with benign/breaking classes. | `infra/targets/saucedemo/Dockerfile` `SEED_BUG` build-arg + `test_seeded_bug.py` accept/reject | MEDIUM on exact `sed` rewrites (validate per build); HIGH on the pattern (proven trust-gate) |

## DIRECT-REUSE Seams (high-confidence assembly)

- `kg/risk.py` → `confidence.py` (frozen-weights + clamped-blend + tier) — **clone the shape verbatim.**
- `explorer/locators.py` → `candidates.py` (`build_locator_chain` order, `merge_locator_history`, `_XPATH_JS` verbatim).
- `kg/writer.py` single-writer → `append_element_history` (the one new graph write, routed through `_write`).
- `stability.py` / `test_seeded_bug.py` / `SEED_BUG` Dockerfile → the mutation harness (keyless, sequenced).
- `0007_execution_history.py` → `0008_heal_audit.py` (revision chain `down_revision='0007'`, `apps/api/alembic/versions/`).
- `execution_history.py` models → `heal_audit.py` (Mapped/mapped_column, JSON columns, indexed run_id/flow_id).
- `routers/executions.py` → `routers/heals.py` (auth-gated router, `get_current_user`).
- `worker/job.py` `_discover_artifacts` + fresh `SessionLocal` → the journal-ingest extension.
- `worker/classifier.py` → the verdict-override helper (additive `auto_healed`/`quarantined`).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `app/templates/healing/_healing.py.j2` (heal LOGIC) | template | event-driven | Net-new in-spec interception; only the Jinja structure has an analog. Use `page_object.py.j2` for structure + RESEARCH Code Examples (lines 430-449) for the `heal()` body. |
| `app/services/healing/candidates.py` (the 4 SUB-SCORE metrics) | service | transform | The DOM-Jaccard / a11y-`difflib` / history-match metrics are net-new (the ORDERING + history reuse `explorer/locators`; the metric bodies do not). |

## Metadata

**Analog search scope:** `apps/api/app/services/{kg,explorer,codegen,worker,gates}/`, `apps/api/app/{models,routers,schemas,templates,core}/`, `apps/api/alembic/versions/`, `apps/api/tests/functional/`, `infra/targets/saucedemo/`
**Files scanned:** 16 source analogs read in full + targeted greps (reader.py, config.py)
**Pattern extraction date:** 2026-06-22
