---
phase: 9
slug: defect-intelligence-jira-agent
status: draft
nyquist_compliant: true
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
| 09-01 T1 | 01 | 1 | DEF-01, DEF-02 | T-09-03, T-09-04 | migration 0009 reversible; jira_api_token never logged; job.py persists error_text with no new imports (no-llm gate) | migration + unit (grep gate) | `cd apps/api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` ; `cd apps/api && uv run python -m pytest tests/unit/test_no_llm_in_worker.py -q` | ✅ | ⬜ pending |
| 09-01 T2 | 01 | 1 | DEF-01 | T-09-01, T-09-02 | pure classifier + fingerprint, no eval/exec; NO-LLM grep gate over defects/; hostile error_text only changes the hex | unit (fixtures + grep gate) | `cd apps/api && uv run python -m pytest tests/unit/test_classifier.py tests/unit/test_fingerprint.py tests/unit/test_no_llm_in_classifier.py -q` | ✅ | ⬜ pending |
| 09-01 T3 | 01 | 1 | DEF-02 | T-09-01 | evidence joins ORM-parameterized; evidence.py imports no LLM path; classify post-retry | unit (seeded rows) | `cd apps/api && uv run python -m pytest tests/unit/test_classifier_evidence.py -q` | ✅ | ⬜ pending |
| 09-02 T1 | 02 | 2 | DEF-03, QUAL-03 | T-09-06, T-09-07 | keyless three-class labeled set; neo4j OFF; dead-port infra fault; no keys read | functional (keyless) | `cd apps/api && uv run python -m pytest tests/functional/test_classifier_accuracy.py -m functional -q --collect-only` | ✅ | ⬜ pending |
| 09-02 T2 | 02 | 2 | DEF-03, QUAL-03 | T-09-05 | accuracy ≥85%; threshold calibrated against the SHIPPED settings default, never a test literal | functional (keyless) | `cd apps/api && uv run python -m pytest tests/functional/test_classifier_accuracy.py -m functional -q` | ✅ | ⬜ pending |
| 09-03 T1 | 03 | 2 | JIRA-01 | T-09-11, T-09-SC | atlassian-python-api install gated behind a blocking-human checkpoint (pypi/source/version verified) | checkpoint:human-verify | (gated — human verifies pypi.org/project/atlassian-python-api before install) | ✅ | ⬜ pending |
| 09-03 T2 | 03 | 2 | JIRA-01 | T-09-08, T-09-SC | JiraGateway Protocol + AtlassianJira (anyio.to_thread, token never logged) + FakeJira; keyless create/attach/link contract | unit (FakeJira) | `cd apps/api && uv run python -c "import anyio, atlassian; print(anyio.__version__)"` ; `cd apps/api && uv run python -m pytest tests/unit/test_jira_create.py -q` | ✅ | ⬜ pending |
| 09-03 T3 | 03 | 2 | JIRA-01 | T-09-10 | build_adf returns an ADF v3 DICT (not a string); describe() keyless no-key fallback + not-enriched flag | unit (TDD) | `cd apps/api && uv run python -m pytest tests/unit/test_adf.py tests/unit/test_jira_description.py -q` | ✅ | ⬜ pending |
| 09-04 T1 | 04 | 3 | JIRA-02, JIRA-03 | T-09-12, T-09-13, T-09-14, T-09-15 | may_autofile flag-AND-threshold (flag-off/below never file); fp-<hash> JQL no user text; per-run cap throttles CREATES without dropping drafts; run_id-derived attach paths | unit (FakeJira) | `cd apps/api && uv run python -m pytest tests/unit/test_autonomy_gate.py tests/unit/test_jira_dedup.py -q` | ❌ W4 | ⬜ pending |
| 09-04 T2 | 04 | 3 | JIRA-02, JIRA-04 | T-09-12, T-09-13 | draft Defect row always persisted (cap throttles filing, not classification); run_id/flow_id traceability link regardless of autonomy; OFF never files | integration (FakeJira) | `cd apps/api && uv run python -m pytest tests/integration/test_defect_pipeline.py -q` | ❌ W4 | ⬜ pending |
| 09-04 T3 | 04 | 3 | JIRA-02, JIRA-04 | T-09-16, T-09-17, T-09-15 | every /api/defects endpoint get_current_user-gated (401 unauth); apply files-or-updates + persists jira_key; token never logged; run_id-derived attachment refs; honest not-configured | integration (FakeJira) | `cd apps/api && uv run python -m pytest tests/integration/test_defects_router.py -q` ; `cd apps/api && uv run python -m pytest -m "not live_llm and not e2e and not graph and not functional" -q` | ❌ W4 | ⬜ pending |
| 09-05 T1 | 05 | 4 | JIRA-02 | T-09-19, T-09-SC | zod mirrors the server schema; confidence meter banded off the SERVER threshold; zero new frontend deps | unit (tsc + dep gate) | `cd apps/web && npx tsc --noEmit` ; `cd apps/web && git diff --exit-code package.json package-lock.json` | ❌ W4 | ⬜ pending |
| 09-05 T2 | 05 | 4 | JIRA-02 | T-09-21 | read-only calibration panel (no write toggle); no fabricated confidence/class/accuracy; inline errors not toasts; one sidebar item | unit (tsc + eslint) | `cd apps/web && npx tsc --noEmit` ; `cd apps/web && npx eslint "app/(dashboard)/defects" components/defects components/app-sidebar.tsx lib/api/defects.ts` | ❌ W4 | ⬜ pending |
| 09-05 T3 | 05 | 4 | JIRA-02, JIRA-04 | T-09-18, T-09-20, T-09-21 | auth-gated artifact links from run-relative basenames (never raw paths); honest apply pending→result (no fake success); mocked-API e2e covers every state | e2e (mocked API) | `cd apps/web && npx tsc --noEmit` ; `cd apps/web && npx eslint "app/(dashboard)/defects/[id]" tests/e2e/defects.spec.ts` ; `cd apps/web && npx playwright test tests/e2e/defects.spec.ts` | ❌ W4 | ⬜ pending |

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
| Memory fit under the 3GB WSL cap during the QUAL-03 run phase | DEF-03 | A `docker stats` observation, not assertable in CI | Run the accuracy harness with neo4j OFF + the saucedemo builds + Chromium; confirm total stays under 3GB |

*Deterministic logic (classifier rules + confidence, fingerprint/dedup/cap, autonomy gate, the QUAL-03 accuracy harness, the draft queue, the Jira contract via FakeJira) is automated WITHOUT keys or a real Jira.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (09-03 T1 is the one gated checkpoint:human-verify — install gate, not auto)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (atlassian-python-api, FakeJira, labeled set, error-text persistence, migration 0009)
- [x] No watch-mode flags
- [x] Feedback latency < 6 min
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
