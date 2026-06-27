# Phase 9: Defect Intelligence & Jira Agent - Pattern Map

**Mapped:** 2026-06-27
**Files analyzed:** 24 (new + modified, backend + frontend + infra)
**Analogs found:** 21 / 24 (3 net-new mechanisms have a discipline-analog but no exact structural twin)

> **One-line summary for the planner:** Phase 9 is the FOURTH instance of three already-shipped patterns — a pure frozen-weights decision module (`kg/risk.py` / `healing/confidence.py` / `worker/classifier.py`), a keyless mutation-build accuracy harness (`test_healing_mutations.py`), and an auth-gated apply/reject review router + list/detail UI (`heals.py` + `scenarios/`). Copy those byte-faithfully. Only THREE mechanisms are net-new (flagged in **No Analog / Net-New** below): the `JiraGateway` Protocol + `FakeJira` double, the 3-way taxonomy *rules body* inside the otherwise-cloned classifier shape, and the dead-port infra-fault generator that extends the harness.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/services/defects/classifier.py` | service (pure) | transform | `app/services/kg/risk.py` + `app/services/healing/confidence.py` | exact (shape); net-new (rules body) |
| `app/services/defects/fingerprint.py` | utility (pure) | transform | `app/services/explorer/fingerprint.py` (hashlib+re normalize) | exact (hashing/normalize discipline) |
| `app/services/defects/evidence.py` | service | CRUD (read joins) | `app/services/worker/job.py` (the test_results/heal_audit reads) | role-match |
| `app/services/defects/pipeline.py` | service | event-driven (post-run) | `app/services/worker/job.py` (post-subprocess orchestrator, fresh SessionLocal) | role-match |
| `app/services/jira/client.py` | service (gateway) | request-response (external) | `app/services/llm_gateway.py` (gateway+fallback+never-log) | role-match; **net-new Protocol** |
| `app/services/jira/adf.py` | utility (pure) | transform | `app/services/explorer/fingerprint.py` (pure builder discipline) | partial (pure-builder shape only) |
| `app/services/jira/fake.py` | test double | request-response (in-memory) | — (no double exists in repo) | **NO ANALOG — net-new** |
| `app/services/infra_health.py` | service (pure) | transform | `app/services/defects/classifier.py` sibling (error-pattern signal) | role-match (pure signal) |
| `app/models/defects.py` | model | CRUD | `app/models/heal_audit.py` + `app/models/execution_history.py` | exact |
| `app/schemas/defect.py` | schema | request-response | `app/schemas/heal.py` (from_attributes Pydantic v2) | exact |
| `app/routers/defects.py` | router | request-response (CRUD) | `app/routers/heals.py` (auth-gated list/apply/reject) | exact |
| `alembic/versions/0009_defects.py` | migration | — | `alembic/versions/0008_heal_audit.py` (down_revision chain) | exact |
| `app/core/config.py` (MODIFY) | config | — | existing `ci_token` / `heal_high_threshold` blocks in same file | exact (extend in place) |
| `app/services/worker/job.py` (MODIFY) | service | event-driven | the file itself (persist already-in-hand `output`) | exact (one-line add) |
| `app/models/execution_history.py` (MODIFY) | model | CRUD | the file itself (add `error_text` to `TestResult`) | exact |
| `tests/unit/test_classifier.py` | test | transform | `tests/` fixture-unit pattern (kg/risk, heal confidence) | role-match |
| `tests/unit/test_fingerprint.py` | test | transform | fixture-unit pattern | role-match |
| `tests/unit/test_no_llm_in_classifier.py` | test (grep gate) | transform | `tests/unit/test_no_llm_in_worker.py` | exact |
| `tests/unit/test_jira_create.py` / `test_jira_dedup.py` / `test_adf.py` | test (FakeJira) | request-response | — (the double itself is net-new) | partial |
| `tests/functional/test_classifier_accuracy.py` | test (functional) | event-driven | `tests/functional/test_healing_mutations.py` | exact |
| `tests/integration/test_defects_router.py` / `test_defect_pipeline.py` | test (integration) | request-response | (router integration style) | role-match |
| `infra/targets/saucedemo/Dockerfile` (REUSE) | infra | — | the file itself (SEED_BUG + mutation build-args) | exact (no edit; dead-port fault is harness-side) |
| `apps/web/lib/api/defects.ts` | api client | request-response | `apps/web/lib/api/scenarios.ts` (zod + api wrapper) | exact |
| `apps/web/app/(dashboard)/defects/page.tsx` + `[id]/page.tsx` | component | request-response | `apps/web/app/(dashboard)/scenarios/page.tsx` + `[id]/page.tsx` | exact |
| `apps/web/components/app-sidebar.tsx` (MODIFY) | component | — | the file itself (append to `NAV_ITEMS`) | exact (one-line add) |

---

## Pattern Assignments

### `app/services/defects/classifier.py` (service, pure transform) — DEF-01/02

**Analog:** `app/services/kg/risk.py` (frozen weights + clamped score) + `app/services/healing/confidence.py` (clamped blend + band resolver). **Clone this discipline byte-for-byte; the taxonomy *rules body* is the only net-new content.**

**Module docstring + purity contract** (`kg/risk.py` lines 1-12) — copy the "PURE … NEVER LLM JUDGMENT … stdlib-only (dataclasses) … weights are a STARTING POINT" framing verbatim:
```python
"""PURE deterministic per-flow risk score (KG-04 / D-04) — NEVER LLM JUDGMENT.
...
Acceptance (test_kg_risk.py): this module imports NOTHING from the graph driver / the metered
LLM path / the DB session factory — it is stdlib-only (dataclasses). The weights are a STARTING
POINT ... and swappable per call.
"""
```

**Frozen-weights dataclass** (`kg/risk.py` lines 23-38) — the exact shape for `ClassifierWeights`:
```python
@dataclass(frozen=True)
class RiskWeights:
    """Frozen so a shared DEFAULT_WEIGHTS can never be mutated under callers ..."""
    destructive_action: int = 40   # binary contributes once
    per_state_change: int = 8
    ...
DEFAULT_WEIGHTS = RiskWeights()
```

**Pure clamped-score function** (`kg/risk.py` lines 41-58) — copy the `signals.get(...)` defaulting + `max(0, min(100, raw))` clamp:
```python
def risk_score(signals: dict, w: RiskWeights = DEFAULT_WEIGHTS) -> int:
    raw = (
        (w.destructive_action if signals.get("has_destructive") else 0)
        + w.per_state_change * int(signals.get("state_change_edges", 0))
        ...
    )
    return max(0, min(100, raw))
```

**Band/tier resolver + HARD precedence gate** (`healing/confidence.py` lines 63-83) — copy `heal_outcome`'s structure for the 3-way class precedence (the structural gate-FIRST discipline; the classifier's class-rule precedence is the analog of the uniqueness-gate-first ordering):
```python
def heal_outcome(conf: float, live_match_count: int, *, high: float, med: float) -> str:
    if live_match_count != 1:
        return "fail_as_defect"   # structural gate applied FIRST, before any band
    if conf >= high:
        return "auto_heal"
    if conf >= med:
        return "quarantine"
    return "fail_as_defect"
```

**Net-new content (no analog — RESEARCH Pattern 1 taxonomy table):** the `_classify_rules(evidence, cited)` body mapping browser-crash/network/timeout/infra-down → `infrastructure`; un-healed/quarantined locator + test-data → `automation`; loaded-page assertion + functional/API error → `product_defect`. **The shape is cloned; the rule bodies + the 60/20/-15 starting weights are the planner's to fill, tuned by QUAL-03 (the heal-band 0.85→0.15 precedent).**

---

### `app/services/defects/fingerprint.py` (utility, pure transform) — JIRA-03/D-05

**Analog:** `app/services/explorer/fingerprint.py` — the closest hashlib+re normalization in the repo (it strips instance data from a structural tree; Phase 9 strips numbers/ids/timestamps/uuids from an error string).

**Normalize regexes + hashlib digest** (`explorer/fingerprint.py` lines 37-39, 58, 86-97, 158-167) — copy the module-level compiled-regex + `_NUM_RE.sub` + `hashlib.sha256(...).hexdigest()` discipline (Phase 9 uses sha1[:16] per RESEARCH Pattern 5):
```python
import hashlib, re
_NUM_RE = re.compile(r"\d+")
...
def _normalize_attr_value(name: str, value: str) -> str:
    ...
    return _NUM_RE.sub("#", value or "")
...
def structural_fingerprint(tree: dict, cfg=DEFAULT_CONFIG) -> str:
    ...
    return hashlib.sha256(skeleton.encode("utf-8")).hexdigest()
```
**Apply:** the RESEARCH Pattern 5 `_UUID/_TS/_HEX/_NUM` regex set + `hashlib.sha1(f"{cls}|{normalize(msg)}|{flow}|{step}").hexdigest()[:16]`. Stdlib only — NO new package (the explorer module proves the discipline).

---

### `app/services/defects/pipeline.py` + `evidence.py` (service, event-driven / read-joins) — DEF-02/JIRA-03

**Analog:** `app/services/worker/job.py` — the post-run orchestrator that gathers per-flow signals and persists in a FRESH `SessionLocal`.

**Fresh-session + commit discipline** (`worker/job.py` lines 178-213) — copy the `async with SessionLocal() as db:` ownership (never a request session) + `db.add(...)` + `await db.commit()`:
```python
async with SessionLocal() as db:
    journal_outcomes = await ingest_heal_journal(db, run_id, flow_id, ...)
    db.add(TestResult(run_id=run_id, flow_id=flow_id, verdict=..., exit_codes=exit_codes, ...))
    for kind, rel_path in artifacts:
        db.add(TestArtifact(run_id=run_id, flow_id=flow_id, kind=kind, path=rel_path))
    await db.commit()
```

**Evidence gather (read joins):** `evidence.py` reads `TestResult.error_text` (NEW column), `HealAudit` (DOM before/after + outcome — `heal_audit.py` lines 41-51), and `TestArtifact` paths — all thread by `run_id`+`flow_id` (already indexed). The pipeline runs ONLY when `verdict == "product_failure"` (the `reconcile_verdict` output, `worker/classifier.py` lines 49-78 — `fail_as_defect` → `product_failure` is the feed).

---

### `app/services/jira/client.py` (service, gateway → external) — JIRA-01/03/04 — **NET-NEW Protocol**

**Analog (gateway + fallback + never-log shape):** `app/services/llm_gateway.py`. The `JiraGateway` Protocol + the sync→async `anyio.to_thread` wrap have NO exact structural twin — flag net-new.

**Never-log + structlog discipline** (`llm_gateway.py` lines 43-46, 468-478) — copy the "provider keys NEVER enter the ledger or a log event" rule; the SENSITIVE regex matches "token"/"password", so the Jira token must never appear in a log key OR value:
```python
# PLAT-07: prompts/responses and provider keys NEVER enter the ledger or a log event.
...
log.info("llm_usage", operation_type=..., run_id=..., provider=..., model=...,
         tok_in=input_tokens, ...)   # NO key/secret in the event, ever
```

**Optional-secret boot-safe operation** (`llm_gateway.py` lines 214, 332-334) — the gateway boots without keys and the description-enrich path uses the deterministic no-key fallback; Phase 9's `client.py` must similarly degrade to FakeJira / not-configured when `settings.jira_api_token` is None.

**Net-new (RESEARCH Pattern 4):** the `JiraGateway` Protocol (`create_issue`/`add_attachment`/`search_jql`/`add_comment`/`create_issue_link` async methods) + the `AtlassianJira` impl wrapping each `atlassian.Jira(...)` call in `anyio.to_thread.run_sync(...)`. No anyio offload exists in the repo today — net-new (anyio is a FastAPI transitive; verify present, do NOT add).

---

### `app/services/jira/adf.py` (utility, pure transform) — JIRA-01

**Analog (pure-builder discipline only):** `app/services/explorer/fingerprint.py` (a pure string/dict builder kept separate from any I/O). The ADF doc-dict shape itself is RESEARCH Code-Examples content (no repo twin). Build `{"type":"doc","version":1,"content":[...]}` from summary/steps/expected/actual/severity — pure, unit-testable, no I/O.

---

### `app/services/jira/fake.py` (test double) — **NO ANALOG — NET-NEW**

No in-memory double / contract fake exists anywhere in the repo (the codebase uses real-subprocess + skip-when-down harnesses, not doubles). The `FakeJira` (RESEARCH Code-Examples: in-memory `issues` dict, `_n` counter, records `attachments`, `search_jql` matches the `fp-<hash>` label) is fully net-new. It is the keyless-CI seam that makes JIRA-01/03 logic testable without a token — flag prominently for the planner.

---

### `app/services/infra_health.py` (service, pure signal) — DEF-02

**Analog:** sibling of `classifier.py` — RESEARCH Open-Q2 recommends starting with the **error-pattern signal** (pure: connection-refused/DNS/timeout patterns over the error_text), keyless, in-module, NOT a live Docker-health probe (deferred to Phase 11). Same pure-regex discipline as `fingerprint.py`.

---

### `app/models/defects.py` (model, CRUD) — DEF/JIRA data model

**Analog:** `app/models/heal_audit.py` (closest — same Phase-8 era, same run_id/flow_id traceability + nullable-after + outcome-vocabulary + JSON-not-blob) backed by `app/models/execution_history.py`.

**Model style** (`heal_audit.py` lines 22-56) — copy `Mapped[...] = mapped_column(...)`, `String(64)` run_id + `index=True`, `String(255)` flow_id, `JSON(none_as_null=True)` for the evidence snapshot, `String(16)` for the status/class vocab, `server_default=func.now()`:
```python
from sqlalchemy import JSON, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class HealAudit(Base):
    __tablename__ = "heal_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    flow_id: Mapped[str] = mapped_column(String(255), index=True)
    after_chain: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    outcome: Mapped[str] = mapped_column(String(16))
    reviewed_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```
**Apply:** `Classification` (class String(16), confidence Integer 0-100, evidence JSON, run_id/flow_id) + `Defect` (status draft|applied|rejected String(16), fingerprint String(64) index, jira_key String(32) nullable, run_id/flow_id FKs). The nullable `jira_key` mirrors `heal_audit.after_chain` nullability; the status vocab mirrors `heal_audit.outcome`'s `applied|rejected` extension.

---

### `app/schemas/defect.py` (schema, request-response)

**Analog:** `app/schemas/heal.py` — ORM-readable Pydantic v2.

**from_attributes config + nullable fields** (`heal.py` lines 18-39):
```python
from pydantic import BaseModel, ConfigDict

class HealAuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    run_id: str
    after_chain: list | None      # nullable maps SQL NULL cleanly
    confidence: float
    outcome: str
    reviewed_outcome: str | None
    created_at: datetime
```
**Apply:** `DefectResponse` / `DefectDetailResponse` (the queue row + the proposed-issue + evidence) + a `CalibrationResponse` (accuracy/precision/threshold/autonomy-flag — a plain BaseModel built from a dict, like `HealStatsResponse` lines 42-48). The UI band edges read `confidence_threshold` off the payload (never a client literal).

---

### `app/routers/defects.py` (router, request-response CRUD) — JIRA-02 — **EXACT clone of heals.py**

**Analog:** `app/routers/heals.py` — the auth-gated list/apply/reject review router (the explicit Phase-8 draft-queue analog).

**Router-level auth gate** (`heals.py` lines 53-59) — copy verbatim; `require_role` does NOT exist, reuse `get_current_user`:
```python
router = APIRouter(
    prefix="/api/heals", tags=["heals"],
    dependencies=[Depends(get_current_user)],   # EVERY endpoint incl. state-changing apply/reject
)
```

**Filtered list off a status column** (`heals.py` lines 64-81) — ORM-parameterized `where(... == status)` + newest-first; Phase 9 adds the `?class=` filter the same way:
```python
@router.get("", response_model=list[HealAuditResponse])
async def list_heals(status: str = "quarantine", db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(
        select(HealAudit).where(HealAudit.outcome == status)
        .order_by(HealAudit.created_at.desc(), HealAudit.id.desc())
    )).all()
    return list(rows)
```

**404 helper + apply/reject state flips** (`heals.py` lines 84-143) — copy `_get_*_or_404` + the `db.get(...)` → flip-status → `commit`/`refresh` → `log.info(...)` shape. Phase-9 `apply` calls the `JiraGateway` (create-or-update per the dedup result) + persists `jira_key`; `reject` is a flag flip (like `reject_heal`).

**Artifact-URL contract (the detail attachment links)** — **Analog:** `app/routers/executions.py` `execution_artifact` (lines 235-259). The defect detail's attachment links REUSE this exact run_id-derived multi-segment path-containment guard; NEVER a request-body path:
```python
segments = [flow_id, *name.split("/")]
if any(seg in ("", ".", "..") or "\\" in seg for seg in segments):
    raise HTTPException(status_code=400, detail="invalid artifact path")
base = run_dir(run_id).resolve()
target = (base / flow_id / name).resolve()
if target != base and base not in target.parents:
    raise HTTPException(status_code=400, detail="invalid artifact path")
```

**Router registration** — `app/main.py` lines 38-39 + 119-123: `from app.routers.defects import router as defects_router` then `app.include_router(defects_router)` after `heals_router`.

---

### `alembic/versions/0009_defects.py` (migration) — EXACT clone of 0008

**Analog:** `alembic/versions/0008_heal_audit.py`. Migrations live in `apps/api/alembic/versions/` (NOT `app/alembic`).

**Revision chain + create_table + indexes + reverse downgrade** (`0008_heal_audit.py` lines 22-60):
```python
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'   # chains down to 0008

def upgrade() -> None:
    op.create_table('classifications', sa.Column('id', sa.Integer(), nullable=False), ...)
    op.create_table('defects', ...)
    op.add_column('test_results', sa.Column('error_text', sa.Text(), nullable=True))  # Pitfall 1
    op.create_index(op.f('ix_defects_run_id'), 'defects', ['run_id'], unique=False)
    ...

def downgrade() -> None:
    op.drop_index(...); op.drop_column('test_results', 'error_text'); op.drop_table('defects'); ...
```
**Reversibility is a phase gate** (RESEARCH Validation): `upgrade && downgrade -1 && upgrade` must round-trip.

---

### `app/core/config.py` (MODIFY — extend in place) — settings

**Analog:** the `ci_token` block (lines 121-130) + the `heal_high_threshold` block (lines 132-148) IN THIS SAME FILE.

**Optional never-log secret** (lines 39, 130) — the `anthropic_api_key` / `ci_token` precedent for `jira_api_token`:
```python
anthropic_api_key: str | None = None  # default None so the app boots without it; never logged
ci_token: str | None = None           # Default None ...; NEVER echoed/logged
```

**Config-tunable threshold with the tuning-note discipline** (lines 139-148) — `jira_confidence_threshold` mirrors `heal_high_threshold` EXACTLY (a starting point the QUAL-03 harness tunes; the harness asserts against the SHIPPED default, never a test-local literal — line 89 `_MUTATION_HIGH = str(_settings.heal_high_threshold)`):
```python
heal_high_threshold: float = 0.15  # env HEAL_HIGH_THRESHOLD — tuned by the QUAL-02 harness
```
**Apply (RESEARCH Runtime State):** add `jira_url`, `jira_email`, `jira_api_token` (`str | None = None`, never-log), `jira_project_key`, `jira_autonomous_enabled: bool = False` (OFF by default), `jira_confidence_threshold` (starting point), `jira_max_tickets_per_run: int`. **Compose must enumerate each explicitly** (the `heal_high_threshold` compose note, lines 138).

---

### `app/services/worker/job.py` + `app/models/execution_history.py` (MODIFY) — Pitfall 1 (error-text gap)

**Analog:** the files themselves — this is the confirmed persistence gap.

**The gap (job.py lines 165-167 vs 199-208):** `_run_spec_once` returns `output` (already in hand at line 165: `result = await _run_spec_once(...)`) but only `exit_codes` is persisted into `TestResult` — `output` is discarded:
```python
result = await _run_spec_once(spec, base_url=base_url, extra_args=capture_args)   # has result["output"]
...
db.add(TestResult(run_id=run_id, flow_id=flow_id, verdict=verdict["verdict"],
                  attempts=verdict["attempts"], exit_codes=exit_codes, duration_ms=duration_ms))
                  # ^ error_text NOT persisted today
```
**Apply:** capture the last attempt's `result["output"]` and pass `error_text=...` to the `TestResult(...)`; add `error_text: Mapped[str | None] = mapped_column(Text, nullable=True)` to `TestResult` (`execution_history.py` lines 58-76, after `exit_codes`). The classifier reads THIS column — without it the taxonomy collapses to exit codes only. **SC3 carry:** `job.py` must stay LLM-import-pure (the `test_no_llm_in_worker.py` gate scans it) — the edit adds no imports.

---

### `tests/functional/test_classifier_accuracy.py` (test, functional) — QUAL-03 — EXACT clone of the mutation harness

**Analog:** `tests/functional/test_healing_mutations.py`.

**Keyless-build labeled set + skip-when-down + threshold-from-settings** (`test_healing_mutations.py` lines 67, 87-115, 303-311):
```python
pytestmark = [pytest.mark.functional]
from app.core.config import settings as _settings
_MUTATION_HIGH = str(_settings.heal_high_threshold)   # prove the SHIPPED default, not a test literal

def _port_open(url: str) -> bool:                       # cheap TCP up-check
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False

def _require_targets() -> None:                          # skip cleanly when builds are down
    down = [n for n, u in _ALL_TARGETS.items() if not _port_open(u)]
    if down:
        pytest.skip("mutation-profile targets are not up ...")
```
**Labeled set (RESEARCH Pattern 3):** SEED_BUG build (8081) → `product_defect`; `BREAK_REMOVE` (8086) → `automation`; a DEAD PORT → `infrastructure`. Assert `accuracy >= 0.85` against `settings.jira_confidence_threshold` (NOT a literal — the line-89 discipline), print per-class confidences to calibrate the threshold.

**Net-new harness piece:** the `_port_open`-INVERSE dead-port / forced-timeout generator for the Infrastructure label (RESEARCH A6) — a non-listening port + a sub-second timeout, no Docker build needed.

---

### `tests/unit/test_no_llm_in_classifier.py` (test, grep gate) — EXACT clone

**Analog:** `tests/unit/test_no_llm_in_worker.py`.

**Comment-stripped import-token scan** (`test_no_llm_in_worker.py` lines 32-48, 61-76) — copy the `_FORBIDDEN` regex list + `_strip_comment_lines` + the offenders-walk, retargeted at `app/services/defects/classifier.py`:
```python
_FORBIDDEN = [re.compile(r"\binit_chat_model\b"), re.compile(r"\bllm_gateway\b"),
              re.compile(r"\bfrom\s+langchain\b"), re.compile(r"\bfrom\s+langgraph\b"), ...]
def _strip_comment_lines(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
```

---

### `apps/web/lib/api/defects.ts` (api client) — EXACT clone of scenarios.ts

**Analog:** `apps/web/lib/api/scenarios.ts` (the zod-mirrors-Pydantic + `api.post` mutation + invalidate-on-success pattern) over `apps/web/lib/api/client.ts` (the same-origin `/api/*` cookie-riding wrapper; 401→refresh→/login).

**zod summary/detail + fetchers + mutations** (`scenarios.ts` lines 34-91):
```python
export const scenarioSummarySchema = z.object({ id: z.number().int(), run_id: z.string(),
  flow_id: z.string(), status: z.string(), updated_at: z.string(), ... });
export const scenarioDetailSchema = scenarioSummarySchema.extend({ gherkin_text: z.string(), ... });
export async function listScenarios(status: string) {
  return scenariosListSchema.parse(await api.get(`/api/scenarios?status=${encodeURIComponent(status)}`));
}
export async function approveScenario(id: number) {
  return scenarioDetailSchema.parse(await api.post(`/api/scenarios/${id}/approve`));
}
```
**Apply:** `defectSummarySchema` (class/confidence/status/jira_key/source refs), `defectDetailSchema` (proposed issue + evidence + attachments + fingerprint + `confidence_threshold`), `calibrationSchema`; `listDefects(status, klass)`, `defectDetail(id)`, `calibration()`, `applyDefect(id)`, `rejectDefect(id)`. Field names MUST mirror `schemas/defect.py`.

---

### `apps/web/app/(dashboard)/defects/page.tsx` + `[id]/page.tsx` (component) — EXACT clone of scenarios pages

**List analog:** `apps/web/app/(dashboard)/scenarios/page.tsx` — the filter-segments + TanStack `useQuery` + table + empty/error/loading states.

**Deep-linkable filter segments (styled-native, NOT a tabs block)** (`scenarios/page.tsx` lines 83-104) — copy the accent-underlined `<button>` set for BOTH the `?status=` and `?class=` segments:
```tsx
<nav className="flex items-center gap-4" aria-label="Filter ...">
  {FILTERS.map((f) => (
    <button ... aria-current={active ? "true" : undefined}
      className={"border-b-2 pb-1 text-sm font-semibold ... " +
        (active ? "border-primary text-primary" : "border-transparent text-muted-foreground ...")}>
      {f.label}
    </button>
  ))}
</nav>
```

**Query + sort + empty/error gating** (`scenarios/page.tsx` lines 61-68, 106-136) — copy `useQuery({ retry: false })`, the `isEmpty` derivation, and the per-filter empty blocks + `ScenarioErrorState` inline (never a toast).

**Detail analog:** `apps/web/app/(dashboard)/scenarios/[id]/page.tsx` — the breadcrumb + header-with-badges + cards + action-bar + confirm-dialog + mutations-with-invalidate.

**Mutations, no optimistic update, invalidate list+detail, success-toast-only** (`scenarios/[id]/page.tsx` lines 82-128):
```tsx
function invalidate() {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: ["scenarios", "detail", id] }),
    queryClient.invalidateQueries({ queryKey: ["scenarios"] }),
  ]);
}
const approveMutation = useMutation({ mutationFn: () => approveScenario(id),
  onSuccess: async () => { await invalidate(); toast.success("Scenario approved"); ... } });
```
**Apply for Phase 9:** the Apply button shows the HONEST pending state (`isPending` → "Filing…" disabled) and flips to "Applied" + the real Jira key only on the server response (UI-SPEC §2; NO fake-instant success). The "create" vs "update {key}" label comes from the server dedup result. Reject reuses the `Dialog` confirm (lines 237-259). Also invalidate the `calibration` query.

**404 + loading skeletons** (`scenarios/[id]/page.tsx` lines 130-152) — copy the `ApiError && status === 404` branch + the skeleton blocks.

---

### `apps/web/components/app-sidebar.tsx` (MODIFY) — one-line append

**Analog:** the file itself (lines 36-51) — the `NAV_ITEMS` flat `{icon, label, href}` contract; the comment at line 31-33 already anticipates appended later-phase items.

**Append after "Executions"** (after line 50), `icon: Bug` (lucide), `href: "/defects"`, active via the existing `pathname.startsWith(item.href)` (line 83):
```tsx
{ icon: Bug, label: "Defects", href: "/defects" },   // explore → graph → scenarios → executions → defects
```

---

## Shared Patterns

### Deterministic decision over LLM (DEF-01 anti-pattern guard)
**Source:** `app/services/kg/risk.py` lines 1-12 + `app/services/worker/classifier.py` lines 1-17 (`# SC3: no LLM/gateway/explorer import`).
**Apply to:** `classifier.py`, `fingerprint.py`, `infra_health.py`, `adf.py` — all pure, stdlib-only, import NOTHING from the LLM/gateway/graph/DB path. Enforced by `test_no_llm_in_classifier.py`.

### Frozen-weights starting point, tuned by a keyless harness
**Source:** `app/core/config.py` lines 139-148 (`heal_high_threshold` tuning note) + `tests/functional/test_healing_mutations.py` line 89 (`_MUTATION_HIGH = str(_settings.heal_high_threshold)`).
**Apply to:** `classifier.py` weights + `settings.jira_confidence_threshold` — ship conservative starting points; the QUAL-03 harness asserts against the SHIPPED default so config can never silently drift from the proof.

### Auth-gated state-changing router
**Source:** `app/routers/heals.py` lines 53-59 (router-level `Depends(get_current_user)`).
**Apply to:** `app/routers/defects.py` — every endpoint, especially `apply`/`reject`/calibration. `require_role` does NOT exist; reuse `get_current_user`.

### Never-log the secret
**Source:** `app/core/config.py` lines 39, 130 (`anthropic_api_key` / `ci_token` optional-default) + `app/services/llm_gateway.py` lines 43-46, 468-478 (no key in any log event; SENSITIVE regex matches "token"/"password").
**Apply to:** `jira_api_token` in config + `jira/client.py` structlog events — keep the token out of log keys AND values entirely.

### Run_id-derived artifact paths (no request paths)
**Source:** `app/routers/executions.py` lines 235-259 (`execution_artifact` multi-segment containment guard) + `app/routers/heals.py` lines 104-105 (`pages_dir = run_dir(heal.run_id) / ...`, never a request path).
**Apply to:** the defect detail's attachment links + the `apply` path that streams artifacts to Jira — paths are always `run_dir(run_id)`-derived.

### Honest UI state (no fabrication)
**Source:** `apps/web/app/(dashboard)/scenarios/[id]/page.tsx` lines 16-18, 200-201 (server-authoritative, no optimistic updates) + `app/(dashboard)/scenarios/page.tsx` lines 106-136 (inline errors, never a toast).
**Apply to:** the defects list + detail — class/confidence/status/jira_key/accuracy render strictly from the server payload; Apply is a real pending→result transition; errors inline, success toasts only.

### Fresh SessionLocal in non-request services
**Source:** `app/services/worker/job.py` lines 178-213 (`async with SessionLocal() as db:` — the worker owns its session, never a request's).
**Apply to:** `defects/pipeline.py` (the post-run orchestrator runs outside a request).

### Migration chain discipline
**Source:** `alembic/versions/0008_heal_audit.py` lines 22-24, 55-60 (`down_revision='0007'` + reverse-order downgrade).
**Apply to:** `0009_defects.py` (`down_revision='0008'`, reversible round-trip).

---

## No Analog Found / Net-New Mechanisms

The planner should treat these as NEW (RESEARCH is the reference, not a repo file):

| File / Mechanism | Role | Data Flow | Reason |
|------------------|------|-----------|--------|
| `app/services/jira/fake.py` (`FakeJira`) | test double | request-response | No in-memory double / contract fake exists anywhere in the repo — the codebase uses real-subprocess + skip-when-down harnesses, not doubles. Fully net-new (RESEARCH Code-Examples). |
| `JiraGateway` Protocol + `anyio.to_thread` wrap (in `client.py`) | service seam | request-response (external) | No `Protocol`-based gateway seam and no `anyio.to_thread.run_sync` sync-offload exist in the repo. `llm_gateway.py` is the nearest gateway *shape* but is async-native (no sync-client offload). Net-new (RESEARCH Pattern 4). |
| The 3-way taxonomy *rules body* (inside `classifier.py`) | service logic | transform | The `classifier.py` SHAPE clones `kg/risk.py` exactly, but the evidence-taxonomy → class rules + the 60/20/-15 weights have no repo precedent — they are RESEARCH Pattern 1 starting points the QUAL-03 harness tunes. |
| The dead-port / forced-timeout infra-fault generator (in `test_classifier_accuracy.py`) | test helper | event-driven | The Infrastructure label has no existing generator; it EXTENDS the harness with a `_port_open`-inverse (RESEARCH A6). The seeded-bug + mutation builds for the other two classes ARE reused verbatim. |
| The ADF v3 doc-dict builder (in `adf.py`) | utility | transform | The pure-builder DISCIPLINE has an analog (`explorer/fingerprint.py`), but the ADF doc shape itself is RESEARCH Code-Examples content with no repo twin (Pitfall 2: must be a dict, not a string, on Cloud v3). |

---

## Direct-Reuse Seams (no net-new logic — copy the shipped pattern)

- **`kg/risk.py` + `healing/confidence.py`** → `classifier.py` (frozen-weights, clamped score, gate-first precedence).
- **`explorer/fingerprint.py`** → `fingerprint.py` (hashlib + compiled-regex normalize).
- **`worker/job.py`** → `pipeline.py`/`evidence.py` (fresh SessionLocal post-run orchestrator + read joins) AND the Pitfall-1 error-text edit (the gap is in this same file).
- **`test_healing_mutations.py`** → `test_classifier_accuracy.py` (keyless build harness, skip-when-down, threshold-from-settings).
- **`test_no_llm_in_worker.py`** → `test_no_llm_in_classifier.py` (comment-stripped import grep).
- **`heals.py`** → `defects.py` (auth-gated list/apply/reject) + **`executions.py`** artifact route (containment guard).
- **`heal_audit.py` + `execution_history.py`** → `models/defects.py`; **`0008_heal_audit.py`** → `0009_defects.py`.
- **`schemas/heal.py`** → `schemas/defect.py` (from_attributes Pydantic v2).
- **`config.py`** `ci_token`/`heal_high_threshold` blocks → the new Jira settings block (extend in place).
- **`scenarios/page.tsx` + `[id]/page.tsx` + `lib/api/scenarios.ts` + `lib/api/client.ts`** → the defects list+detail+api (filter segments, mutations-with-invalidate, honest states, zod-mirrors-Pydantic).
- **`app-sidebar.tsx`** `NAV_ITEMS` → the "Defects" append; **`main.py`** include_router → register `defects_router`.

---

## Metadata

**Analog search scope:** `apps/api/app/services/{kg,healing,worker,explorer,jira,defects}`, `apps/api/app/{models,schemas,routers,core}`, `apps/api/alembic/versions/`, `apps/api/tests/{unit,functional}`, `infra/targets/saucedemo/`, `apps/web/{app/(dashboard)/{scenarios,executions},lib/api,components}`.
**Files scanned (read in full or targeted):** 18 source/test files + 2 planning docs (CONTEXT, RESEARCH, UI-SPEC).
**Pattern extraction date:** 2026-06-27
