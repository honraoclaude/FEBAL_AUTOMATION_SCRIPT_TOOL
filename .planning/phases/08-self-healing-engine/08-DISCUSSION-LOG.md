# Phase 8: Self-Healing Engine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-22
**Phase:** 8-self-healing-engine
**Areas discussed:** Where healing runs, Deterministic vs LLM healing, Heal-as-commit semantics, Confidence banding

---

## Where healing runs (HEAL-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Inline in the worker, deterministic | Locator failure mid-run → deterministic heal + live re-validate before the attempt is scored; auto-heal continues, quarantine/fail resolve the test | ✓ |
| Separate post-failure pass | Run completes, a separate healing job replays + re-runs failures (could use LLM); slower, run never self-heals | |
| Hybrid inline + async deep | Inline quick heal, inconclusive cases queued to a deeper offline pass | |

**User's choice:** Inline in the worker, deterministic
**Notes:** Fastest path to green; reuses the live page/browser context; honors the Phase-7 SC3 NO-LLM-in-the-execution-loop invariant precisely because the engine is deterministic.

---

## Healing engine — deterministic vs LLM (HEAL-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Purely deterministic | DOM + visual + a11y + historical-mapping similarity, blended confidence, live re-validation; keyless, auditable, no hallucinated false-heal | ✓ |
| LLM-assisted ranking | Deterministic candidate gathering, LLM picks best; spend, non-determinism, hallucination risk, key-dependent harness | |

**User's choice:** Purely deterministic
**Notes:** Fits the deterministic-gate ethos + near-zero-false-heal goal; the mutation harness runs without provider keys.

---

## Heal-as-commit semantics (HEAL-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Audit row + file rewrite + KG write-back | Page-object locator rewrite by element key + Postgres heal-audit row (before/after, confidence, outcome, run_id) + KG Element-history via single writer; diff rendered from the audit record | ✓ |
| Literal git commit in workspace | workspaces/<run_id>/ becomes a git repo; each heal a real commit, diff = git diff; adds git plumbing per ephemeral workspace | |

**User's choice:** Audit row + file rewrite + KG write-back
**Notes:** Keeps the ephemeral workspaces model intact; consistent with how Phase-7 persists artifacts/history (filesystem + Postgres rows + KG structure).

---

## Confidence banding → 3 outcomes (HEAL-02 / QUAL-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Conservative + live re-validate gate | Auto-heal only on high confidence AND a unique live re-validation; medium → quarantine; low → fail-as-defect; tuned so seeded bugs fail (false-heal ~0), more quarantines | ✓ |
| Balanced auto-heal-leaning | Lower auto-heal bar → higher raw heal rate, fewer quarantines, more false-heal risk | |

**User's choice:** Conservative + live re-validate gate
**Notes:** Structurally enforces the QUAL-02 near-zero-false-heal target; thresholds config-tunable, exact bands derived from the mutation harness.

---

## Claude's Discretion

- The four similarity metrics + the blended-confidence formula/weights + the live re-validation uniqueness check.
- The benign-vs-breaking mutation catalog (which mutations heal vs must fail) extending the SEED_BUG/planted-spec harness, measured keylessly.
- The heal-audit data model + migration 0008; per-element heal-success/false-heal aggregation for HEAL-04.
- The exact inline worker hook point + the Phase-7 retry/flaky reconciliation + the TestResult verdict mapping (auto-healed/quarantined/failed).
- Whether Phase 8 needs its own minimal quarantine-review UI-SPEC or defers all heal UI to Phase 10.

## Deferred Ideas

- Failure classification + Jira filing → Phase 9 (fail-as-defect feeds it).
- Heal-success/false-heal dashboards + trends → Phase 10.
- LLM-assisted heal ranking → rejected.
- Literal git-versioned workspaces → rejected for v1.
- K8s/Prometheus heal metrics → Phase 11.
