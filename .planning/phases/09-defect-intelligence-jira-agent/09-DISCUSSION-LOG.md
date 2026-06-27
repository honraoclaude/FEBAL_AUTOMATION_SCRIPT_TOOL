# Phase 9: Defect Intelligence & Jira Agent - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-27
**Phase:** 9-defect-intelligence-jira-agent
**Areas discussed:** Classifier engine, Jira client, Autonomous-filing gate, Fingerprint/dedup/cap

---

## Classifier engine (DEF-01/02)

| Option | Description | Selected |
|--------|-------------|----------|
| Deterministic-first + optional LLM enrich | Rules over evidence → class + 0-100 confidence; LLM only enriches the Jira description (no-key fallback); keyless, calibratable, QUAL-03 measured deterministically | ✓ |
| LLM agent + structured output | create_agent tool-loop emits {class, confidence, evidence}; needs keys, non-deterministic, QUAL-03 key-dependent | |
| Hybrid: rules gate, LLM tie-break | Rules decide high-signal cases, LLM adjudicates ambiguous; two calibration surfaces | |

**User's choice:** Deterministic-first + optional LLM enrich
**Notes:** The class/confidence decision is deterministic (keyless, reproducible); the LLM writes description prose only, never the classification.

---

## Jira client (JIRA-01/03)

| Option | Description | Selected |
|--------|-------------|----------|
| atlassian-python-api 4.x (gated dep) | The recommended lib once JQL + links + attachments are in scope; enhanced_jql + ADF v3; sync → anyio.to_thread; one gated dep | ✓ |
| Raw httpx on REST v3 | Already a dep, async, ~200 lines; hand-rolled ADF + nextPageToken paging | |

**User's choice:** atlassian-python-api 4.x
**Notes:** Phase 9 needs create + attachments + transitions + JQL dedup + issue links — exactly where CLAUDE.md says the library wins. One gated new dependency.

---

## Autonomous-filing gate (JIRA-02 / DEF-03 / QUAL-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Config flag, human flips after review | Filing OFF by default; harness measures accuracy + draft precision; human reviews + flips the flag; even then conf ≥ threshold required | ✓ |
| Auto-enable on stored calibration | Calibration record auto-enables filing once thresholds cross; no human gate before real tickets | |

**User's choice:** Config flag, human flips after review
**Notes:** No autonomous ticket can be filed before a human confirms accuracy ≥85% AND draft precision ≥90%. Conservative, auditable, human-in-the-loop.

---

## Fingerprint, dedup & cap (JIRA-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Hash(class+normalized-msg+flow+step) as a Jira label, JQL by label | Fingerprint = stable hash; stored as Jira label fp-<hash>; dedup via JQL labels= ... ; hit updates, miss creates; per-run cap | ✓ |
| Local-DB fingerprint, store Jira key | Fingerprint + Jira key in a local table; dedup checks local only (no JQL); misses external issues | |

**User's choice:** Hash(...) as a Jira label, JQL by label
**Notes:** JQL-based dedup per the spec (self-healing across the platform + external edits); local row stores the Jira key for traceability; per-run cap prevents ticket storms.

---

## Claude's Discretion

- The evidence-taxonomy → class rules + the 0-100 confidence formula/weights (tuned by the labeled set).
- The QUAL-03 hand-labeled failure set (seeded bug → Product; un-healed mutation → Automation; injected infra error → Infrastructure), measured keylessly + threshold calibration.
- The defects/classifications data model + migration 0009 + the evidence joins.
- The atlassian-python-api v3 call shapes (create+ADF / attach / transition / JQL / links) + anyio.to_thread wrapping + the draft-queue apply/reject flow.
- The infra-health evidence source.
- The traceability-chain representation exposed for Phase 10.

## Open question for plan-phase

- UI scope: own minimal draft-review-queue UI-SPEC this phase (JIRA-02 names a review queue; leaning yes) vs API-only + defer all heal/defect UI to Phase 10 — resolve at the plan-phase UI gate (as done for Phase 8).

## Deferred Ideas

- Classification/defect dashboards + traceability visualization + RBAC + Elasticsearch search → Phase 10.
- LLM create_agent classifier → rejected (deterministic decision; LLM prose-only).
- Local-DB-only dedup → rejected (JQL-based).
- K8s/Prometheus defect metrics → Phase 11.
- Bi-directional Jira sync / webhooks → out of v1 scope.
