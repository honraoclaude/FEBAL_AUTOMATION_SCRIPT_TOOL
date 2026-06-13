---
phase: 2
slug: llm-gateway
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-13
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (pytest-asyncio 1.4, asyncio_mode=auto) |
| **Config file** | apps/api/pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd apps/api && uv run pytest tests/unit -q` (mocked init_chat_model — no providers, no spend) |
| **Full suite command** | `cd apps/api && uv run pytest tests -q` (functional hit live stack; `live_llm`-marked parity tests skip when provider keys absent) |
| **Estimated runtime** | ~20-40 seconds (unit + functional); live parity adds provider latency when keys present |

---

## Sampling Rate

- **After every task commit:** Run `cd apps/api && uv run pytest tests/unit -q`
- **After every plan wave:** Run `cd apps/api && uv run pytest tests -q`
- **Before `/gsd:verify-work`:** Full suite green; the `live_llm` two-provider parity test passed at least once with real keys (Success Criterion 1)
- **Max feedback latency:** ~40 seconds

---

## Per-Task Verification Map

> Populated by the planner against the PLAN.md tasks. Each task maps to PLAT-05 or PLAT-06,
> a test type (unit with mocked provider / functional against live stack / live_llm integration),
> and an automated command.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _planner fills_ | | | PLAT-05 / PLAT-06 | | | unit/functional/live_llm | | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `apps/api/tests/unit/conftest.py` — mocked `init_chat_model` fixture (returns canned AIMessage with controllable `usage_metadata`); fake Redis or flushed test DB index for counter/cache tests
- [ ] `apps/api/tests/unit/` package — budget/kill-switch/cache/pricing logic tests that need no live provider
- [ ] `live_llm` pytest marker registered in pyproject.toml + skipif-on-missing-keys helper (ANTHROPIC_API_KEY/OPENAI_API_KEY)

*Existing functional infra (tests/conftest.py live-HTTP client, asyncio_mode=auto) carries forward from Phase 1.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Two-provider parity with REAL keys | PLAT-05 | Requires real ANTHROPIC_API_KEY + OPENAI_API_KEY (cost, not in CI by default) | Set both keys in .env, run `cd apps/api && uv run pytest -m live_llm -q`; confirm the same gateway call returns a valid response from both providers with only the model-config string changed |

*All other phase behaviors (budget pre-check/breach, kill-switch trip/halt, cost computation, cache hit, ledger rows) have automated verification with mocked providers.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (unit conftest, live_llm marker)
- [ ] No watch-mode flags
- [ ] Feedback latency < 40s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
