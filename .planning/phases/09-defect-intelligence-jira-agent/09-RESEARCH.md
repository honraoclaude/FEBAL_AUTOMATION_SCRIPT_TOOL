# Phase 9: Defect Intelligence & Jira Agent - Research

**Researched:** 2026-06-27
**Domain:** Deterministic failure classification + 0-100 confidence, keyless accuracy-calibration harness (QUAL-03), Jira Cloud REST v3 agent (atlassian-python-api 4.x), defect data model + draft-review queue
**Confidence:** HIGH on architecture/patterns/data-model (all mirror shipped Phase 6/7/8 code); MEDIUM on the exact classifier weights + the calibrated confidence threshold (starting points, tuned by the QUAL-03 harness — the kg/risk.py / healing/confidence.py precedent: HIGH on the shape, LOW on the exact numbers); MEDIUM on atlassian-python-api 4.x ADF call shape (verified method names; the ADF-as-dict-on-Cloud-v3 detail carries a known library friction point — Pitfall 6).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01** Deterministic-first classifier: rules over evidence → {Infrastructure, Automation, Product Defect} + 0-100 confidence. LLM (gateway) used ONLY to enrich Jira description prose (operation_type e.g. `defect.describe`, run_id), with deterministic no-key fallback — NEVER for the class/confidence decision. Keyless, calibratable, reproducible.
- **D-02 (DEF-02)** Classification runs AFTER the Phase-7 retry loop (pass-on-retry = flaky/infra; all-fail = real failure to classify). Cites evidence: error type (TestResult output), DOM diff + healing history (heal_audit), infra health. Phase-7 binary retry/flaky classifier is an INPUT, not replaced.
- **D-03** atlassian-python-api 4.x — Jira Cloud REST v3 (create/attach/transition/JQL/links; enhanced_jql nextPageToken pagination; v3/ADF). SYNC (requests) → call via `anyio.to_thread.run_sync`. ONE gated new dep (checkpoint:human-verify install). Auth = Jira Cloud email + API token (config, never logged).
- **D-04** Autonomous filing OFF by default (`jira_autonomous_enabled = False`, per target). Human reviews QUAL-03 accuracy + draft precision then EXPLICITLY flips the flag. Until then ALL issues stay in draft/review queue (human apply/reject). Even flag-on requires confidence ≥ calibrated threshold. No autonomous ticket before human confirms accuracy ≥85% AND draft precision ≥90%.
- **D-05** Fingerprint = stable hash(class + NORMALIZED error message [strip numbers/ids/timestamps/uuids] + flow id + failing step). Stored as Jira LABEL `fp-<hash>` AND on local defect row. Dedup = JQL `labels = "fp-<hash>" AND statusCategory != Done` — hit UPDATES (comment + re-attach), miss CREATES. Per-run cap via config'd counter (`jira_max_tickets_per_run`). Local row stores Jira key.
- **D-06** Phase 9 ships a MINIMAL draft-review-queue UI (own UI-SPEC): list draft issues + rendered classification (class + confidence + cited evidence) + steps/attachment links + apply/reject + a calibration panel (accuracy + draft-precision). Rich traceability viz + dashboards + RBAC → Phase 10. Zero new shadcn / native-styled (Phase 6/7 precedent).

### Claude's Discretion
- Concrete evidence-taxonomy → class rules + the 0-100 confidence formula/weights (tuned by labeled set).
- QUAL-03 labeled set generation (seeded-bug → Product; un-healed mutation → Automation; injected infra → Infrastructure); accuracy + threshold calibration compute + storage.
- Defect/classification data model + migration 0009; heal_audit/execution_history evidence joins.
- atlassian-python-api v3 call shapes; anyio.to_thread wrapping; draft-queue model + apply/reject.
- The infra-health evidence source.
- Traceability-chain representation (Postgres FKs + Jira key, and/or KG links) for Phase 10.

### Deferred Ideas (OUT OF SCOPE)
- Classification/defect DASHBOARDS + trend analytics + rich traceability VISUALIZATION + RBAC + Elasticsearch defect search → Phase 10.
- LLM create_agent tool-loop classifier → REJECTED for class/confidence decision (LLM is description-prose only).
- Local-DB-only dedup → REJECTED (JQL-based per spec; local row stores Jira key for traceability, not dedup source of truth).
- K8s/Prometheus defect/classification metrics → Phase 11.
- Bi-directional Jira sync / webhooks (status flowing back) → not v1.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEF-01 | Every failure classified Infrastructure / Automation / Product Defect with a 0–100 confidence | The deterministic taxonomy + frozen-weights confidence blend in Architecture Pattern 1 + 2; mirrors kg/risk.py & healing/confidence.py |
| DEF-02 | Failures retried before classification; classification cites evidence (error type, DOM diff, healing history, infra health) | Runs after the Phase-7 retry/reconcile (`classify_retry` + `reconcile_verdict`, job.py); evidence joins from TestResult.output (NEW column — see Runtime State / Pitfall 1), heal_audit, infra-health probe (Pattern 5) |
| DEF-03 | Classification accuracy measured against a hand-labeled set before autonomous filing | QUAL-03 keyless harness (Pattern 3) reusing SEED_BUG + mutation builds + injected infra failures; accuracy + calibrated threshold computed & stored (Pattern 3 + config) |
| JIRA-01 | Create Jira Cloud issues w/ summary, description, steps, expected/actual, severity, priority, screenshots, video, logs | atlassian-python-api 4.x `create_issue` (ADF v3 description) + `add_attachment` from TestArtifact paths (Pattern 4); LLM prose enrich for description (gateway, no-key fallback) |
| JIRA-02 | Draft/review queue; autonomous creation only above threshold + after >90% draft precision | Draft-queue model + apply/reject router (mirrors heals.py); the D-04 autonomy gate (Pattern 6) |
| JIRA-03 | Dedup via fingerprint + JQL; existing issues updated not duplicated; per-run cap | Fingerprint (stdlib hashlib/re, Pattern 5) + `enhanced_jql` dedup (Pattern 4) + per-run cap counter (config) |
| JIRA-04 | Created issues linked to test/flow/execution; links in traceability chain | Defect-row FKs (run_id/flow_id) + jira_key + `create_issue_link`; Postgres FK representation for Phase 10 (Pattern 4 + data model) |
| QUAL-03 | Labeled set measures accuracy (>85%) and calibrates the Jira confidence threshold | Same harness as DEF-03; the calibrated threshold persisted to settings (mirrors heal_high_threshold 08-04 tuning) |
</phase_requirements>

## Summary

Phase 9 turns every all-fail test failure (post Phase-7 retry) into a **classified, evidenced, deduplicated Jira draft**. The shape is already proven three times in this codebase: a **pure, keyless, frozen-weights deterministic decision** (`kg/risk.py` risk score, `healing/confidence.py` heal blend, `worker/classifier.py` retry verdict), an **auth-gated apply/reject review router** (`heals.py`), and a **keyless mutation-build accuracy harness** (`test_healing_mutations.py` for QUAL-02). Phase 9 is the fourth instance of each pattern. There is essentially **zero novel architecture** — the work is composing these patterns for a 3-way classifier, a Jira client, and a defect data model.

Two genuine gaps must be closed by the plan. **(1) Error text is not persisted today.** `_run_spec_once` (stability.py) returns `{passed, exit_code, output}` with `output` = the tail-capped (8000-char) combined stdout/stderr, but `job.py` stores only `exit_codes` into `TestResult` and **discards `output`**. The classifier needs the error text to classify by error type, so migration 0009 must add an error-text column to `test_results` (or a `classifications.evidence` JSON) and `job.py` must persist the last attempt's `output`. **(2) The classifier weights + the calibrated confidence threshold are starting points, not facts** — exactly like the heal bands, which 08-04's mutation harness empirically tuned from unreachable 0.85/0.60 down to the shipped 0.15/0.10. The QUAL-03 harness is the instrument that tunes the Phase-9 threshold the same way.

The keyless/Manual-Only split is sharp and favorable: the **classifier, the QUAL-03 accuracy harness, fingerprint/dedup-logic/cap, the draft queue, and the Jira contract against a FAKE client** are all keyless-CI-testable. Only **live LLM description enrichment** (needs provider keys) and **live filing against a real Jira Cloud + token** are Manual-Only.

**Primary recommendation:** Build a pure `services/defects/classifier.py` (frozen-weights, stdlib-only, fixture-tested — clone the `kg/risk.py` discipline byte-for-byte), persist error text in migration 0009 alongside a `classifications` + `defects` table, wrap atlassian-python-api 4.x in a thin `services/jira/client.py` behind a `JiraGateway` Protocol so a `FakeJira` makes JIRA-01/03 logic keyless-testable, and gate all filing behind the draft queue + the `jira_autonomous_enabled` flag. Add exactly ONE dependency: `atlassian-python-api==4.0.*` (gated checkpoint:human-verify). `anyio` ships transitively with FastAPI/Starlette — verify, don't add.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 3-way classification + 0-100 confidence | API / Backend (pure service) | — | Deterministic decision over DB evidence; no browser, no LLM, no network — a pure module like kg/risk.py |
| Evidence gathering (error type, DOM diff, heal history, infra health) | API / Backend | Worker plane (writes the error-text column) | Reads test_results/heal_audit; infra-health probe reads container/healthcheck state — backend owns the join |
| QUAL-03 accuracy harness | Test/CI plane | Docker (mutation + infra-fault builds) | Keyless functional test; reuses the mutation-profile + a dead-port infra fault, like test_healing_mutations.py |
| Jira issue create/attach/JQL/link | API / Backend (sync client via anyio.to_thread) | External (Jira Cloud) | atlassian-python-api is sync/requests; offloaded to a worker thread from async FastAPI |
| Fingerprint / dedup / per-run cap | API / Backend (pure helpers + JQL) | External (JQL is source of truth) | Hash is pure stdlib; dedup is a live JQL query — self-heals across external edits |
| Draft-review queue + apply/reject | API / Backend (auth-gated router) | Browser (minimal UI, D-06) | Mirrors heals.py exactly; UI is a thin list+actions surface |
| Autonomy gate (flag + threshold) | API / Backend (config + guard) | — | Structural gate; OFF by default; no UI authority to file autonomously |
| Description prose enrichment | API / Backend (LLM gateway) | External (Anthropic/OpenAI) | The ONLY LLM use; deterministic no-key fallback so the path is keyless-safe |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| atlassian-python-api | 4.0.* (4.0.7 latest) | Jira Cloud REST v3 client: create/attach/transition/JQL/links; `enhanced_jql` nextPageToken pagination; v3/ADF | The CLAUDE.md-locked choice (D-03); the `jira` pycontribs package broke during Atlassian's 2025 v2→v3 search migration; 4.x is the v3-native line |
| anyio | (transitive via FastAPI/Starlette) | `anyio.to_thread.run_sync` to call the SYNC Jira client from async FastAPI | Already in the tree (FastAPI dep); the canonical sync→async offload; gateway already uses async patterns. **VERIFY present; do NOT add** |
| hashlib + re | stdlib | Fingerprint hash + error-message normalization | D-05 mandates stripping numbers/ids/timestamps/uuids; pure, deterministic, unit-testable — NO new package |
| SQLAlchemy | 2.0.* (in tree) | `classifications` + `defects` ORM models | The shipped async ORM pattern (execution_history.py / heal_audit.py) |
| Alembic | 1.18.* (in tree) | Migration 0009 (chains down_revision='0008') | The shipped migration chain; lives in `apps/api/alembic/versions/` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| langchain (init_chat_model via llm_gateway) | in tree | Jira description PROSE enrichment ONLY (operation_type `defect.describe`) | When provider keys exist; deterministic no-key fallback otherwise — NEVER for the class/confidence decision (D-01) |
| structlog | in tree | Defect/Jira lifecycle logging | All services; NEVER log the Jira token (SENSITIVE regex; mirror the ci_token pattern) |
| httpx | 0.28.* (in tree) | The v3 fallback for any endpoint atlassian-python-api lacks (already a dep) | Only if a needed v3 endpoint is missing from the library; prefer the library |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| atlassian-python-api | raw httpx against REST v3 | httpx is natively async (no anyio.to_thread) and ~200 lines for create+attach+transition; but JQL search + issue links + ADF push the balance to the library (CLAUDE.md decided this exactly for Phase 9 scope). LOCKED to the library by D-03 |
| Pure deterministic classifier | LLM create_agent tool-loop classifier | REJECTED (D-01, Deferred): a number users act on must be reproducible, auditable, free, and QUAL-03-measurable without keys |
| Frozen-weights confidence blend | calibrated ML model | Overkill + opaque; the frozen-weights blend is the shipped house style (risk/confidence) and is directly tunable by the labeled set |

**Installation:**
```bash
# ONE gated dependency (checkpoint:human-verify before install):
uv add "atlassian-python-api==4.0.*"
# anyio is already present (FastAPI/Starlette transitive) — verify, do NOT add:
uv run python -c "import anyio; print(anyio.__version__)"
```

**Version verification (run 2026-06-27):**
- `pip index versions atlassian-python-api` → 4.0.7 latest (4.0.0–4.0.7 on the 4.x line). Matches CLAUDE.md's pinned 4.0.x. HIGH confidence.

## Package Legitimacy Audit

> ONE new dependency this phase. slopcheck was unavailable at research time → the package is tagged `[ASSUMED]` and the planner MUST gate the install behind a `checkpoint:human-verify` task (the aio-pika / recharts precedent).

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| atlassian-python-api | PyPI | mature (1.x → 4.x, years of releases) | high (widely used Atlassian wrapper) | github.com/atlassian-api/atlassian-python-api | unavailable | Approved — gated checkpoint:human-verify (locked by CLAUDE.md D-03) `[ASSUMED]` |
| anyio | PyPI | mature | very high (Starlette/FastAPI dep) | github.com/agronholm/anyio | unavailable | NOT a new install — transitive; verify presence only |

**Packages removed due to slopcheck [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

*slopcheck could not be installed in the research environment. Per protocol, `atlassian-python-api` is tagged `[ASSUMED]`; the planner inserts a `checkpoint:human-verify` task before the install (which the aio-pika/recharts gated-dep precedent already establishes). The package is the CLAUDE.md-locked choice and was confirmed present on PyPI at 4.0.7 via `pip index versions`.*

**Zero other new packages:** fingerprinting uses stdlib `hashlib` + `re`; the Jira-contract test uses a hand-written `FakeJira` (no recorded-HTTP library, no `responses`/`vcrpy`); the calibration panel uses native styling (recharts already addressed in Phase 7, prefer native for a minimal panel).

## Architecture Patterns

### System Architecture Diagram

```
  Phase-7 worker (job.py)
   run flow → 2x retry loop → classify_retry + reconcile_verdict (exit codes + heal journal)
        │  verdict ∈ {passed, flaky, auto_healed, quarantined, product_failure, aborted}
        │  [NEW] persist last-attempt error `output` text  ──────────────┐
        ▼                                                                 │
   TestResult (verdict, attempts, exit_codes, [NEW] error_text)          │
   TestArtifact (screenshot|trace|video paths)   HealAudit (DOM diff, heal history, outcome)
        │                                                │                │
        └──────────────────┬─────────────────────────────┘                │
                           ▼                                               │
         ┌─────────── DEFECT INTELLIGENCE (post-run, only verdict==product_failure) ───────────┐
         │  evidence gather: error_text + heal_audit(DOM diff, heal history) + infra-health probe │
         │              │                                                                          │
         │              ▼                                                                          │
         │   classifier.classify(evidence)  ── PURE, frozen weights, NO LLM ──►  {class, conf 0-100}│
         │              │                                                                          │
         │              ▼                                                                          │
         │   class == Product Defect AND conf high enough? ──no──► persist classification only     │
         │              │ yes                                                                       │
         │              ▼                                                                          │
         │   fingerprint = hash(class + normalize(msg) + flow + step)                              │
         │              ▼                                                                          │
         │   JiraGateway.search_jql(labels="fp-<hash>" AND statusCategory != Done)                 │
         │              │                                                                          │
         │     hit ─────┴──── miss                                                                 │
         │      │              │ (per-run cap not exceeded)                                        │
         │      ▼              ▼                                                                    │
         │  draft: update    draft: create  (description prose ← LLM gateway, no-key fallback)      │
         │              │                                                                          │
         │              ▼                                                                          │
         │   Defect row (status=draft, fingerprint, jira_label, run_id, flow_id, jira_key=NULL)    │
         └──────────────────────────────────────────────────────────────────────────────────────┘
                           │
       ┌───────────────────┴───────────────────────────────────────────┐
       ▼ (D-04 autonomy OFF: default)                                   ▼ (autonomy ON + conf≥threshold)
   /api/defects review queue (auth-gated)                          auto-file path (same JiraGateway calls)
   human apply → JiraGateway.create_issue / add_attachment / create_issue_link → jira_key persisted
   human reject → status=rejected
       │
       ▼
   Minimal review-queue UI (D-06): list drafts + classification + evidence + apply/reject + calibration panel
```

### Recommended Project Structure
```
apps/api/app/
├── services/
│   ├── defects/
│   │   ├── classifier.py      # PURE frozen-weights 3-way + 0-100 conf (clone kg/risk.py discipline)
│   │   ├── evidence.py        # gather evidence dict from test_results + heal_audit + infra-health
│   │   ├── fingerprint.py     # PURE: normalize(msg) + hash(class+msg+flow+step) — stdlib only
│   │   └── pipeline.py        # post-run orchestrator: classify → fingerprint → dedup → draft (async, DB)
│   ├── jira/
│   │   ├── client.py          # JiraGateway Protocol + AtlassianJira (sync, anyio.to_thread wrapped)
│   │   ├── adf.py             # PURE: build the ADF v3 description doc (summary/steps/expected/actual/severity)
│   │   └── fake.py            # FakeJira — in-memory, records calls; the keyless-CI contract double
│   └── infra_health.py        # the infra-health evidence source (container/healthcheck or error-pattern)
├── models/
│   └── defects.py             # Classification + Defect ORM (mirror execution_history.py / heal_audit.py)
├── schemas/
│   └── defect.py              # *Response Pydantic v2 (from_attributes), like schemas/heal.py
├── routers/
│   └── defects.py             # auth-gated list/apply/reject + calibration GET (mirror heals.py)
└── alembic/versions/
    └── 0009_defects.py        # classifications + defects tables + test_results.error_text (down_revision='0008')
```

### Pattern 1: Pure deterministic 3-way classifier (DEF-01) — clone kg/risk.py + healing/confidence.py
**What:** A stdlib-only module: a `@dataclass(frozen=True)` of tunable weights, a pure `classify(evidence) -> (class, confidence)` that maps the error-type taxonomy to a class and computes a clamped 0-100 confidence. Imports NOTHING from the DB session, graph driver, LLM path, or browser (the SC3-style grep gate scans it).
**When to use:** The DEF-01/02 decision. ALWAYS — the LLM is never on this path.
**The error-type taxonomy → class (D-01/D-02 mapping):**

| Class | Signals (from evidence) | Examples |
|-------|-------------------------|----------|
| **Infrastructure** | browser crash / `Target closed` / `Browser has been closed`; network: `ERR_CONNECTION_REFUSED`, DNS, `net::ERR_`; timeout reaching the target / page never loaded; env: target port dead (infra-health probe = down) | a dead target port, a forced timeout, a Chromium crash |
| **Automation** | locator failure AFTER an un-healed / quarantined / fail_as_defect heal (heal_audit shows the element couldn't be re-found); selector not found with the page otherwise loaded; test-data mismatch (login/fixture data wrong) | un-healed locator drift (BREAK_REMOVE-style), a stale test fixture |
| **Product Defect** | assertion failure on a SUCCESSFULLY-LOADED page (page rendered, the app behaved wrong); functional/validation error; API 4xx/5xx from the app under test; the SEED_BUG signature (`.inventory_list` assertion target broke) | the seeded bug (post-login assertion fails), a broken business rule |

**Example (the shape to clone):**
```python
# Source: mirror apps/api/app/services/kg/risk.py + healing/confidence.py (shipped, byte-faithful discipline)
from __future__ import annotations
from dataclasses import dataclass

INFRA, AUTOMATION, PRODUCT = "infrastructure", "automation", "product_defect"

@dataclass(frozen=True)
class ClassifierWeights:
    """FROZEN starting-point weights (RESEARCH: HIGH on shape, LOW on exact values — tuned by QUAL-03)."""
    # confidence contributions per corroborating signal (0-100 clamp at the end)
    strong_class_signal: int = 60   # an unambiguous class signal present (e.g. ERR_CONNECTION_REFUSED)
    corroborating_signal: int = 20  # each additional same-class signal (heal history, infra-health, page-loaded)
    weak_or_conflicting: int = -15  # a cross-class signal present (lowers confidence)

DEFAULT_WEIGHTS = ClassifierWeights()

def classify(evidence: dict, w: ClassifierWeights = DEFAULT_WEIGHTS) -> dict:
    """PURE: evidence dict -> {class, confidence 0-100, cited}. No I/O, no LLM, no browser.

    evidence keys (any absent -> falsey): error_text(str), page_loaded(bool),
    heal_outcome(str|None ∈ auto_heal/quarantine/fail_as_defect/None), infra_health(str ∈ up/down/unknown),
    flow_id(str), step(str).
    """
    cited: list[str] = []
    # 1) deterministic class rules over the taxonomy (order = precedence; infra first, product last default)
    cls = _classify_rules(evidence, cited)
    # 2) clamped weighted confidence from the count/strength of corroborating signals for `cls`
    raw = w.strong_class_signal + w.corroborating_signal * _corroboration(cls, evidence)
    raw += w.weak_or_conflicting * _conflict(cls, evidence)
    confidence = max(0, min(100, raw))
    return {"classification": cls, "confidence": confidence, "cited": cited}
```
The exact rule/weight bodies are the planner's to fill, tuned by the QUAL-03 labeled set (Pattern 3) — the values above are RESEARCH starting points (the kg/risk.py / heal-bands precedent: ship a starting point, let the harness tune it).

### Pattern 2: Calibrated confidence threshold (DEF-03/QUAL-03) — mirror the heal-band tuning (08-04)
**What:** A config-tunable `jira_confidence_threshold` (default a conservative starting point), the floor at which a Product-Defect classification is eligible for autonomous filing. The QUAL-03 harness derives the empirically separating value (exactly how 08-04 tuned `heal_high_threshold` from an unreachable 0.85 to the shipped 0.15 after measuring live confidences).
**When to use:** The filing eligibility check (autonomy gate, Pattern 6) reads `settings.jira_confidence_threshold` — never a hardcoded literal (the heal_high_threshold precedent).

### Pattern 3: Keyless accuracy harness (QUAL-03) — clone test_healing_mutations.py
**What:** A functional test that generates KNOWN-class failures keylessly, runs the classifier over each, and asserts `accuracy >= 0.85` against the hand-labels, then prints the per-class confidences that calibrate the threshold.
**The labeled set (keyless generation — reuse the shipped infra):**

| Label (known class) | Generator | Source |
|---------------------|-----------|--------|
| **Product Defect** | SEED_BUG build (`saucedemo-bug`, `.inventory_list`→`_BROKEN`) → the post-login assertion fails on a loaded page | `test_seeded_bug.py` + Dockerfile `SEED_BUG=1` (port 8081) |
| **Automation** | un-healed breaking mutation: `BREAK_REMOVE` (deleted element → fail_as_defect, no auto_heal) | `test_healing_mutations.py` + Dockerfile `BREAK_REMOVE` (port 8086) |
| **Infrastructure** | injected infra fault: point the run at a DEAD port (connection refused) or force a sub-second timeout | NEW: a `_port_open`-style dead target (mirror the harness's `_port_open` skip pattern, inverted) |

**Example (the harness shape):**
```python
# Source: clone apps/api/tests/functional/test_healing_mutations.py (QUAL-02 harness, keyless, deterministic)
async def test_classifier_accuracy_meets_85pct_and_calibrates_threshold():
    _require_targets()  # skip cleanly if mutation/seed builds are down (mirror test_seeded_bug.py)
    cases = [
        ("product_defect", run_against(SEED_BUG_URL)),      # SEED_BUG → loaded-page assertion fail
        ("automation",     run_against(BREAK_REMOVE_URL)),  # un-healed locator drift
        ("infrastructure", run_against(DEAD_PORT_URL)),     # connection refused / forced timeout
        # ... multiple instances per class for a meaningful denominator
    ]
    correct, confs_by_class = 0, {}
    for expected, result in cases:
        ev = gather_evidence(result)          # the same evidence join the pipeline uses
        got = classify(ev)                    # PURE classifier — the production module, no keys
        if got["classification"] == expected:
            correct += 1
        confs_by_class.setdefault(expected, []).append(got["confidence"])
    accuracy = correct / len(cases)
    assert accuracy >= 0.85, f"classification accuracy {accuracy:.2f} < 0.85 :: {confs_by_class}"
    # the separating threshold for autonomous filing is derived from confs_by_class[product_defect]
    # vs the misclassified tail — printed/asserted to calibrate settings.jira_confidence_threshold
```
**Keyless:** no provider keys, no real Jira — the classifier is pure and the failures come from Docker builds. neo4j OFF during the run phase (3GB cap), same sequencing as Phase 7/8.

### Pattern 4: Jira agent via atlassian-python-api 4.x behind a Protocol (JIRA-01/03/04)
**What:** A `JiraGateway` Protocol with an `AtlassianJira` implementation (the sync library, every call wrapped in `anyio.to_thread.run_sync`) and a `FakeJira` in-memory double for keyless CI. The pipeline/router depend on the Protocol — so JIRA-01/03 logic is fully keyless-testable.
**The 4.x call shapes (verified method names — see Sources):**
```python
# Source: atlassian-python-api 4.x docs (readthedocs jira.html) + Jira Cloud REST v3
from atlassian import Jira

# CRUCIAL: cloud=True + api_version="3" so the description accepts an ADF doc (Pitfall 6)
jira = Jira(url=settings.jira_url, username=settings.jira_email,
            password=settings.jira_api_token, cloud=True, api_version="3")

# CREATE (ADF v3 description — a dict, not a string, on Cloud v3)
fields = {
    "project": {"key": settings.jira_project_key},
    "issuetype": {"name": "Bug"},
    "summary": summary,
    "description": adf_doc,            # build_adf(...) from adf.py — the ADF doc dict
    "labels": [f"fp-{fingerprint}"],   # D-05 fingerprint label
    "priority": {"name": priority},    # mapped from severity
}
issue = jira.create_issue(fields=fields)      # -> {"key": "PROJ-123", ...}

# ATTACH (screenshots/video/logs from TestArtifact.path, resolved via workspaces.run_dir)
jira.add_attachment(issue_key, str(artifact_abs_path))   # repeat per artifact

# DEDUP SEARCH (enhanced_jql — the 2025 nextPageToken pagination)
res = jira.enhanced_jql(f'labels = "fp-{fingerprint}" AND statusCategory != Done')
existing = res["issues"]   # hit -> update that key; res also has isLast / nextPageToken

# UPDATE-ON-DUP (add a comment + re-attach new evidence)
jira.issue_add_comment(existing_key, adf_comment)   # ADF comment on v3
jira.add_attachment(existing_key, str(new_artifact_abs_path))

# LINK test↔flow↔execution (JIRA-04) — issue links are Jira-side; the test/flow/exec live in Postgres FKs
jira.create_issue_link({"type": {"name": "Relates"},
                        "inwardIssue": {"key": child}, "outwardIssue": {"key": parent}})

# TRANSITION (if a draft is filed then moved)
jira.issue_transition(issue_key, "In Progress")
```
**anyio wrapping (sync → async):**
```python
# Source: anyio (FastAPI transitive) — the canonical sync-client offload from async FastAPI
import anyio
async def create_issue(self, fields: dict) -> dict:
    return await anyio.to_thread.run_sync(lambda: self._jira.create_issue(fields=fields))
```
**Note on JIRA-04:** the *traceability chain* is primarily **Postgres FKs** (the Defect row carries run_id + flow_id + jira_key, joinable to TestRun/TestResult and the kg/flows id). `create_issue_link` is the optional Jira-side link between related Jira issues. Phase 10 *renders* the chain; Phase 9 persists the data (the Defect row IS the link).

### Pattern 5: Fingerprint + dedup + per-run cap (JIRA-03/D-05) — stdlib only
**What:** Pure `fingerprint.py`: normalize the error message (strip digits, UUIDs, ISO timestamps, hex ids), then `hashlib.sha1(f"{cls}|{norm}|{flow}|{step}").hexdigest()[:N]`. Dedup is the JQL query (Pattern 4). The per-run cap is a counter compared to `settings.jira_max_tickets_per_run`.
```python
# Source: stdlib re + hashlib — pure, unit-testable (NO new package)
import hashlib, re
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_TS   = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*")
_HEX  = re.compile(r"\b0x[0-9a-f]+\b", re.I)
_NUM  = re.compile(r"\d+")
def normalize(msg: str) -> str:
    s = _UUID.sub("<uuid>", msg); s = _TS.sub("<ts>", s)
    s = _HEX.sub("<hex>", s);     s = _NUM.sub("<n>", s)
    return " ".join(s.split())
def fingerprint(cls: str, msg: str, flow_id: str, step: str) -> str:
    key = f"{cls}|{normalize(msg)}|{flow_id}|{step}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]   # label fp-<hash>
```

### Pattern 6: Autonomy gate (D-04 / JIRA-02) — structural, OFF by default
**What:** Filing autonomously requires BOTH `settings.jira_autonomous_enabled` (per-target flag, default False) AND `confidence >= settings.jira_confidence_threshold` (the calibrated value). Until a human reviews accuracy (≥85%) + draft precision (≥90%) and flips the flag, EVERY classification stays a draft for human apply/reject. Mirror the conservative heal-banding + the kill-switch flag style.
```python
def may_autofile(conf: int) -> bool:
    return settings.jira_autonomous_enabled and conf >= settings.jira_confidence_threshold
```

### Pattern 7: Auth-gated draft-review router (JIRA-02) — clone heals.py
**What:** `/api/defects` with router-level `Depends(get_current_user)`; `GET ?status=draft` lists the queue with the classification + evidence; `POST /{id}/apply` files/updates to Jira (via the gateway) + persists jira_key + status=applied; `POST /{id}/reject` flips status=rejected; `GET /calibration` surfaces the accuracy + draft-precision numbers for the human gate. ORM-parameterized (no string SQL); run_id-derived artifact paths (never request paths) — the heals.py security carry-forward.

### Anti-Patterns to Avoid
- **LLM on the class/confidence path:** forbidden (D-01). The LLM only writes description prose with a no-key fallback. A grep-gate (`test_no_llm_in_classifier`, mirror `test_no_llm_in_worker.py`) should assert the classifier module imports no LLM path.
- **Local-DB-only dedup:** rejected (D-05). The JQL label search is the source of truth so dedup self-heals across external Jira edits; the local row stores the key for traceability only.
- **Hardcoding the confidence threshold or weights in the module:** they are config/dataclass values tuned by QUAL-03 (the heal_high_threshold precedent — `_MUTATION_HIGH = str(_settings.heal_high_threshold)`).
- **Logging the Jira token:** never (mirror ci_token; the SENSITIVE regex matches "token"/"password" — keep auth out of log events entirely).
- **Passing a string description to Cloud v3:** on `api_version="3"` the description must be an ADF doc dict (Pitfall 6).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Jira REST v3 client (create/attach/JQL/links/ADF) | A bespoke httpx Jira wrapper | atlassian-python-api 4.x (D-03) | Handles enhanced_jql nextPageToken pagination, ADF, attachment multipart, auth — the exact 2025 v3 migration the `jira` pkg botched |
| sync→async offload | A thread pool / `loop.run_in_executor` by hand | `anyio.to_thread.run_sync` | Already in the tree; FastAPI's own bridge; cancellation-aware |
| Error-message normalization | regex you invent ad hoc each call | The pure `normalize()` helper (one place, unit-tested) | D-05 needs stable stripping; one tested function, fingerprint determinism depends on it |
| Keyless Jira contract test | A real Jira sandbox in CI | `FakeJira` in-memory double behind the `JiraGateway` Protocol | No token/instance in dev; the contract (calls + shapes) is asserted against the fake; live filing is Manual-Only |
| Accuracy harness | A new labeling tool | Reuse SEED_BUG + mutation builds + a dead-port fault (clone test_healing_mutations.py) | Known-class failures already exist as Docker build-args; keyless + deterministic |

**Key insight:** Every hard part of Phase 9 already has a shipped precedent in this repo — the pure decision module (kg/risk.py, healing/confidence.py, worker/classifier.py), the keyless calibration harness (test_healing_mutations.py), the auth-gated apply/reject router (heals.py), the gated-dep checkpoint (aio-pika/recharts), and the never-log-the-secret pattern (ci_token). Phase 9 composes them; it does not invent.

## Runtime State Inventory

> Phase 9 is greenfield code + a migration, not a rename/refactor. The relevant "state" question is what runtime/stored signals the classifier needs that do NOT exist yet.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data (error text) | **`TestResult` has NO error-text column.** `_run_spec_once` returns `output` (tail-capped 8000-char combined stdout/stderr) but `job.py` stores only `exit_codes` and DISCARDS `output`. The classifier's error-type taxonomy needs this text. | **Migration 0009 adds an error-text column** (to `test_results` or to `classifications.evidence` JSON) AND `job.py` must persist the last-attempt `output`. This is a code edit (worker) + a schema add — both must be in the plan. |
| Stored data (evidence joins) | `heal_audit` (DOM before/after chains, heal outcome, live_match_count) and `test_artifacts` (screenshot/trace/video paths) exist and thread by run_id+flow_id — the classifier joins on these. | None — read-only joins; available today. |
| Live service config | No Jira instance in dev (STATE.md). The fp-<hash> labels live ON Jira issues once filed; dedup reads them via JQL. | Live JQL dedup is Manual-Only; the FakeJira double makes the dedup LOGIC keyless-testable. |
| Secrets/env vars | NEW: `jira_url`, `jira_email`, `jira_api_token`, `jira_project_key`, `jira_autonomous_enabled`, `jira_confidence_threshold`, `jira_max_tickets_per_run`. Token never logged. | Add to `Settings` (config.py) with the optional-default + never-log pattern (mirror ci_token / anthropic_api_key). Compose must enumerate each explicitly (the heal_high_threshold note). |
| Build artifacts | Migration 0009 chains `down_revision='0008'`; lives in `apps/api/alembic/versions/` (NOT app/alembic). The seeded-bug (8081) + mutation (8082–8087) Docker builds exist; the infra-fault needs a dead-port target. | New migration file; reuse existing builds; add a dead-port/forced-timeout infra-fault generator for the Infrastructure label. |

**Nothing found in OS-registered state:** None — verified; Phase 9 adds no OS-level registrations (no new scheduled tasks/services).

## Common Pitfalls

### Pitfall 1: The error text the classifier needs is not persisted today
**What goes wrong:** Planning the classifier as if `TestResult` carries the failure message — it does not (only `verdict`, `attempts`, `exit_codes`, `duration_ms`). `_run_spec_once`'s `output` is computed then dropped by `job.py`.
**Why it happens:** Phase 7 only needed exit codes for the binary flaky/product split; the error text was never required until now.
**How to avoid:** Migration 0009 adds an error-text column; `job.py` persists the last-attempt `output` (already in hand at line ~165). Without this, the classifier has nothing but exit codes to classify by — taxonomy collapses.
**Warning signs:** A classifier reading `TestResult.error` / `.output` — those attributes don't exist.

### Pitfall 2: Cloud v3 description must be an ADF doc dict, not a string
**What goes wrong:** Passing `description="..."` to `create_issue` on Cloud v3 errors (the library types description as a string in some paths; Cloud v3 wants the ADF doc). Reported friction in the ecosystem.
**Why it happens:** v2 took plain text/wiki markup; v3 mandates ADF for description/comments.
**How to avoid:** Construct `Jira(..., cloud=True, api_version="3")` and pass `description=<adf_doc_dict>` built by a pure `adf.py` (doc → paragraphs for summary/steps/expected/actual/severity). If a library path rejects the dict, fall back to httpx against `/rest/api/3/issue` (httpx is already a dep). VERIFY against the live instance in the Manual-Only step.
**Warning signs:** `description must be a string` errors at create time.

### Pitfall 3: Calling the sync Jira client directly from an async FastAPI handler blocks the loop
**What goes wrong:** atlassian-python-api is sync/requests; a direct call inside an async route blocks the event loop for the whole HTTP round-trip.
**How to avoid:** Every gateway method wraps the library call in `anyio.to_thread.run_sync` (D-03). The gateway exposes async methods; the router/pipeline `await` them.
**Warning signs:** Latency spikes / blocked health checks when filing.

### Pitfall 4: The confidence threshold and weights are starting points, not facts
**What goes wrong:** Shipping the classifier weights / `jira_confidence_threshold` as if final — exactly the trap 08-04 hit with the heal bands (0.85/0.60 were UNREACHABLE; the real separation was 0.06 < high <= 0.21, shipped at 0.15).
**How to avoid:** Ship conservative starting points; let the QUAL-03 harness measure the real per-class confidence distribution and calibrate the threshold into the empirical separation window. Store it in `settings` and prove the gate against the SHIPPED default (the `_MUTATION_HIGH = str(_settings.heal_high_threshold)` discipline) so the config can never silently drift from the proof.
**Warning signs:** Accuracy < 85% with "right" weights → the weights/threshold need tuning, not the architecture.

### Pitfall 5: Per-run cap must not silently swallow real defects
**What goes wrong:** The per-run cap (`jira_max_tickets_per_run`) prevents ticket storms but, set too low, drops genuine distinct defects.
**How to avoid:** Cap CREATES only (updates to existing fp-<hash> issues are free); persist the local Defect row regardless of the cap (so capped defects are still in the review queue, just not auto-filed). The cap throttles Jira writes, not classification.
**Warning signs:** Defects classified but no draft row — the cap is dropping data instead of throttling filing.

### Pitfall 6: 3GB WSL cap + neo4j sequencing during the QUAL-03 run phase
**What goes wrong:** Running neo4j + saucedemo variants + Chromium together OOMs under the 3GB cap.
**How to avoid:** neo4j OFF during the run phase (the classifier needs no graph); the labeled-set harness touches Docker target builds + a Chromium subprocess only — same sequencing as test_seeded_bug.py / test_healing_mutations.py. Memory fit is a Manual-Only `docker stats` observation.
**Warning signs:** Subprocess spawn failures / killed targets mid-run.

## Code Examples

### Building the ADF v3 description (pure, unit-testable)
```python
# Source: Jira Cloud REST v3 ADF spec (developer.atlassian.com/cloud/jira/platform/rest/v3)
def _para(text: str) -> dict:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}

def build_adf(*, steps: list[str], expected: str, actual: str, severity: str, prose: str) -> dict:
    content = [_para(prose), _para(f"Severity: {severity}")]
    content.append({"type": "heading", "attrs": {"level": 3},
                    "content": [{"type": "text", "text": "Steps to Reproduce"}]})
    content.append({"type": "orderedList",
                    "content": [{"type": "listItem", "content": [_para(s)]} for s in steps]})
    content.append(_para(f"Expected: {expected}"))
    content.append(_para(f"Actual: {actual}"))
    return {"type": "doc", "version": 1, "content": content}
```

### FakeJira contract double (keyless CI for JIRA-01/03)
```python
# Source: hand-written double behind the JiraGateway Protocol (no recorded-HTTP lib)
class FakeJira:
    def __init__(self): self.issues = {}; self._n = 0; self.attachments = []
    async def search_jql(self, jql: str) -> list[dict]:
        # match labels = "fp-<hash>" AND statusCategory != Done against in-memory issues
        return [i for i in self.issues.values() if _matches(jql, i)]
    async def create_issue(self, fields: dict) -> dict:
        self._n += 1; key = f"FAKE-{self._n}"
        self.issues[key] = {"key": key, **fields, "statusCategory": "To Do"}; return self.issues[key]
    async def add_attachment(self, key: str, path: str) -> None:
        self.attachments.append((key, path))
    async def add_comment(self, key: str, adf: dict) -> None: ...
    async def create_issue_link(self, data: dict) -> None: ...
# Tests assert: a miss creates exactly one issue with the fp-<hash> label + the right attachments;
# a second identical failure HITS the JQL and UPDATES (comment + re-attach), never creates a duplicate;
# the per-run cap blocks the Nth create.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `jira` (pycontribs) for Jira Cloud | atlassian-python-api 4.x | 2025 v2→v3 search/pagination migration | `jira` broke on enhanced search; 4.x is v3-native (`enhanced_jql`, ADF) — CLAUDE.md "What NOT to Use" |
| v2 plain-text description | v3 ADF doc (dict) for description/comments | Jira Cloud v3 | Description must be an ADF doc dict (Pitfall 2) |
| Jira search `startAt`/`maxResults` | `nextPageToken` (enhanced_jql) | Atlassian 2025 forced migration | Dedup pagination uses `nextPageToken`/`isLast`, not `startAt` |

**Deprecated/outdated:**
- The `jira` pycontribs package for Cloud — broken; use atlassian-python-api 4.x.
- LLM-judged classification — rejected here (D-01); deterministic only.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The exact classifier weights (60/20/-15) + the `jira_confidence_threshold` default are starting points | Pattern 1/2 | LOW — tuned by QUAL-03 like the heal bands; the harness is the corrective instrument |
| A2 | The error-type → class taxonomy (browser/network/timeout→Infra; un-healed locator/test-data→Automation; loaded-page assertion/functional/API→Product) is the right cut | Pattern 1 | MEDIUM — QUAL-03 accuracy <85% would force re-cutting the taxonomy; mitigated by labeled set spanning all 3 classes |
| A3 | `description` accepts an ADF dict on `Jira(cloud=True, api_version="3")` via `create_issue` | Pattern 4 / Pitfall 2 | MEDIUM — if the library path rejects it, fall back to httpx `/rest/api/3/issue` (already a dep). Verify in the Manual-Only live step |
| A4 | `anyio` is already in the dependency tree (FastAPI/Starlette transitive) | Standard Stack | LOW — verify with `import anyio`; if absent, it is not a new logical dep |
| A5 | Migration 0009 should add the error-text column (vs storing only in classifications.evidence JSON) | Runtime State / Pitfall 1 | LOW — either works; the column on test_results is the cleaner join, but planner may choose evidence JSON |
| A6 | An Infrastructure-class failure can be generated keylessly via a dead port / forced timeout | Pattern 3 | LOW — `_port_open` inverse + a short timeout is deterministic; no real outage needed |
| A7 | `enhanced_jql` returns `{"issues", "isLast", "nextPageToken"}` and supports the `labels = ... AND statusCategory != Done` query | Pattern 4 | MEDIUM — verified method name + pagination keys from docs; the exact response keys verify against the live instance (Manual-Only) |

## Open Questions

1. **error-text column vs classifications.evidence JSON?**
   - What we know: the error text must be persisted (Pitfall 1); both a `test_results.error_text` column and a `classifications.evidence` JSON blob can carry it.
   - What's unclear: which the planner prefers.
   - Recommendation: add `test_results.error_text` (cleaner join, the classifier reads it directly) AND `classifications.evidence` JSON for the full cited-evidence snapshot the UI renders. Both in migration 0009.

2. **infra-health evidence source granularity (Pattern 5 / priority 8)**
   - What we know: D-02 wants infra health as a cited signal; options are (a) a container/healthcheck state probe (Docker/compose health) or (b) an error-pattern signal derived from the error text (connection-refused/DNS/timeout patterns).
   - What's unclear: whether a live Docker-health probe is worth the coupling for a single-user MVP.
   - Recommendation: start with (b) the error-pattern signal (pure, keyless, in the classifier) and treat a live container-health probe as a Phase-11 enrichment. The dead-port QUAL-03 case proves (b) deterministically.

3. **severity → priority mapping**
   - What we know: JIRA-01 wants severity + priority; the classifier yields class + confidence.
   - Recommendation: a small pure map (e.g. Product Defect + high confidence → High; Automation → Medium; configurable). Not load-bearing; planner's discretion.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| atlassian-python-api | JIRA-01/03/04 live | ✗ (must install, gated) | 4.0.7 on PyPI | FakeJira double for all CI logic; live filing Manual-Only |
| anyio | sync→async Jira offload | ✓ (FastAPI transitive — verify) | (transitive) | none needed |
| Jira Cloud instance + API token | live filing/dedup | ✗ (none in dev, STATE.md) | — | FakeJira contract test; live = Manual-Only |
| Provider keys (Anthropic/OpenAI) | LLM description enrichment | ✗ (empty, STATE.md) | — | deterministic no-key fallback (gateway) → keyless |
| Docker (saucedemo-bug 8081, mutation 8082–8087) | QUAL-03 labeled set | ✓ (Phase 6/8 builds) | — | harness SKIPS cleanly when down (`_port_open`) |
| Dead-port / forced-timeout target | QUAL-03 Infrastructure label | ✗ (new, trivial) | — | a non-listening port + a sub-second timeout — no build needed |
| neo4j | NOT needed in run phase | (off) | — | classifier needs no graph; OFF during runs (3GB cap) |
| PostgreSQL | classifications/defects | ✓ | — | — |

**Missing dependencies with no fallback:** none block CI — every keyless path has a double or a build.
**Missing dependencies with fallback:** atlassian-python-api (FakeJira), Jira instance (FakeJira + Manual-Only), provider keys (no-key fallback).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x (pytest-asyncio 1.4, asyncio_mode=auto) + pytest-playwright + pytest-bdd |
| Config file | apps/api/pyproject.toml (`[tool.pytest.ini_options]`) |
| Quick run command | `cd apps/api && uv run pytest -m "not live_llm and not graph and not e2e" -q` (the PURE classifier: taxonomy rules + frozen-weights 0-100 confidence; fingerprint normalize+hash; the autonomy gate logic; the ADF builder; the FakeJira contract [create/attach/JQL-dedup/update/cap/link]; the no-LLM grep gate — all on fixture dicts, NO keys, NO neo4j, NO browser, NO real Jira) |
| Full suite command | `cd apps/api && uv run pytest -m "not live_llm" -q` (adds functional: the QUAL-03 labeled-set accuracy harness against the SEED_BUG + BREAK_REMOVE + dead-port builds, keyless; the migration 0009 up/down; the defects router integration with FakeJira) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEF-01 | 3-way class + 0-100 confidence | unit (fixtures) | `pytest tests/unit/test_classifier.py -q` | ❌ Wave 0 |
| DEF-02 | classify after retry; cites error/DOM-diff/heal-history/infra-health | unit + integration | `pytest tests/unit/test_classifier_evidence.py tests/integration/test_defect_pipeline.py -q` | ❌ Wave 0 |
| DEF-03 / QUAL-03 | accuracy ≥85% on labeled set; threshold calibrated | functional (keyless) | `pytest tests/functional/test_classifier_accuracy.py -m functional -q` | ❌ Wave 0 |
| JIRA-01 | create issue w/ ADF description + attachments | unit (FakeJira) | `pytest tests/unit/test_jira_create.py tests/unit/test_adf.py -q` | ❌ Wave 0 |
| JIRA-02 | draft queue + autonomy gate (OFF default) | integration | `pytest tests/integration/test_defects_router.py tests/unit/test_autonomy_gate.py -q` | ❌ Wave 0 |
| JIRA-03 | fingerprint + JQL dedup (update-not-dup) + per-run cap | unit (FakeJira) | `pytest tests/unit/test_fingerprint.py tests/unit/test_jira_dedup.py -q` | ❌ Wave 0 |
| JIRA-04 | defect linked to test/flow/execution (FK) + issue link | integration | `pytest tests/integration/test_defect_pipeline.py -q` | ❌ Wave 0 |
| (gate) | no LLM in the classifier path | unit (grep) | `pytest tests/unit/test_no_llm_in_classifier.py -q` | ❌ Wave 0 |
| (schema) | migration 0009 up/down/up | migration | `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd apps/api && uv run pytest -m "not live_llm and not graph and not e2e" -q`
- **Per wave merge:** full suite (`-m "not live_llm"`) with the SEED_BUG/mutation builds up + a dead-port fault; neo4j OFF in the run phase (3GB cap), same sequencing as Phase 7/8.
- **Phase gate:** full deterministic suite green; the QUAL-03 harness green (accuracy ≥85%, threshold calibrated + asserted against the shipped `settings.jira_confidence_threshold`); the no-LLM grep gate green; migration 0009 reversible. Live LLM description enrichment + live Jira filing/dedup demonstrated Manual-Only.

### Wave 0 Gaps
- [ ] `tests/unit/test_classifier.py` + fixtures — DEF-01 taxonomy + confidence on evidence dicts
- [ ] `tests/unit/test_fingerprint.py` — DEF-05 normalize+hash determinism
- [ ] `tests/unit/test_jira_create.py` / `test_jira_dedup.py` + `services/jira/fake.py` (FakeJira) — JIRA-01/03 keyless contract
- [ ] `tests/unit/test_adf.py` — the ADF builder
- [ ] `tests/unit/test_no_llm_in_classifier.py` — the SC3-style grep gate (clone test_no_llm_in_worker.py)
- [ ] `tests/functional/test_classifier_accuracy.py` — QUAL-03 harness (clone test_healing_mutations.py); a dead-port infra-fault helper
- [ ] `tests/integration/test_defects_router.py` + `test_defect_pipeline.py` — router + pipeline with FakeJira
- [ ] migration 0009 (classifications + defects + test_results.error_text) + the `job.py` error-text persistence edit
- [ ] `Settings` fields: jira_url/email/api_token/project_key/autonomous_enabled/confidence_threshold/max_tickets_per_run

## Security Domain

> `security_enforcement` not set false → included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | The Jira API token (Settings, never logged — mirror ci_token); the /api/defects router auth-gated via `get_current_user` |
| V3 Session Management | yes | Reuse the JWT/httpOnly cookie auth on the router (heals.py precedent) |
| V4 Access Control | yes | Router-level `Depends(get_current_user)` on EVERY endpoint, especially state-changing apply/reject/autofile (state-changing endpoints never public) |
| V5 Input Validation | yes | ORM-parameterized queries (no string SQL); the fingerprint label is server-built; artifact paths are run_id-derived, NEVER request paths (heals.py carry-forward); JQL built from the server-side fingerprint, not user input |
| V6 Cryptography | no (hashlib.sha1 for fingerprint is a non-security identity hash, not a secret) | none — the fingerprint hash is an identity key, not a credential; do not treat as crypto |
| V7 Errors/Logging | yes | The Jira token + provider keys NEVER enter logs/ledger (the SENSITIVE regex matches "token"/"password"); structlog events omit auth |

### Known Threat Patterns for {Python FastAPI + sync Jira client + Postgres}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Jira token leak in logs/error responses | Information Disclosure | Optional-default + never-log (mirror ci_token / anthropic_api_key); structlog redaction |
| JQL injection via attacker-influenced fingerprint | Tampering | The fingerprint is a server-computed sha1 hex (`fp-<hash>`), never user text — no injectable surface; the JQL is a fixed template |
| Path traversal in attachment upload | Tampering | Artifact paths are run_id-derived via `workspaces.run_dir` (heals.py rule), never a request-body path |
| Unauthenticated defect filing/apply | Elevation of Privilege | Router-level auth gate; autonomous filing additionally gated by the OFF-by-default flag + calibrated threshold |
| Blocking the event loop (DoS) with the sync client | Denial of Service | `anyio.to_thread.run_sync` offload |
| SQL injection in defect queries | Tampering | SQLAlchemy ORM-parameterized (execution_history/heal_audit precedent) |

## Sources

### Primary (HIGH confidence)
- Shipped repo code (read this session): `apps/api/app/models/execution_history.py`, `app/models/heal_audit.py`, `app/services/worker/classifier.py`, `app/services/worker/job.py`, `app/services/stability.py` (`_run_spec_once` → `{passed, exit_code, output}`), `app/services/kg/risk.py`, `app/services/healing/confidence.py`, `app/routers/heals.py`, `app/core/config.py`, `app/services/llm_gateway.py` (`complete(operation_type, run_id)`), `app/schemas/heal.py` — the patterns Phase 9 clones. HIGH.
- `apps/api/tests/functional/test_seeded_bug.py`, `test_healing_mutations.py`, `infra/targets/saucedemo/Dockerfile` (SEED_BUG=1, BENIGN_*/BREAK_* build-args, ports 8081–8087) — the QUAL-03 labeled-set generators. HIGH.
- `.planning/phases/08-self-healing-engine/08-VALIDATION.md` — the keyless/Manual-Only split + calibration-by-harness template. HIGH.
- `pip index versions atlassian-python-api` (run 2026-06-27) → 4.0.7 latest. HIGH.
- CLAUDE.md (stack lock: atlassian-python-api 4.x, sync→anyio.to_thread, init_chat_model gateway, "What NOT to Use" = jira pycontribs). HIGH.

### Secondary (MEDIUM confidence)
- atlassian-python-api 4.x docs (readthedocs `jira.html`): `create_issue(fields=...)`, `add_attachment(issue_key, filename)`, `issue_transition`, `set_issue_status`, `enhanced_jql(... nextPageToken ...)` → `{issues, isLast, nextPageToken}`, `create_issue_link(data)`. MEDIUM (method names verified; exact response keys verify against a live instance).
- Jira Cloud REST API v3 + community: description/comments take ADF on v3; ADF doc shape `{type:"doc", version:1, content:[...]}`; known library friction passing a dict description (Pitfall 2). MEDIUM.

### Tertiary (LOW confidence)
- The exact classifier weights + the calibrated `jira_confidence_threshold` — starting points only, to be tuned by the QUAL-03 harness (the kg/risk.py / heal-band precedent). LOW on values, HIGH on shape.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — atlassian-python-api 4.0.7 verified on PyPI; matches CLAUDE.md lock; one gated dep, rest in tree.
- Architecture/patterns/data model: HIGH — every pattern (pure decision module, keyless harness, auth-gated apply/reject router, gated dep, never-log-secret) is a shipped Phase 6/7/8 precedent.
- Classifier taxonomy: MEDIUM — the 3-way cut is sound but unproven until the QUAL-03 harness measures ≥85% accuracy; mitigated by the labeled set spanning all classes.
- Classifier weights + confidence threshold: LOW on values, HIGH on shape — explicitly starting points tuned by the harness (the heal-band 0.85→0.15 precedent).
- atlassian-python-api ADF call shape: MEDIUM — method names verified; the ADF-dict-on-Cloud-v3 detail and `enhanced_jql` response keys verify against a live instance in the Manual-Only step.

**Research date:** 2026-06-27
**Valid until:** ~2026-07-27 (atlassian-python-api 4.x is stable; the repo patterns are internal and stable). Re-verify the ADF call shape if atlassian-python-api bumps a major.
