# Phase 8: Self-Healing Engine - Research

**Researched:** 2026-06-22
**Domain:** Deterministic, inline (Phase-7 worker) self-healing locator engine
**Confidence:** HIGH on architecture/seams/hook-point; MEDIUM on exact blend weights + band thresholds (tuned by the mutation harness, by design)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Healing runs INLINE in the Phase-7 worker. On a locator failure mid-run, attempt a deterministic heal + re-validate against the LIVE page BEFORE the attempt is finally scored. High-confidence → auto-heal lets the test proceed; medium → quarantine; low → fail-as-potential-defect. Reconcile with the Phase-7 2x retry loop + flaky classifier (a heal is NOT a flake).
- **D-02:** Engine is PURELY DETERMINISTIC — NO LLM. Blend DOM similarity + visual similarity + a11y-attribute match + historical-locator mapping (from Element Repository `history_json`), each candidate re-validated to a UNIQUE live hit; result is confidence in [0,1]. Keyless, auditable, reproducible. Visual similarity must be a cheap deterministic measure (bounding-box / screenshot-region compare), NOT an LLM vision call.
- **D-03:** "heal-as-commit" = NOT git. A heal (a) rewrites the generated page-object locator by element key, (b) writes a Postgres heal-audit row, (c) appends to KG Element history via kg/writer SINGLE writer (managed execute_write + read-back + parameterized Cypher). Before/after diff rendered from the audit record. No git plumbing in ephemeral workspaces.
- **D-04:** CONSERVATIVE banding + hard LIVE RE-VALIDATION gate. Auto-heal ONLY when confidence ≥ HIGH AND candidate re-validates to EXACTLY ONE live element; medium → quarantine; low → fail-as-defect. Thresholds CONFIG-tunable (like Phase-7 stability_runs). Assertions NEVER weakened — only locators are healed.
- **D-05:** NO heal UI. Minimal auth-gated quarantine API only (list / apply / reject, returning before/after diff + confidence from the heal-audit record). Review SCREEN + heal visualizations DEFERRED to Phase 10.

### Claude's Discretion (research these)
- The four similarity strategies' concrete metrics + blended-confidence formula + weights + the live re-validation uniqueness check.
- The benign-vs-breaking MUTATION CATALOG (QUAL-02).
- The heal-audit data model + migration 0008; per-element heal-success/false-heal aggregation (HEAL-04).
- The inline worker hook: where a locator failure is intercepted, how heal re-uses the live page, outcome → TestResult verdict + retry/flaky reconciliation.

### Deferred Ideas (OUT OF SCOPE)
- Failure CLASSIFICATION + Jira filing → Phase 9 (fail-as-defect FEEDS Phase 9).
- Rich heal dashboards + trends → Phase 10.
- LLM-assisted heal ranking → REJECTED.
- Literal git-versioned workspaces → REJECTED for v1.
- K8s/Prometheus heal metrics → Phase 11.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HEAL-01 | On locator failure, find alternatives via DOM similarity, visual similarity, a11y attributes, historical locator mapping, using the priority chain (data-testid → aria-label → role → text → xpath) | The 4 deterministic similarity strategies (Pattern 2) reuse `build_locator_chain` ordering + `element_repository`/`element_detail` history + Playwright live-page reads (`bounding_box`, `get_attribute`, `count`). |
| HEAL-02 | Three outcomes — auto-heal (high), quarantine (medium), fail-as-defect (low); assertions never weakened | Confidence-band resolver (Pattern 3) mirrors `kg/risk.py` `risk_tier`; hook intercepts ONLY locator resolution, never `expect(...)` assertions (Pattern 1, the in-spec interception layer). |
| HEAL-03 | Auditable before/after diff + confidence; updates script repo; writes back to KG | File-journal handoff (Pattern 4): in-spec layer writes a heal-journal; worker ingests → Postgres `heal_audit` row (migration 0008) + page-object rewrite by element key + KG Element-history append via a NEW single-writer fn in `kg/writer.py`. |
| HEAL-04 | Healing success rate + false-heal rate tracked per element, reported on dashboards | Per-element aggregation queries over `heal_audit` (Pattern 5) mirror Phase-7 execution-history queries; exposed via the minimal quarantine/stats API. Dashboard rendering is Phase 10. |
| QUAL-02 | Seeded-bug / benign-mutation harness measures heal success (>90%) + false-heal rate, proves tests fail on real bugs | Benign-vs-breaking mutation catalog (Pattern 6) extends `infra/targets/saucedemo/Dockerfile` SEED_BUG build-args + the `test_stability.py`/`test_seeded_bug.py` planted-spec harness, keyless. |
</phase_requirements>

## Summary

Phase 8 adds a deterministic, keyless self-healing locator engine that runs INLINE during a Phase-7 regression run. The single hardest design question — "where does the heal hook, given the generated spec runs in an isolated `uv run pytest` subprocess?" — resolves cleanly: **the worker (`worker/job.py`) only sees subprocess exit codes and has NO live page handle, so healing CANNOT live in the worker.** It must live INSIDE the generated project, where the spec's own Playwright page/context is live. Concretely: a small generated `_healing.py` module + a page-object locator accessor (or a `conftest` hook) wraps locator resolution; on a `TimeoutError`/zero-match it runs the deterministic candidate search against the live page, re-validates to a unique match, and either continues (auto-heal) or records a quarantine/fail decision. Because the subprocess has no DB/Neo4j access (the generated project imports only `pages/`, `playwright`, `pytest_bdd`), heal events are written to a **heal-journal JSON file** under `workspaces/<run_id>/`; after the subprocess exits, the worker INGESTS the journal and performs the three persistence side-effects (Postgres audit row, page-object rewrite, KG history write-back) — exactly mirroring how `worker/job.py` already walks the output dir for artifacts after the run.

The deterministic engine is a faithful sibling of `kg/risk.py`: a `@dataclass(frozen=True)` of tunable weights + a pure `confidence(signals)` function that blends four [0,1] sub-scores — DOM-structure similarity (tag + attribute-set Jaccard + xpath ancestry overlap), VISUAL similarity (bounding-box IoU + size/position proximity, computed from `locator.bounding_box()` — geometry only, ZERO new packages, no pixel decode), a11y match (role + accessible-name equality/normalized-ratio), and historical-locator mapping (does a candidate's chain match a prior `history_json` snapshot). The hard live-re-validation uniqueness gate (`page.locator(candidate).count() == 1`) is the structural guarantee that pins false-heal near zero — a candidate that resolves to 0 or >1 live elements can NEVER auto-heal regardless of score. Conservative HIGH/MED bands (config-tunable, like `stability_runs`) are derived empirically from the mutation harness.

The trust gate (QUAL-02) extends the existing SEED_BUG Dockerfile pattern: add BENIGN mutation build-args (rename `data-test`, change visible text, reorder siblings, change tag) that MUST heal (>90%) alongside the existing/extended BREAKING mutations (remove element, break flow) that MUST still fail (~0 false-heal) — all proven keylessly on planted specs, no provider keys.

**Primary recommendation:** Build a new `app/services/healing/` package (pure `confidence.py` + `candidates.py` mirroring `kg/risk.py`/`explorer/locators.py` discipline), GENERATE an in-spec `_healing.py` + heal-journal writer into the project tree (`codegen/project.py` + a new template), INGEST the journal in `worker/job.py` after the subprocess exits, persist via a new `heal_audit` model (migration 0008) + a new single-writer KG fn, and prove it with a benign-vs-breaking mutation harness extending the SEED_BUG build. **ZERO new packages** — Playwright geometry + stdlib `difflib`/`hashlib` cover everything.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Locator-failure interception | Generated test project (in-subprocess) | — | The live Playwright page handle exists ONLY inside the spec subprocess; the worker sees only exit codes. Interception MUST be in-spec. |
| Deterministic candidate scoring | API service (`app/services/healing/`, pure) | Generated project (imports the pure scorer copied/vendored in) | Pure stdlib logic; table-testable like `kg/risk.py`. The in-spec layer needs the same scoring — vendor the pure module into the generated tree or keep it importable. |
| Live re-validation (uniqueness gate) | Generated test project (in-subprocess) | — | Needs the live `page.locator(...).count()` — only available in the subprocess. |
| Heal-journal write | Generated test project (in-subprocess, file I/O) | — | No DB/Neo4j in the subprocess; write a JSON journal under `workspaces/<run_id>/`. |
| Postgres heal-audit row | Worker (`worker/job.py`, post-subprocess) | — | Worker has `SessionLocal`; ingests the journal after the run (mirrors artifact discovery). |
| Page-object locator rewrite | Worker (post-subprocess, file I/O) | — | Safe, key-targeted rewrite of `pages/*.py` under the workspace; worker owns the filesystem handoff. |
| KG Element-history write-back | Worker (`kg/writer.py` single writer) | — | The single-write-path invariant: only `kg/writer.py` may MERGE/SET on the graph. |
| Per-element heal stats (HEAL-04) | API service (read queries over `heal_audit`) | — | Mirrors Phase-7 execution-history aggregation; exposed via the API. |
| Quarantine API (list/apply/reject) | API router (auth-gated) | — | Reuses the `get_current_user` auth-gate pattern from `executions.py`. |
| Benign-vs-breaking mutation harness | Infra (Dockerfile build-args) + test harness | — | Extends SEED_BUG; deterministic + keyless like `test_seeded_bug.py`. |

## Standard Stack

### Core (all already in the project — ZERO new packages)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| playwright (Python) | 1.60.x [CITED: CLAUDE.md] | Live-page candidate search + re-validation: `page.locator()`, `.count()`, `.bounding_box()`, `.get_attribute()`, `.inner_text()`, `.evaluate()` (sync API inside the generated spec) | Already the decided automation tool; `bounding_box()` returns `{x,y,width,height}` for a deterministic geometric visual measure — no pixel decode, no image lib [CITED: playwright.dev/python/docs/api/class-locator] |
| SQLAlchemy (async) | 2.0.x [CITED: CLAUDE.md] | `heal_audit` model (mirrors `execution_history.py`) | The locked ORM; `Mapped[...] = mapped_column(...)` style already used by `TestResult`/`TestArtifact` |
| Alembic | 1.18.x [CITED: CLAUDE.md] | Migration 0008 (chains after 0007) | The locked migration tool; 0007 is the template to copy |
| neo4j (async driver) | 6.2.x [CITED: CLAUDE.md] | KG Element-history write-back via a new `kg/writer.py` single-writer fn | Locked; the single-write-path invariant requires the new write to go through `kg/writer.py` |
| structlog | 26.x [CITED: CLAUDE.md] | Heal event logging (worker + ingest) | Project standard |
| FastAPI deps | — | Auth-gated quarantine router (`get_current_user`) | `executions.py` already demonstrates the cookie/CI-token auth gate |

### Supporting (stdlib only)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `difflib` (stdlib) | 3.13 | `SequenceMatcher.ratio()` for accessible-name / visible-text normalized similarity sub-score | When comparing two strings for a [0,1] similarity (a11y name match, text match) |
| `hashlib` (stdlib) | 3.13 | Optional: stable hash of an element-region screenshot IF a pixel-level tiebreak is ever needed (NOT recommended for v1 — geometry suffices) | Only if bounding-box IoU proves insufficient during tuning |
| `json` (stdlib) | 3.13 | heal-journal serialize/deserialize; chain_json/history_json (already used by `kg/reader._loads`) | The file-handoff journal + KG payloads |
| `dataclasses` (stdlib) | 3.13 | `@dataclass(frozen=True)` tunable weights (mirror `RiskWeights`) | The blend-weight config object |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Bounding-box IoU (geometry) for visual similarity | Pillow / `pixelmatch-py` / OpenCV pixel diff | Adds a NEW package (planner must gate). Pixel diff is heavier, needs PNG decode, and is sensitive to anti-aliasing/font rendering — non-deterministic across environments. Geometry (IoU + size proximity) is fully deterministic, keyless, zero-dep, and sufficient for "is this the same visual region." STRONGLY prefer geometry. [ASSUMED — confirm during harness tuning that IoU discriminates benign vs breaking adequately] |
| In-spec interception layer (generated `_healing.py`) | Worker-side heal around the subprocess | REJECTED by the architecture: the worker has NO live page handle (subprocess isolation, `worker/job.py` only reads exit codes). Heal MUST be in-spec. |
| File-journal handoff for persistence | Direct DB/Neo4j write from inside the spec | REJECTED: the generated project is a standalone pytest project with no DB/driver imports (verified — `codegen/project.py` renders only `pages/`, `steps/`, `conftest.py`). Giving it DB creds violates isolation and the single-write-path gate. |
| pytest plugin hook (`pytest_runtest_makereport`) | Page-object accessor wrapper | Both viable; the page-object accessor (a `heal_locator(self, attr)` helper, or wrapping `page.locator`) is more surgical — it intercepts at the exact resolution point and keeps the live `page` in scope. A conftest/plugin hook fires after the failure when the page may already be torn down. PREFER the page-object/accessor wrapper; a `conftest` autouse fixture can inject the heal context. |

**Installation:** None. All dependencies are already pinned in the project.

**Version verification:** No new packages to verify. Playwright `bounding_box()` / `locator.count()` / `locator.screenshot(clip=...)` confirmed current in the 1.60 API surface [CITED: playwright.dev/python/docs/api/class-locator, accessed 2026-06-22].

## Package Legitimacy Audit

> No external packages are installed by this phase. ZERO new packages (the project's stated preference). Every dependency used (playwright, SQLAlchemy, Alembic, neo4j, structlog, FastAPI) is already pinned in CLAUDE.md and verified in prior phases. All similarity math is stdlib (`difflib`, `hashlib`, `json`, `dataclasses`).

| Package | Registry | Disposition |
|---------|----------|-------------|
| (none) | — | No installs — slopcheck N/A |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

**Planner note:** If tuning later shows geometry-only visual similarity is insufficient and a pixel-diff lib is proposed (Pillow, pixelmatch-py, opencv-python), that is a NEW package and MUST be gated behind a `checkpoint:human-verify` task + the Package Legitimacy Gate. v1 should ship geometry-only.

## Architecture Patterns

### System Architecture Diagram

```
  REGRESSION RUN (Phase 7 worker plane)
  ┌─────────────────────────────────────────────────────────────────────┐
  │ worker/consumer.py  ──dequeues {run_id, flow_id}──►  worker/job.py    │
  │                                                                       │
  │  run_flow_job():                                                      │
  │    ├─ 2x retry loop ─► stability._run_spec_once()                     │
  │    │      │  (uv run pytest <spec> --screenshot/--tracing ...)        │
  │    │      ▼                                                           │
  │    │   ┌──────────── ISOLATED SUBPROCESS (sync Playwright) ────────┐  │
  │    │   │ generated project  workspaces/<run_id>/target/            │  │
  │    │   │   steps/test_*.py ─► pages/*.py (PageObject)              │  │
  │    │   │       │ self.button_add_to_cart  ── resolve locator       │  │
  │    │   │       ▼  ON FAILURE (TimeoutError / 0 matches)            │  │
  │    │   │   _healing.heal(page, element_key, broken_chain):         │  │
  │    │   │     1. read live DOM candidates (role/attrs/bbox/text)    │  │
  │    │   │     2. score each: DOM⊕VISUAL⊕A11Y⊕HISTORY → conf[0,1]    │  │
  │    │   │     3. LIVE RE-VALIDATE: locator(cand).count()==1 ? gate  │  │
  │    │   │     4. band: HIGH+unique→auto-heal(continue)              │  │
  │    │   │              MED→quarantine(record, FAIL test)            │  │
  │    │   │              LOW→fail-as-defect(record, FAIL test)        │  │
  │    │   │     5. append event ─► heal-journal.json (file I/O only)  │  │
  │    │   │   NEVER touches expect(...) assertions                    │  │
  │    │   └────────────────────────────────────────────────────────┘  │
  │    │                                                                 │
  │    ▼ subprocess exits (exit code)                                    │
  │    classify_retry(exit_codes) ─► verdict  (reconciled w/ heal, below)│
  │    _discover_artifacts(out_dir)                                      │
  │    INGEST heal-journal.json  ◄── NEW (mirrors artifact discovery)    │
  │       ├─ Postgres: heal_audit rows (before/after/conf/outcome)       │
  │       ├─ page-object rewrite: pages/*.py locator by element key      │
  │       └─ KG: kg/writer append Element history (single writer)        │
  │    record TestResult(verdict incl. auto_healed/quarantined)          │
  └─────────────────────────────────────────────────────────────────────┘

  REVIEW (API plane)
   GET  /heals?status=quarantined  ─► heal_audit rows (before/after/conf)
   POST /heals/{id}/apply          ─► mark applied (rewrite already staged)
   POST /heals/{id}/reject         ─► mark rejected (revert staged rewrite)
   GET  /heals/stats?element=...   ─► per-element success/false-heal (HEAL-04)
```

### Recommended Project Structure
```
apps/api/app/
├── services/
│   ├── healing/
│   │   ├── __init__.py
│   │   ├── confidence.py     # PURE: HealWeights(frozen) + confidence(signals)->float; bands (mirror kg/risk.py)
│   │   ├── candidates.py     # PURE: score a candidate dict vs the broken chain (DOM/a11y/history sub-scores on fixture dicts)
│   │   ├── geometry.py       # PURE: bounding-box IoU + size/position proximity (visual sub-score, no Playwright import)
│   │   └── ingest.py         # worker-side: parse heal-journal, write audit rows, rewrite page-object, KG write-back
│   └── codegen/
│       └── project.py        # EXTEND: render _healing.py + wire the page-object accessor
├── templates/
│   └── healing/
│       └── _healing.py.j2    # NEW: the in-spec interception layer (live search + re-validate + journal write); vendors the pure scorer
├── models/
│   └── heal_audit.py         # NEW: HealAudit model (mirrors execution_history.py)
├── routers/
│   └── heals.py              # NEW: auth-gated quarantine API (list/apply/reject/stats)
└── core/config.py            # EXTEND: heal_high_threshold, heal_med_threshold, heal_enabled (like stability_runs)

apps/api/alembic/versions/
└── 0008_heal_audit.py        # NEW: chains after 0007

apps/api/app/services/kg/writer.py   # EXTEND: append_element_history() single-writer fn
infra/targets/saucedemo/Dockerfile   # EXTEND: BENIGN_MUT + more BREAKING build-args (mutation catalog)
infra/docker-compose*.yml            # EXTEND: saucedemo-benign / saucedemo-break profile services
apps/api/tests/functional/test_healing_mutations.py   # NEW: the >90%/~0 mutation proof (keyless)
apps/api/tests/unit/test_heal_confidence.py           # NEW: table tests on the pure scorer
```

### Pattern 1: In-spec interception via a page-object heal accessor (THE CRUX)
**What:** Healing intercepts at the locator-resolution point INSIDE the generated spec subprocess, where the live `page` is in scope. The page object exposes a heal-aware resolver.
**When to use:** Every interaction/visibility check that resolves a repo-sourced locator.
**Why in-spec (not worker):** `worker/job.py` runs `uv run pytest <spec>` as an isolated subprocess (`stability._run_spec_once`) and only observes the exit code + walks the output dir for artifact files. It has NO Playwright page handle. The live DOM only exists inside the subprocess. (Verified: `execution.py`/`job.py` read only exit codes; the generated project imports only `pages`, `playwright`, `pytest_bdd` — no DB/driver.)
```python
# Source: generated into pages/*.py + _healing.py (NEW template); pattern derived from
# page_object.py.j2 + explorer/locators.py + playwright.dev/python/docs/api/class-locator
# (PSEUDO — the locator chain + element_key are repo-sourced template inputs)
from _healing import heal  # vendored pure scorer + live search + journal

class InventoryPage:
    def __init__(self, page):
        self.page = page
        # element_key + ordered chain come from the Element Repository at codegen time
        self._chains = {"button_add_to_cart": [{"strategy":"data-testid","value":"add-to-cart"}, ...]}

    def add_to_cart(self):
        loc = self._resolve("button_add_to_cart")   # heal-aware
        loc.click()

    def _resolve(self, element_key):
        chain = self._chains[element_key]
        loc = self.page.locator(_to_selector(chain[0]))
        try:
            loc.wait_for(state="attached", timeout=HEAL_TIMEOUT_MS)
            return loc
        except Exception:
            # locator FAILED — attempt a deterministic heal against the LIVE page.
            return heal(self.page, element_key=element_key, broken_chain=chain)
            #  heal() either returns a healed Locator (auto-heal) OR raises HealFailed
            #  (quarantine/fail) AFTER appending to the heal-journal. The test then fails
            #  naturally on the raise — assertions are NEVER weakened.
```
**Reconciliation with the Phase-7 retry loop (D-01):** A heal happens WITHIN a single subprocess attempt. The verdict mapping is:
- auto-heal succeeds → the spec proceeds and (if everything else passes) exits 0 → the worker reads exit 0. To distinguish "passed cleanly" from "passed via heal" (a heal is NOT a flake — `classifier.classify_retry` would otherwise mislabel), the worker reads the heal-journal: if the journal has an `auto_heal` event for this flow, the verdict is upgraded to **`auto_healed`** (a new verdict) rather than `passed`/`flaky`. The retry loop still applies for genuine flakes (a heal failing on attempt 1 may still be retried, but a journal'd auto-heal that produced exit 0 is `auto_healed`, never `flaky`).
- quarantine / fail-as-defect → `heal()` raises → the spec exits non-zero → after retries exhaust, the worker reads the journal: a `quarantine` event → verdict **`quarantined`**; a `fail_as_defect` event (or no heal candidate at all) → verdict **`product_failure`** (feeds Phase 9).

### Pattern 2: The four deterministic similarity sub-scores (HEAL-01)
**What:** Each candidate live element gets four [0,1] sub-scores; the blend is a weighted sum (mirrors `risk_score`). Candidates are enumerated from the live page (all elements of the broken element's role, or a bounded DOM region around the last-known xpath ancestry).

| Sub-score | Deterministic metric | Source data | Notes |
|-----------|---------------------|-------------|-------|
| **DOM similarity** | Jaccard of attribute SETS (`{tag, type, name, placeholder, class tokens}`) + tag-equality bonus + xpath-ancestry overlap ratio (shared leading segments / max segments) | live `get_attribute()` + the `_XPATH_JS` from `explorer/locators.py` (REUSE verbatim) + the broken chain's xpath tier | Pure on fixture dicts (no browser) — table-testable like `build_locator_chain` |
| **VISUAL similarity** | Bounding-box **IoU** (intersection-over-union of `{x,y,width,height}`) + size-ratio proximity (`min(a,b)/max(a,b)` of area) | live `locator.bounding_box()` [CITED: playwright.dev/python/docs/api/class-locator] | DETERMINISTIC geometry — NO pixel decode, NO new package. `bounding_box()` returns null for non-visible → sub-score 0 |
| **a11y match** | role equality (1.0/0.0) blended with accessible-name `difflib.SequenceMatcher.ratio()` (normalized, case-folded) | live `get_attribute("role")` + accessible name (`aria-label` else `inner_text`) | Mirrors the role+name tier of `build_locator_chain` |
| **historical mapping** | Does the candidate's freshly-built chain (via `build_locator_chain`) match ANY prior snapshot in the element's `history_json`? Best-matching snapshot's tier weight → [0,1] | `element_detail(key).history` (the append-only `{step, chain}` snapshots) | The element_key is known at codegen time; history is read at codegen and vendored into `_healing.py`, OR (Manual-Only live path) read live by the worker and passed in |
**Priority chain:** Candidate enumeration + tie-breaking follow the SAME healing-priority order as `build_locator_chain` (data-testid → aria-label → role → text → xpath). A candidate matching on a higher tier scores higher, all else equal.
```python
# Source: app/services/healing/confidence.py (NEW) — mirrors app/services/kg/risk.py verbatim discipline
from dataclasses import dataclass

@dataclass(frozen=True)
class HealWeights:
    dom: float = 0.30          # STARTING POINTS — tuned by the mutation harness (LOW confidence on values)
    visual: float = 0.20
    a11y: float = 0.30
    history: float = 0.20

DEFAULT_WEIGHTS = HealWeights()

def confidence(signals: dict, w: HealWeights = DEFAULT_WEIGHTS) -> float:
    """PURE: weighted blend of four [0,1] sub-scores -> clamped [0,1]. No I/O, no LLM, no browser."""
    raw = (w.dom    * float(signals.get("dom", 0.0))
         + w.visual * float(signals.get("visual", 0.0))
         + w.a11y   * float(signals.get("a11y", 0.0))
         + w.history* float(signals.get("history", 0.0)))
    total = (w.dom + w.visual + w.a11y + w.history) or 1.0
    return max(0.0, min(1.0, raw / total))
```

### Pattern 3: Confidence banding + the hard live re-validation gate (HEAL-02 / D-04)
**What:** The [0,1] confidence maps to one of three outcomes — but auto-heal requires BOTH a HIGH band AND a unique live match.
```python
# Source: app/services/healing/confidence.py — mirrors kg/risk.py risk_tier()
def heal_outcome(conf: float, live_match_count: int, *, high: float, med: float) -> str:
    """PURE: the 3-outcome resolver with the hard uniqueness gate (D-04).

    auto_heal ONLY when conf >= high AND the candidate resolves to EXACTLY ONE live element.
    A non-unique match (0 or >1) can NEVER auto-heal regardless of confidence — this is the
    structural guarantee that pins false-heal near zero (QUAL-02).
    """
    if live_match_count != 1:
        return "fail_as_defect"          # ambiguous/missing -> never auto-heal
    if conf >= high:
        return "auto_heal"
    if conf >= med:
        return "quarantine"
    return "fail_as_defect"
```
- `high` / `med` come from `settings.heal_high_threshold` / `settings.heal_med_threshold` (env-tunable, exactly like `stability_runs`). Starting points: `high=0.85`, `med=0.60` [ASSUMED — derived empirically from the mutation harness].
- **Assertions are never a heal target.** The interception layer wraps locator RESOLUTION only; `expect(...).to_be_visible()` / `to_have_url()` in the page object and steps are untouched. A real defect that breaks an assertion (not a locator) surfaces as `product_failure` → Phase 9.

### Pattern 4: heal-as-commit via file-journal handoff (HEAL-03 / D-03)
**What:** Because the subprocess can't reach Postgres/Neo4j, the in-spec layer writes a heal-journal; the worker ingests it post-run.
```python
# In-spec (subprocess): append-only journal under the run workspace (file I/O only).
# Source: pattern mirrors worker/job.py artifact discovery (worker walks out_dir post-run)
# workspaces/<run_id>/<flow_id>/heal-journal.json  -> list of:
{ "element_key": "...", "before_chain": [...], "after_chain": [...],
  "confidence": 0.91, "outcome": "auto_heal", "flow_id": "flow-0",
  "live_match_count": 1, "ts": "..." }

# Worker (post-subprocess, has SessionLocal + neo4j): ingest.py
#   1. Postgres: INSERT HealAudit rows (before/after/conf/outcome/run_id/flow_id/element_key)
#   2. page-object rewrite: open workspaces/<run_id>/target/pages/<module>.py, replace the
#      locator literal for element_key with the new top chain entry (SAFE: key-targeted,
#      AST-or-line precise, only for outcome=auto_heal; quarantine/fail rewrites are STAGED
#      but gated behind the apply API).
#   3. KG: kg/writer.append_element_history(key, new_chain, ...) — NEW single-writer fn.
```
- **Migration 0008** copies `0007_execution_history.py` shape exactly (revision `'0008'`, `down_revision='0007'`).
- **The KG write-back** is a NEW function in `kg/writer.py` (the ONLY sanctioned write path) — it MUST use managed `execute_write` + parameterized Cypher + the `RETURN count(*) AS n` read-back guard (the SC1 invariant). It appends to `history_json` (read-modify-write the existing JSON via `_UPSERT_ELEMENT`-style SET, or a dedicated MERGE that appends a `{step, chain}` snapshot). REUSE `merge_locator_history` (pure) from `explorer/locators.py` to build the new history list before serializing.

### Pattern 5: Per-element heal stats (HEAL-04)
**What:** Aggregate `heal_audit` by `element_key` for success-rate and false-heal-rate — mirrors the Phase-7 execution-history aggregation queries.
- **heal success rate** = `count(outcome IN (auto_heal, applied)) / count(all heal attempts)` per element_key.
- **false-heal rate** = `count(outcome=auto_heal AND later_rejected) / count(auto_heal)` per element_key. (A `rejected` outcome on a previously auto-healed/quarantined row marks a false heal — captured by the reject API flipping a `reviewed_outcome` column or inserting a linked row.)
- Exposed via `GET /heals/stats` (and per-element `GET /heals/stats?element=<key>`). Dashboard RENDERING is Phase 10; this phase only persists + exposes.

### Pattern 6: The benign-vs-breaking mutation catalog (QUAL-02)
**What:** Extend the SEED_BUG Dockerfile build-arg pattern with a catalog of mutations; benign ones MUST heal (>90%), breaking ones MUST still fail (~0 false-heal). Keyless, deterministic, on planted specs.

| Class | Mutation | Dockerfile `sed` rewrite (build-arg) | Expected outcome |
|-------|----------|--------------------------------------|------------------|
| BENIGN | rename `data-test` attribute value | `s/data-test="add-to-cart"/data-test="add-to-cart-btn"/` | HEAL (alt tiers — role/text/aria still match) |
| BENIGN | change visible text | `s/>Add to cart</>Add item</` | HEAL (data-test/role/bbox still match) |
| BENIGN | change tag (`<button>`→`<a role=button>`) | tag rewrite | HEAL (role + a11y name + bbox match) |
| BENIGN | reorder siblings / move element | reorder DOM block | HEAL (attrs + role match; xpath changes but isn't the only tier) |
| BENIGN | add wrapper `<div>` (ancestry shift) | wrap element | HEAL (attrs/role/bbox unchanged) |
| BREAKING | remove the element entirely | delete the node | FAIL-as-defect (0 live matches → uniqueness gate forbids heal) |
| BREAKING | break the post-login flow (existing SEED_BUG `.inventory_list`→`_BROKEN`) | EXISTING build-arg | FAIL (assertion target, not a locator → product_failure) |
| BREAKING | duplicate the element (ambiguous) | clone the node | FAIL (live_match_count > 1 → uniqueness gate forbids heal) |
| BREAKING | change semantics (button → disabled/different role+action) | role/disabled rewrite | FAIL (a11y mismatch lowers conf below MED; or click no-ops → assertion fails) |

**Measurement (deterministic, keyless):** For each BENIGN build, run the planted spec; assert the heal-journal records `auto_heal` (and the spec passes). For each BREAKING build, assert the spec FAILS and the journal records `fail_as_defect`/`quarantine` (NEVER `auto_heal` on a removed/duplicated/semantically-changed element). Aggregate: `benign_heal_rate = healed_benign / total_benign >= 0.90`; `false_heal_rate = auto_healed_breaking / total_breaking ~= 0`. This mirrors `test_seeded_bug.py`'s accept/reject assertions exactly, extended to a catalog.

### Anti-Patterns to Avoid
- **Healing in the worker around the subprocess:** Impossible — no live page handle. (The single most likely planning mistake.)
- **Giving the generated spec project DB/Neo4j credentials:** Breaks subprocess isolation + the single-write-path gate. Use the file-journal handoff.
- **Pixel-diff visual similarity with a new image lib:** Non-deterministic across environments + a new dependency. Use bounding-box IoU geometry.
- **Weakening an assertion to make a test green:** Forbidden invariant (D-04). Heal ONLY locator resolution; never `expect(...)`.
- **Auto-healing on a non-unique live match:** The uniqueness gate (`count()==1`) is the structural false-heal guard — never bypass it on a high score.
- **Labeling an auto-heal as `flaky`:** `classify_retry` would mislabel a healed pass as flaky if it needed a retry. The journal-driven `auto_healed` verdict must take precedence.
- **Interpolating page-derived text into Cypher / locator rewrites:** Carry the T-04-14/T-05-01 parameterization + the run_id-derived-path discipline into the KG write-back and the page-object rewrite.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Locator-chain priority ordering | A new ordering scheme | `explorer/locators.build_locator_chain` (PURE, already healing-priority ordered) | It is literally documented as "so Phase 8 healing can fall back" |
| Element history snapshots | A new history store | `element_detail(key).history` + `merge_locator_history` (append-only `{step, chain}`) | Already the Phase-4 healing seam |
| xpath extraction | A new xpath generator | `explorer/locators._XPATH_JS` (REUSE verbatim) | Already produces stable absolute xpaths |
| KG writes | Direct Cypher anywhere | A new `kg/writer.py` single-writer fn (managed `execute_write` + read-back + parameterized) | The single-write-path grep gate must stay green |
| Subprocess spec runs | `pytest.main` / in-process | `stability._run_spec_once` (argv list, no shell, isolated) | Sync Playwright in-process deadlocks the asyncio API (Pitfall 3 / T-06-19) |
| Migration scaffolding | Hand-written DDL | Copy `0007_execution_history.py` | Exact revision-chain + index style already proven |
| Confidence/band math shape | A bespoke scorer | Mirror `kg/risk.py` (`@dataclass(frozen=True)` weights + pure clamped blend + tier fn) | Established, table-tested pattern; reviewers expect it |
| Mutation/seeded-bug harness | A new test target | Extend `infra/targets/saucedemo/Dockerfile` SEED_BUG build-args + `test_seeded_bug.py` | Proven keyless trust-gate pattern |
| Auth on the quarantine API | A new auth scheme | `get_current_user` cookie/CI-token gate (as `executions.py`) | 4-role `require_role` DI doesn't exist yet; don't invent it here |

**Key insight:** Phase 8 is overwhelmingly an ASSEMBLY of existing seams. The genuinely new code is small: the pure scorer (`confidence.py`/`candidates.py`/`geometry.py`), the in-spec `_healing.py` template, the worker ingest, one model + one migration + one KG writer fn, and one router. Everything else is reuse.

## Runtime State Inventory

> Phase 8 is primarily new code + a new table, NOT a rename/refactor. This section is included because the heal write-back touches stored KG state and the page-object rewrite mutates generated artifacts.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Neo4j `:Element.history_json` (append-only `{step, chain}` snapshots) — the heal write-back APPENDS a new snapshot; `:Element.chain_json` (the current chain) — an applied heal updates the top tier. Postgres gains a new `heal_audit` table (no existing data migrated). | New single-writer KG fn (append history; optionally update chain_json on applied heal); migration 0008 creates the table. NO destructive migration of existing Element data. |
| Live service config | None — healing adds no external service config. Neo4j availability sequencing carries from Phase 7 (graph_mode). | None new. Reuse the Phase-7 3GB sequencing note (below). |
| OS-registered state | None. | None. |
| Secrets/env vars | New tunable settings only: `HEAL_HIGH_THRESHOLD`, `HEAL_MED_THRESHOLD`, `HEAL_ENABLED` (mirror `STABILITY_RUNS`). No secrets. | Add to `core/config.py` Settings + compose env (compose does not pass whole .env — carry the Phase-2 lesson). |
| Build artifacts | Generated project tree under `workspaces/<run_id>/target/pages/*.py` — an applied heal REWRITES the locator literal in place. The heal-journal JSON is a NEW per-flow artifact under `workspaces/<run_id>/<flow_id>/`. | Worker ingest rewrites pages safely (key-targeted); journal is gitignored (workspaces/ already gitignored). No stale-package concern (no `pip install -e`). |

## Common Pitfalls

### Pitfall 1: Assuming the worker can heal (no live page handle)
**What goes wrong:** Planner places healing in `worker/job.py` around the subprocess.
**Why it happens:** "Inline in the worker" (D-01) is read literally; but the worker only runs `uv run pytest` and reads exit codes.
**How to avoid:** Heal INSIDE the spec (Pattern 1). The worker's role is the POST-run journal INGEST. "Inline in the worker plane" = the worker-orchestrated subprocess, not the worker process itself.
**Warning signs:** A design that calls `page.locator()` from `job.py` — there is no `page` there.

### Pitfall 2: Sync Playwright in-process deadlock
**What goes wrong:** Running the spec in-process to "get the page handle" deadlocks/crashes the asyncio API.
**Why it happens:** The generated spec uses the SYNC Playwright API (T-06-19).
**How to avoid:** Keep the isolated-subprocess model (`stability._run_spec_once`). The page handle lives in the subprocess; heal there; hand off via file.
**Warning signs:** `pytest.main(...)` or `async_playwright` inside the API process for healing.

### Pitfall 3: False heal on a non-unique match
**What goes wrong:** A high DOM/visual score on a duplicated element auto-heals to the wrong node.
**Why it happens:** Confidence alone, without the uniqueness gate.
**How to avoid:** The hard `live_match_count == 1` gate in `heal_outcome` (Pattern 3) — structural, not score-based.
**Warning signs:** Mutation harness shows a BREAKING "duplicate element" build healing.

### Pitfall 4: Mislabeling a healed pass as flaky
**What goes wrong:** A heal that needed a retry attempt gets `classify_retry` verdict `flaky`.
**Why it happens:** `classifier.classify_retry` only sees exit codes; a retried pass = flaky.
**How to avoid:** Journal-driven verdict precedence: if the journal has an `auto_heal` event for the flow, the verdict is `auto_healed`, overriding `passed`/`flaky` (Pattern 1 reconciliation).
**Warning signs:** TestResult shows `flaky` for a run whose journal recorded an auto-heal.

### Pitfall 5: KG write-back outside the single writer
**What goes wrong:** Healing writes Cypher directly, breaking the single-write-path grep gate.
**Why it happens:** Convenience of writing where the data is read.
**How to avoid:** Add ONE new fn to `kg/writer.py` (managed `execute_write` + parameterized + read-back guard). All graph writes route there.
**Warning signs:** `execute_write` or `tx.run(...MERGE...)` anywhere outside `kg/writer.py`.

### Pitfall 6: Neo4j memory / sequencing under the 3GB WSL cap
**What goes wrong:** Running the mutation harness (saucedemo + mutated builds + Chromium) WITH neo4j up triggers an OOM kill.
**Why it happens:** Host 5.7GB / WSL cap 3GB; postgres+redis+api+neo4j+targets ≈ near the ceiling (Phase-7 T-06-20).
**How to avoid:** SEQUENCE — the mutation RUN phase needs NO neo4j (the spec is already written; healing reads vendored chains/history from the spec, not the graph). Stop neo4j before the harness, exactly as `test_seeded_bug.py` documents. The LIVE KG write-back (applied heal) happens in the worker under graph_mode separately.
**Warning signs:** OOM kill during `test_healing_mutations.py`.

### Pitfall 7: Non-deterministic visual similarity
**What goes wrong:** Pixel-diff visual scores vary across OS/font rendering → flaky heal decisions.
**Why it happens:** Reaching for an image-diff lib (Pillow/opencv).
**How to avoid:** Bounding-box IoU geometry only (Pattern 2). Deterministic, keyless, zero-dep.
**Warning signs:** A new image package in the plan; visual sub-scores that differ between CI and local.

## Code Examples

### Bounding-box IoU visual sub-score (pure, no Playwright import)
```python
# Source: app/services/healing/geometry.py (NEW). Box = {"x","y","width","height"} as returned
# by playwright locator.bounding_box() [CITED: playwright.dev/python/docs/api/class-locator]
def iou(a: dict | None, b: dict | None) -> float:
    """PURE: intersection-over-union of two bounding boxes -> [0,1]. None (off-screen) -> 0."""
    if not a or not b:
        return 0.0
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    ix = max(0.0, min(ax2, bx2) - max(a["x"], b["x"]))
    iy = max(0.0, min(ay2, by2) - max(a["y"], b["y"]))
    inter = ix * iy
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union > 0 else 0.0
```

### Live candidate search + re-validate (in-spec, sync Playwright)
```python
# Source: templates/healing/_healing.py.j2 (NEW). PSEUDO — runs INSIDE the spec subprocess.
# Reuses build_locator_chain ordering + _XPATH_JS from explorer/locators (vendored).
def heal(page, *, element_key, broken_chain, history, weights, high, med):
    candidates = _enumerate_live_candidates(page, broken_chain)   # by role/attrs near xpath ancestry
    scored = []
    for cand in candidates:
        signals = {
            "dom":     _dom_sim(cand, broken_chain),
            "visual":  iou(cand["bbox"], broken_chain_bbox),
            "a11y":    _a11y_sim(cand, broken_chain),
            "history": _history_sim(cand, history),
        }
        scored.append((confidence(signals, weights), cand))
    scored.sort(reverse=True, key=lambda t: t[0])
    conf, best = scored[0] if scored else (0.0, None)
    selector = _to_selector(best) if best else None
    match_count = page.locator(selector).count() if selector else 0   # HARD live re-validation
    outcome = heal_outcome(conf, match_count, high=high, med=med)
    _append_journal(element_key, broken_chain, best, conf, outcome, match_count)
    if outcome == "auto_heal":
        return page.locator(selector)        # continue the test with the healed locator
    raise HealFailed(outcome)                # quarantine / fail -> the test fails (no weakened assert)
```

### New KG single-writer fn (history append)
```python
# Source: app/services/kg/writer.py (EXTEND) — mirrors _UPSERT_ELEMENT + the SC1 read-back guard
_APPEND_ELEMENT_HISTORY = (
    "MATCH (e:Element {key:$key}) "
    "SET e.history_json=$history_json, e.chain_json=$chain_json, e.last_verified=$now "
    "RETURN count(*) AS n"
)
async def append_element_history(*, key, history_json, chain_json, now, driver=None):
    return await _write(_APPEND_ELEMENT_HISTORY,
        {"key": key, "history_json": history_json, "chain_json": chain_json, "now": now},
        driver=driver, what="append_element_history")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LLM-assisted/vision heal ranking | Deterministic blend + hard uniqueness gate | D-02 (this project) | Keyless, reproducible, no false-heal hallucination, mutation-harness-provable |
| Pixel-diff visual regression libs | Bounding-box IoU geometry | This phase | Zero-dep, deterministic across environments |
| Selenium self-healing plugins (e.g. Healenium) | Playwright-native live re-validation in-spec | This phase | No external healing service; reuses the existing locator chain + KG history |

**Deprecated/outdated:**
- Any in-process spec execution for healing → REJECTED (sync Playwright deadlock).
- Image-diff dependency for visual similarity → avoid for v1 (geometry suffices).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Default blend weights `dom=0.30, visual=0.20, a11y=0.30, history=0.20` | Pattern 2 | LOW — weights are config-tunable and TUNED by the mutation harness; starting values only |
| A2 | Default bands `high=0.85, med=0.60` | Pattern 3 | MEDIUM — too-low `high` risks false heals; mitigated structurally by the uniqueness gate; tune via harness |
| A3 | Bounding-box IoU geometry discriminates benign vs breaking adequately (no pixel diff needed) | Stack / Pattern 2 | MEDIUM — if IoU alone is weak, a11y+DOM sub-scores compensate; pixel diff is the gated fallback |
| A4 | The generated project has NO DB/Neo4j access (file-journal handoff is required) | Architecture | LOW — verified: `codegen/project.py` renders only `pages/steps/conftest`; no driver imports |
| A5 | A new `auto_healed` verdict (+ `quarantined`) is added to the TestResult vocabulary | Pattern 1 | LOW — additive to the existing `passed/flaky/product_failure/aborted` enum (String(16) column, no schema change needed) |
| A6 | `require_role` 4-role DI is NOT built yet; quarantine API uses `get_current_user` | Quarantine API | LOW — verified: no `require_role` in the codebase; `executions.py` uses `get_current_user` |
| A7 | Element history/chains can be vendored into `_healing.py` at codegen time (so the keyless harness needs no live graph) | Pattern 2 / Pitfall 6 | MEDIUM — keeps the harness graph-free; the LIVE write-back still uses the graph in the worker |

## Open Questions

1. **Page-object rewrite precision (line vs AST):**
   - What we know: locators are single literals in `page.locator(<selector>)` lines (template `page_object.py.j2`), one per attr.
   - What's unclear: whether a line-targeted replace (find the `self.<attr> = page.locator(...)` line) or a full AST rewrite is safer.
   - Recommendation: line-targeted replace keyed by the attr name (deterministic, the template guarantees one line per attr); validate with `ast.parse` after rewrite (reuse the codegen `_render_checked_py` discipline). Plan as a small task with a unit test on a fixture page object.

2. **Where the pure scorer is vendored for the in-spec layer:**
   - What we know: the in-spec `_healing.py` needs `confidence`/`heal_outcome`/`iou`/sub-scores; the generated project can't import `app.services`.
   - What's unclear: copy the pure functions into the template vs ship a tiny vendored module.
   - Recommendation: render the pure functions INTO `_healing.py.j2` (they're stdlib-only and small), so the generated project is self-contained. Keep the canonical copy in `app/services/healing/` for unit tests; assert byte-equivalence in a test (a drift guard).

3. **Auto-heal application timing (stage vs apply):**
   - What we know: auto-heal continues the test live; the rewrite happens in worker ingest.
   - What's unclear: does an auto-heal IMMEDIATELY rewrite the page object, or stage it like quarantine?
   - Recommendation: auto-heal rewrites immediately (it's high-confidence + unique-validated, the whole point of D-04); quarantine/fail STAGE the proposed rewrite behind the apply API. Audit row outcome distinguishes them.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Playwright + Chromium | In-spec live candidate search, mutation harness | ✓ (Phase 6/7) | 1.60.x | none needed |
| `uv` runner | subprocess spec runs | ✓ (Phase 3/6/7) | — | honest-failure path already exists |
| PostgreSQL | heal_audit table | ✓ (Phase 1) | 15.x | none |
| Neo4j | KG history write-back (LIVE path only) | ✓ via graph_mode | 6.x server | mutation harness needs NO neo4j (sequenced) |
| Docker / compose | mutation-build targets (saucedemo variants) | ✓ (Phase 1/6) | — | none |
| Provider LLM key | NOT required (deterministic engine) | ✗ (empty) | — | N/A — engine is keyless by design |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** provider keys absent — irrelevant; the engine + harness are keyless. Only a live end-to-end heal during a real LLM-generated-suite run is Manual-Only (needs keys + target up).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.x + pytest-asyncio 1.4.x (`asyncio_mode=auto`); pytest-playwright for the in-spec proof |
| Config file | `apps/api/pyproject.toml` `[tool.pytest.ini_options]` (markers: `functional`, `graph`) |
| Quick run command | `cd apps/api && uv run pytest tests/unit/test_heal_confidence.py -q` |
| Full suite command | `cd apps/api && uv run pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HEAL-01 | 4 sub-scores + priority-chain candidate ordering | unit | `uv run pytest tests/unit/test_heal_candidates.py -q` | ❌ Wave 0 |
| HEAL-01 | blend → [0,1] confidence (pure, fixture dicts) | unit | `uv run pytest tests/unit/test_heal_confidence.py -q` | ❌ Wave 0 |
| HEAL-02 | 3-outcome banding + uniqueness gate (pure) | unit | `uv run pytest tests/unit/test_heal_outcome.py -q` | ❌ Wave 0 |
| HEAL-02 | assertions never weakened (heal touches only locators) | unit | `uv run pytest tests/unit/test_heal_outcome.py::test_assertion_never_healed -q` | ❌ Wave 0 |
| HEAL-03 | journal ingest → heal_audit rows | integration | `uv run pytest tests/integration/test_heal_ingest.py -q` | ❌ Wave 0 |
| HEAL-03 | page-object rewrite by element key (ast-valid) | unit | `uv run pytest tests/unit/test_page_object_rewrite.py -q` | ❌ Wave 0 |
| HEAL-03 | KG history append via single writer | integration (graph) | `uv run pytest -m graph tests/integration/test_heal_kg_writeback.py -q` | ❌ Wave 0 |
| HEAL-04 | per-element success/false-heal aggregation | integration | `uv run pytest tests/integration/test_heal_stats.py -q` | ❌ Wave 0 |
| QUAL-02 | benign builds heal (>90%) on planted specs, keyless | functional (graph-marked, neo4j-off) | `uv run pytest -m functional tests/functional/test_healing_mutations.py -q` | ❌ Wave 0 |
| QUAL-02 | breaking builds still FAIL (~0 false-heal) | functional | `uv run pytest -m functional tests/functional/test_healing_mutations.py -q` | ❌ Wave 0 |
| D-05 | quarantine API list/apply/reject auth-gated | integration | `uv run pytest tests/integration/test_heals_router.py -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the relevant `tests/unit/test_heal_*.py` (sub-second, no browser/DB).
- **Per wave merge:** `cd apps/api && uv run pytest -q` (unit + integration; functional/graph gated by marker + services up).
- **Phase gate:** full suite green + the mutation harness (`test_healing_mutations.py`) proving >90% benign-heal AND ~0 false-heal, with neo4j stopped (3GB sequencing), before `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] `tests/unit/test_heal_confidence.py` — covers HEAL-01 (blend, clamp)
- [ ] `tests/unit/test_heal_candidates.py` — covers HEAL-01 (sub-scores on fixture dicts)
- [ ] `tests/unit/test_heal_outcome.py` — covers HEAL-02 (bands + uniqueness gate + never-weaken)
- [ ] `tests/unit/test_page_object_rewrite.py` — covers HEAL-03 (safe rewrite)
- [ ] `tests/unit/test_geometry.py` — covers the IoU visual sub-score
- [ ] `tests/integration/test_heal_ingest.py` — covers HEAL-03 (journal → audit rows)
- [ ] `tests/integration/test_heal_kg_writeback.py` (graph) — covers HEAL-03 (single-writer append)
- [ ] `tests/integration/test_heal_stats.py` — covers HEAL-04
- [ ] `tests/integration/test_heals_router.py` — covers D-05 (auth-gated list/apply/reject)
- [ ] `tests/functional/test_healing_mutations.py` — covers QUAL-02 (the trust gate, keyless)
- [ ] `infra/targets/saucedemo/Dockerfile` build-args + compose services for the mutation catalog
- [ ] `tests/conftest.py` — reuse the existing `_plant`/host-driver fixtures from `test_stability.py`

## Security Domain

> `security_enforcement` is not set to `false` in config → included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Quarantine API gated by `get_current_user` (cookie/CI-token), as `executions.py` |
| V3 Session Management | yes (reuse) | Existing JWT/httpOnly-cookie session (PyJWT) — no new session surface |
| V4 Access Control | partial | Apply/reject mutate generated artifacts + DB — must require an authenticated user; (4-role RBAC is a later phase, but the apply/reject endpoints are state-changing and MUST be auth-gated, not public) |
| V5 Input Validation | yes | `heal_id` is an int PK; `element` filter is a string — parameterize all queries (SQLAlchemy ORM). The heal-journal is machine-written under a run_id-derived path, but VALIDATE its shape on ingest (reject malformed entries) |
| V6 Cryptography | no | No new crypto; no hand-rolled hashing for security purposes (`hashlib` use, if any, is non-security tiebreak only) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cypher injection via page-derived text in the KG write-back | Tampering | Parameterized Cypher ONLY; labels/edge-types are `kg/schema` constants (carry T-04-14/T-05-01) |
| Path traversal via journal-supplied paths | Tampering | All paths run_id-derived via `workspaces` helpers; never trust a path from the journal body (carry T-07-11) |
| Command injection via the spec rewrite / subprocess | Tampering | argv-list, no `shell=True`; rewrite is line-targeted by attr name, ast-validated (carry T-03-15/T-06-18) |
| Malformed heal-journal crashing ingest | DoS | Tolerant parse (mirror `kg/reader._loads`); reject bad entries, never crash the worker |
| Unauthenticated apply/reject mutating state | Elevation of Privilege | Auth-gate every mutating endpoint with `get_current_user` |
| Binary blob / unbounded data in Postgres | DoS | heal_audit stores chains as JSON + scalars only; no blobs (carry the execution-history rule) |

## Sources

### Primary (HIGH confidence)
- Codebase (read this session): `explorer/locators.py`, `kg/reader.py`, `kg/writer.py`, `kg/risk.py`, `codegen/locators.py`, `codegen/project.py`, `templates/pages/page_object.py.j2`, `templates/conftest.py.j2`, `templates/steps/steps.py.j2`, `stability.py`, `worker/job.py`, `worker/classifier.py`, `execution.py`, `models/execution_history.py`, `alembic/versions/0007_execution_history.py`, `tests/functional/test_seeded_bug.py`, `tests/functional/test_stability.py`, `infra/targets/saucedemo/Dockerfile`, `routers/executions.py` — the seams, invariants, and hook points.
- `CLAUDE.md` — locked stack, single-writer rule, no-LLM-in-loop, Playwright 1.60.
- `.planning/REQUIREMENTS.md` — HEAL-01..04, QUAL-02 verbatim.
- `playwright.dev/python/docs/api/class-locator` — `bounding_box()`, `count()`, `screenshot(clip=...)` deterministic element-region APIs [CITED, accessed 2026-06-22].

### Secondary (MEDIUM confidence)
- Phase 08 CONTEXT.md (D-01..D-05) — locked decisions.
- Phase 07 SUMMARYs (via job.py/classifier.py docstrings) — retry/flaky reconciliation, 3GB sequencing.

### Tertiary (LOW confidence)
- WebSearch (Playwright screenshot/bbox) — corroborated against official docs; default weights/thresholds are ASSUMED starting points (Assumptions A1–A3), tuned by the mutation harness.

## Metadata

**Confidence breakdown:**
- Architecture / hook point / seams: HIGH — verified directly against the worker, execution, codegen, and generated-project code.
- Standard stack (zero new packages): HIGH — every dependency already pinned and used; Playwright geometry APIs confirmed.
- Similarity metrics shape: HIGH — mirrors `kg/risk.py`/`build_locator_chain`; exact weights MEDIUM/LOW (tuned by harness, by design).
- Band thresholds: MEDIUM — config-tunable starting points; the uniqueness gate provides the structural false-heal guarantee independent of thresholds.
- Mutation catalog: HIGH on the pattern (extends SEED_BUG); MEDIUM on the exact `sed` rewrites (validate per build).

**Research date:** 2026-06-22
**Valid until:** 2026-07-22 (stable — internal seams + a pinned stack; re-check only if Playwright is bumped past 1.60)
