"""Determinism harness — two runs vs a RESET target produce identical results (SC5, keyless).

Proves SC5: running the SAME planted spec TWICE against a freshly-RESET SauceDemo target yields
IDENTICAL results on the comparable surface (exit_code / passed / derived verdict) — NOT on
timing, timestamps, or durations (RESEARCH Pitfall 6: those are EXPECTED to differ between runs
and must NEVER be compared). This is the engine-determinism half of local/Docker/CI parity: the
same engine, run twice, against the same reset state, is reproducible.

KEYLESS + GRAPH-OFF (RESEARCH D-03b / Phase-6 sequencing): this reuses the Phase-6 PLANTED spec
(the retained app/templates/test_login.py.j2 rendered with FIXED observed SauceDemo slots,
TARGET_BASE_URL-overridable) so there is NO gateway call, NO provider key, and NO neo4j needed —
the spec is already materialized on disk and the RUN phase reads no graph (neo4j stays OFF during
the run phase, mirroring the Phase-6 codegen->stop-neo4j->run sequencing).

RESET BETWEEN RUNS: `infra/scripts/reset_target.py saucedemo` is invoked between the two runs
(subprocess, argv list, honoring its exit-code contract: 0 success / 1 strategy-or-health failure
/ 2 unknown name). SauceDemo's mutable state lives in browser localStorage, so each fresh
Playwright context already isolates a run (reset_target.py's own honesty note); the explicit reset
is the documented determinism control and is exercised here so the two-runs proof consumes the
Phase-1 reset contract directly.

SUBPROCESS DISCIPLINE: the two SPEC runs go through stability._run_spec_once VERBATIM (argv LIST,
no shell, never in-process — T-06-18/T-06-19). This test does NOT re-implement the spec runner —
it reuses the battle-tested primitive. The ONLY direct subprocess here is the reset_target.py
invocation (also an argv LIST, never shell=True), which is the Phase-1 reset contract, not a
second test runner.

REQUIRES SauceDemo up on its host-published port (localhost:8080):
  cd infra && docker compose up -d --wait saucedemo
The reset uses the host `docker compose` via the script's own argv. neo4j and provider keys are
NOT required.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import uuid
from pathlib import Path

import pytest

# Reuse the planted-spec plant helper + workspaces root from the stability proof (SAME planted
# spec — the retained test_login.py.j2 with fixed SauceDemo slots, TARGET_BASE_URL-overridable).
from tests.functional.test_stability import (
    SAUCEDEMO_HOST_URL,
    _WORKSPACES_ROOT,
    _plant,
)

pytestmark = [pytest.mark.functional]

# reset_target.py lives at infra/scripts/; resolve it from the repo root.
# test_determinism.py -> functional -> tests -> api -> apps -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_RESET_SCRIPT = _REPO_ROOT / "infra" / "scripts" / "reset_target.py"


async def _reset_saucedemo() -> int:
    """Invoke `reset_target.py saucedemo` (argv LIST, no shell); return its exit code.

    Honors the script's exit-code contract (0 success / 1 strategy-or-health failure / 2 unknown
    name). Stdlib-only script, so it runs under the host's plain Python interpreter.
    """
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(_RESET_SCRIPT),
        "saucedemo",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0:
        # Surface the reset output so a determinism failure rooted in the reset is diagnosable.
        print((out or b"").decode(errors="replace"))
    return proc.returncode if proc.returncode is not None else 1


def _derive_verdict(result: dict) -> str:
    """The comparable single-attempt verdict (mirrors the Plan-01 thin shape).

    Deliberately derived ONLY from the run's exit_code/passed — NEVER from timing/duration/
    timestamps (Pitfall 6: those differ between runs and are not part of the determinism claim).
    """
    return "passed" if result["passed"] else "product_failure"


async def test_two_runs_vs_reset_target_are_identical_keyless() -> None:
    """Two consecutive planted-spec runs against a reset SauceDemo are identical (status+verdict).

    Run the SAME planted spec twice via _run_spec_once (the reused subprocess primitive), calling
    reset_target.py saucedemo BETWEEN the two runs so target state is identical. Assert the two
    runs match on exit_code / passed / derived verdict — and EXCLUDE timing/timestamps/durations
    (Pitfall 6). Keyless: planted spec, no gateway, no neo4j.
    """
    from app.services.stability import _run_spec_once

    run_id = f"determinism-{uuid.uuid4().hex}"
    spec_path = _plant(run_id)  # render the planted spec at workspaces/<run_id>/test_login.py
    try:
        # Run 1 against a freshly reset target.
        assert await _reset_saucedemo() == 0, "reset_target.py saucedemo failed before run 1"
        first = await _run_spec_once(str(spec_path), base_url=SAUCEDEMO_HOST_URL)

        # Reset BETWEEN runs so run 2 sees identical target state (the determinism control).
        assert await _reset_saucedemo() == 0, "reset_target.py saucedemo failed between runs"
        second = await _run_spec_once(str(spec_path), base_url=SAUCEDEMO_HOST_URL)

        # Both runs must be green (the planted spec passes vs standard SauceDemo) AND identical on
        # the COMPARABLE surface only.
        assert first["passed"] is True, f"run 1 not green: {first['output'][-1000:]}"
        assert second["passed"] is True, f"run 2 not green: {second['output'][-1000:]}"

        # IDENTICAL on status + verdict — exit_code, passed, and the derived verdict.
        assert first["exit_code"] == second["exit_code"], (
            f"exit codes differ across runs: {first['exit_code']} vs {second['exit_code']}"
        )
        assert first["passed"] == second["passed"], "passed flags differ across runs"
        assert _derive_verdict(first) == _derive_verdict(second), "derived verdicts differ"

        # The comparison EXCLUDES timing/timestamps/durations (Pitfall 6): we never read a
        # duration/timestamp key off the result, and _run_spec_once returns none — asserting the
        # comparable surface is exactly {exit_code, passed} keeps the proof timing-independent.
        assert set(first) == {"passed", "exit_code", "output"}, (
            "unexpected result keys — the comparison must stay on status/verdict, not timing"
        )
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)
