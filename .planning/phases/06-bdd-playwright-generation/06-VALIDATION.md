---
phase: 6
slug: bdd-playwright-generation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-20
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (pytest-asyncio 1.4, asyncio_mode=auto) + pytest-bdd 8.1 + pytest-playwright; frontend tsc/eslint/playwright |
| **Config file** | apps/api/pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `cd apps/api && uv run pytest -m "not live_llm and not graph and not e2e" -q` (lint gate, structured no-vacuous gate on a fixture KG, freehand-selector AST gate, review status transitions, Examples derivation, N-run harness on a planted spec — no keys, no neo4j) |
| **Full suite command** | `cd apps/api && uv run pytest -m "not live_llm" -q` (adds graph-marked codegen-reads-Element-Repository + seeded-bug harness under graph_mode) |
| **Frontend command** | `cd apps/web && npx tsc --noEmit && npx eslint <touched> && npx playwright test tests/e2e/review-queue.spec.ts` |
| **Estimated runtime** | ~3-4 min (N-run stability + seeded-bug subprocess runs add real wall time) |

---

## Sampling Rate

- **After every task commit:** `cd apps/api && uv run pytest -m "not live_llm and not graph and not e2e" -q`
- **After every plan wave:** full suite under graph_mode (`graph_mode up`; `docker compose stop neo4j` + restore web after)
- **Before `/gsd:verify-work`:** full suite green; the no-vacuous + freehand-selector gates green on fixtures; the N-run + seeded-bug harness green on a planted spec; live generate→review→codegen→stabilize demonstrated with provider keys
- **Max feedback latency:** ~4 min

---

## Per-Task Verification Map

> Populated by the planner. Each task maps to GEN-01..05, a test type (unit deterministic / graph
> functional under graph_mode / live_llm-manual), a threat ref, and a command. The lint gate, the
> structured no-vacuous gate (fixture KG), the freehand-selector AST gate, review status transitions,
> Examples derivation, the N-run harness + seeded-bug pass/fail (planted spec) are ALL deterministic
> WITHOUT keys; the live generate→review→codegen→stabilize chain is Manual-Only.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _planner fills_ | | | GEN-0x | | | unit/graph/live_llm | | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Fixture KG (reuse/extend Phase-5 fixtures) + a fixture scenarios set with then_refs (resolvable + vacuous cases) so the no-vacuous gate is unit-testable WITHOUT neo4j/keys
- [ ] Planted template-rendered spec (reuse Phase-3 test_login.py.j2 path) for the deterministic N-run + seeded-bug harness proof (passes N× vs SauceDemo, fails vs the bug build) — no keys
- [ ] Seeded-bug SauceDemo build (compose service/profile via build-arg on the existing Dockerfile; one injected defect) + addressing (distinct service/port)
- [ ] Mocked gateway fixture (carried from Phase 2) for generation-logic tests with the deterministic no-key fallback
- [ ] scenarios table + migration 0006 (chains after 0005); review router test scaffolding
- [ ] graph_mode + neo4j_session fixture (carried) for graph-marked codegen tests; OOM mitigation note (codegen under graph_mode, stop neo4j before the run phase)

*Existing functional infra (live-HTTP client, authed_client, poll_until_terminal, asyncio_mode=auto) carries forward.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live generate → review → approve → codegen → stabilize | GEN-01..05 | LLM generation (real spend) + a real explored graph | Set keys, explore SauceDemo (graph_mode), generate scenarios, approve in the review UI, generate Playwright, run the N-run stability check, then run vs the seeded-bug build and confirm FAILURE |
| Live scenario quality (outlines + Examples, non-vacuous) | GEN-01/03 | LLM output quality | After generation, inspect scenarios: outlines have Examples; every Then has a resolvable KG ref (gate green); deterministic fallback scenarios appear without keys |
| Memory fit: neo4j + SauceDemo + seeded-bug + Chromium under 3GB | (infra) | host Vmmem observation | Run the seeded-bug harness; `docker stats` under cap; codegen under graph_mode then stop neo4j before the run phase |

*Deterministic logic (lint, structured no-vacuous gate, freehand-selector AST gate, review transitions, Examples derivation, N-run + seeded-bug harness on a planted spec) is automated without keys.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (fixture scenarios/then_refs, planted spec, seeded-bug build, scenarios migration)
- [ ] No watch-mode flags
- [ ] Feedback latency < 4 min
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
