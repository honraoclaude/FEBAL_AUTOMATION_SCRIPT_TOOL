---
phase: 1
slug: foundation-dev-environment
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-12
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.x + pytest-asyncio 1.4.x (`asyncio_mode = "auto"`) + httpx 0.28 (API functional) + pytest-playwright 0.8 / Playwright 1.60 (UI functional) |
| **Config file** | none — Wave 0 installs (`apps/api/pyproject.toml [tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/functional -x -q` (from `apps/api`, stack running) |
| **Full suite command** | `docker compose -f infra/docker-compose.yml up -d --wait && uv run pytest tests -q` |
| **Estimated runtime** | quick: seconds against running stack; full: ~2-5 min including e2e |

D-02 mandate: tests are *functional* — they hit the running app over HTTP with real Postgres (no ASGITransport in-process shortcut, no DB mocking). UI tests run Playwright on the host against `http://localhost:3000`.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/functional -x -q`
- **After every plan wave:** Run full suite incl. e2e + smoke scripts
- **Before `/gsd:verify-work`:** Full suite must be green on a clean-state run (`docker compose down -v && docker compose up -d --wait` then full suite, then `verify_stack.py`)
- **Max feedback latency:** ~60 seconds (quick functional run)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-03-T1/T2 | 01-03 | 3 | PLAT-03 | V2/V3 | Login sets httpOnly cookies; bad password 401; refresh rotates; logout clears; uniform 401 (no user enumeration) | functional | `uv run pytest tests/functional/test_auth.py -x` | ❌ W0 | ⬜ pending |
| 01-04-T3 | 01-04 | 4 | PLAT-03 | V3 | UI: login form → /targets; unauthenticated /targets → /login | e2e | `uv run pytest tests/e2e/test_login_ui.py -x` | ❌ W0 | ⬜ pending |
| 01-05-T1/T2 | 01-05 | 4 | PLAT-01 | V5 | Register/edit/soft-delete target via API; defaults applied (allowlist=origin, sandbox=false) | functional | `uv run pytest tests/functional/test_targets.py -x` | ❌ W0 | ⬜ pending |
| 01-06-T3 | 01-06 | 5 | PLAT-01 | V5 | UI: register target via dialog, appears in table, credentials masked | e2e | `uv run pytest tests/e2e/test_targets_ui.py -x` | ❌ W0 | ⬜ pending |
| 01-05-T1/T2 | 01-05 | 4 | PLAT-07 | V6 / Info Disclosure | No plaintext password in any API response; DB column is Fernet ciphertext (round-trip); captured logs contain no plaintext | functional | `uv run pytest tests/functional/test_credential_security.py -x` | ❌ W0 | ⬜ pending |
| 01-08-T1/T2 | 01-08 | 6 | INFRA-01 | — | All default services healthy; dormant services absent; every container has non-zero memory limit | smoke | `python infra/scripts/verify_stack.py` | ❌ W0 | ⬜ pending |
| 01-07-T2 | 01-07 | 5 | QUAL-04 | — | SauceDemo serves 200; `reset_target.py saucedemo` exits 0 and target healthy after | smoke | `uv run pytest tests/functional/test_reset_target.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*(Task IDs filled by planner — map rows to tasks in PLAN.md files.)*

---

## Wave 0 Requirements

- [ ] `apps/api/pyproject.toml` — pytest config (`asyncio_mode = "auto"`, markers `functional`, `e2e`)
- [ ] `apps/api/tests/conftest.py` — base URLs from env, authed-client fixture, table-truncate fixture
- [ ] `tests/functional/test_auth.py`, `test_targets.py`, `test_credential_security.py`, `test_reset_target.py` — written alongside their features (D-02), files created in each slice
- [ ] `tests/e2e/` Playwright tests + `uv run playwright install chromium` (one-time)
- [ ] `infra/scripts/verify_stack.py` — INFRA-01 evidence script

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `.wslconfig` applied (Vmmem bounded) | INFRA-01 | Host-level, not CI-able | After `wsl --shutdown` + Docker Desktop restart, observe Vmmem memory bounded in Task Manager |
| Stack healthy after Windows reboot | INFRA-01 | Host-level ("Looks Done But Isn't") | Reboot, start Docker Desktop, `docker compose up -d --wait`, run `verify_stack.py` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
