---
phase: 9
slug: defect-intelligence-jira-agent
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-27
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (pytest-asyncio 1.4, asyncio_mode=auto) + pytest-playwright + pytest-bdd; frontend tsc/eslint/playwright. NOTE: invoke as `uv run python -m pytest` (Windows AppControl blocks the `pytest.exe` shim — os error 4551). |
| **Config file** | apps/api/pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd apps/api && uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional" -q` (the deterministic classifier rules + 0-100 confidence, fingerprint normalization, JQL-dedup query build, per-run cap, the autonomy-gate logic, the Jira contract via FakeJira, the draft-queue apply/reject service — keyless, no neo4j, no real Jira) |
| **Full suite command** | `cd apps/api && uv run python -m pytest -m "not live_llm" -q` (adds functional: the retry→classify wiring over execution-history rows, the QUAL-03 accuracy harness against the labeled failure set generated from seeded-bug/mutation/infra-fault builds, the draft-queue router round-trip) |
| **Frontend command** | `cd apps/web && npx tsc --noEmit && npx eslint "app/(dashboard)/defects" <touched> && npx playwright test tests/e2e/defects.spec.ts` (path QUOTED — parens break POSIX sh) |
| **Estimated runtime** | ~4-6 min (the labeled-set accuracy harness runs known-class failures; the rest is fast unit/contract) |

---

## Sampling Rate

- **After every task commit:** `cd apps/api && uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional" -q`
- **After every plan wave:** full suite (the QUAL-03 harness needs the seeded-bug/mutation/infra-fault builds up; neo4j OFF in the run phase, 3GB cap)
- **Before `/gsd:verify-work`:** full deterministic suite green; the QUAL-03 accuracy harness ≥85% on the labeled set + the calibrated threshold derived; the Jira contract green vs FakeJira; a live classify→draft→(human-flip)→file→dedup demonstrated against a real Jira Cloud + provider keys (Manual-Only)
- **Max feedback latency:** ~6 min

---

## Per-Task Verification Map

> Populated by the planner. Each task maps to DEF-01/02/03 / JIRA-01..04 / QUAL-03, a test type
> (unit deterministic on fixtures / functional over execution-history + labeled builds / contract via
> FakeJira / live_llm+live-Jira-manual), a threat ref, and a keyless command. The classifier rules +
> confidence, fingerprint/dedup/cap, the autonomy gate, the QUAL-03 accuracy harness, the draft queue,
> and the Jira contract (FakeJira) are ALL deterministic WITHOUT keys/real-Jira; live LLM description
> enrichment + live Jira filing are Manual-Only.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | DEF-01..03, JIRA-01..04, QUAL-03 | — | populated by planner | — | — | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] atlassian-python-api 4.0.x added to apps/api/pyproject.toml + `uv sync` (the ONE expected new dep; locked in CLAUDE.md) — gated (checkpoint:human-verify). anyio is already transitive via FastAPI — verify, do NOT add.
- [ ] `test_results.error_text` column + `job.py` persisting the last-attempt subprocess output (the classifier's error-type taxonomy needs it; today job.py discards `output`) — migration 0009 (chains after 0008) + the worker edit
- [ ] A `JiraGateway` Protocol + a hand-written `FakeJira` test double (create/attach/transition/JQL/link) so JIRA-01/03 logic is keyless-CI-testable WITHOUT a real Jira instance
- [ ] The QUAL-03 LABELED failure set generated keylessly: Product = the SEED_BUG build; Automation = an un-healed/quarantined locator mutation (Phase-8 mutation builds); Infrastructure = a NEW injected infra fault (dead target port / forced timeout) — plus the accuracy computation + threshold calibration
- [ ] defects/classifications model + migration 0009 (class, confidence, evidence json, fingerprint, jira_key/label, status, test/flow/execution links)
- [ ] Existing functional infra (live-HTTP client, authed_client, the heals apply/reject router pattern, execution-history + heal_audit evidence, the seeded-bug/mutation builds) carries forward

*Existing infrastructure (the kg/risk + healing/confidence frozen-weights pattern, the QUAL-02 harness shape, the heals.py auth-gated apply/reject router, the gateway no-key fallback) covers most of the phase; atlassian-python-api + FakeJira + the labeled-set + the error-text persistence are the new Wave-0 pieces.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live classify → draft → human-flip → autonomous file → dedup | DEF-01, JIRA-01/02/03/04 | Needs a real Jira Cloud instance + API token (+ provider keys for description enrichment) | Configure the Jira token; run a tier with real failures; review drafts + the accuracy/precision panel; flip jira_autonomous_enabled; confirm above-threshold defects file with full evidence/attachments + links; re-run → the duplicate UPDATES the same issue (JQL); per-run cap holds |
| Live LLM description enrichment | JIRA-01 | Needs provider keys | With keys set, confirm the Jira description prose is LLM-enriched; without keys the deterministic fallback description is used |

*Deterministic logic (classifier rules + confidence, fingerprint/dedup/cap, autonomy gate, the QUAL-03 accuracy harness, the draft queue, the Jira contract via FakeJira) is automated WITHOUT keys or a real Jira.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (atlassian-python-api, FakeJira, labeled set, error-text persistence, migration 0009)
- [ ] No watch-mode flags
- [ ] Feedback latency < 6 min
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
