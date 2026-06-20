"""Seeded-bug breakage detection — deterministic planted-spec proof (GEN-05b / D-08).

The breakage-detection half of the trust gate: the SAME PLANTED spec that passes N times vs the
standard SauceDemo build MUST FAIL against the seeded-bug build (saucedemo-bug, SEED_BUG=1 —
`.inventory_list` renamed to `.inventory_list_BROKEN`, so the post-login `.inventory_list`
success assertion can never resolve). NO gateway, NO provider keys — the planted spec proves the
whole mechanic.

Asserts:
  - run_seeded_bug repoints the SAME spec at SEEDED_BUG_BASE_URL (via the TARGET_BASE_URL env
    override the conftest reads) and the run FAILS -> detected_breakage is True;
  - accept_spec returns accepted=True ONLY when N-green-vs-standard AND red-vs-bug both hold;
  - a spec that is stable but does NOT fail vs the bug build is NOT accepted (a passing spec vs
    a broken target is not detecting breakage) — modelled by pointing the "bug" run at the
    STANDARD build, where the spec still passes, so detected_breakage is False.

REQUIRES the saucedemo-bug build up under the bugbuild profile:
  cd infra && docker compose --profile bugbuild up -d --wait saucedemo-bug
graph-marked (the surrounding tracer runs under graph_mode); per T-06-20 sequencing the RUN
phase needs NO neo4j — stop neo4j before this test so saucedemo + saucedemo-bug + Chromium fit
under the 3GB cap. The bug build is reached by its in-cluster compose name http://saucedemo-bug:80.

Subprocess discipline: stability.run_seeded_bug uses the SAME create_subprocess_exec argv-list,
no-shell, never-in-process runner as run_stability (T-06-18/T-06-19).
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

# Reuse the planted-spec renderer + plant helper from the stability proof (same planted spec).
from tests.functional.test_stability import (
    SAUCEDEMO_HOST_URL,
    _WORKSPACES_ROOT,
    _plant,
)

pytestmark = [pytest.mark.functional, pytest.mark.graph]

# Host-published port of the profile-gated seeded-bug build (distinct from saucedemo's 8080).
# In-cluster (container-driven) callers would use http://saucedemo-bug:80 instead.
SEEDED_BUG_HOST_URL = "http://localhost:8081"


async def test_planted_spec_fails_against_seeded_bug_build() -> None:
    """The SAME planted spec FAILS vs saucedemo-bug -> breakage detected (D-08)."""
    from app.services.stability import run_seeded_bug

    run_id = f"bug-{uuid.uuid4().hex}"
    spec_path = _plant(run_id)
    try:
        result = await run_seeded_bug(spec_path, base_url=SEEDED_BUG_HOST_URL)
        assert result["detected_breakage"] is True, (
            f"planted spec did NOT fail vs the seeded-bug build (no breakage detected): {result}"
        )
        assert result["exit_code"] not in (0, None)
        assert result["base_url"] == SEEDED_BUG_HOST_URL
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)


async def test_accept_spec_requires_green_vs_std_and_red_vs_bug() -> None:
    """accept_spec accepts ONLY when N-green-vs-standard AND red-vs-bug both hold (D-07+D-08)."""
    from app.services.stability import accept_spec

    run_id = f"acc-{uuid.uuid4().hex}"
    spec_path = _plant(run_id)
    try:
        # N green vs standard AND red vs the bug build -> accepted.
        result = await accept_spec(
            spec_path, runs=3, seeded_bug_base_url=SEEDED_BUG_HOST_URL
        )
        assert result["accepted"] is True, f"green-vs-std + red-vs-bug not accepted: {result}"
        assert result["stability"]["accepted"] is True
        assert result["seeded_bug"]["detected_breakage"] is True
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)


async def test_accept_spec_rejects_when_bug_run_still_passes() -> None:
    """A stable spec that does NOT fail vs the 'bug' target is NOT accepted (no breakage).

    Modelled by pointing the seeded-bug run at the STANDARD build, where the spec still passes —
    so detected_breakage is False and accept_spec must reject (a spec that passes vs the target
    it should detect breakage on is not a real-breakage detector).
    """
    from app.services.stability import accept_spec

    run_id = f"acc-no-bug-{uuid.uuid4().hex}"
    spec_path = _plant(run_id)
    try:
        result = await accept_spec(
            spec_path, runs=3, seeded_bug_base_url=SAUCEDEMO_HOST_URL
        )
        assert result["stability"]["accepted"] is True
        assert result["seeded_bug"]["detected_breakage"] is False
        assert result["accepted"] is False, (
            f"spec accepted despite NOT failing vs the bug target: {result}"
        )
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)
