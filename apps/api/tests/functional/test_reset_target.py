"""QUAL-04 smoke tests for the SauceDemo target + reset-target contract.

VALIDATION row QUAL-04 → task 01-07-T2. These are functional tests (D-02): they
hit the RUNNING compose stack and invoke the real reset script as a subprocess.
"""

import subprocess
import sys
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.functional

# Repo root is four parents up from apps/api/tests/functional/this_file.py.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_RESET_SCRIPT = _REPO_ROOT / "infra" / "scripts" / "reset_target.py"
_SAUCEDEMO_URL = "http://localhost:8080"


def test_saucedemo_serves_200() -> None:
    """The self-hosted SauceDemo target serves its SPA shell with HTTP 200."""
    resp = httpx.get(_SAUCEDEMO_URL, timeout=10)
    assert resp.status_code == 200


def test_reset_target_exits_zero_and_target_healthy() -> None:
    """`reset_target.py saucedemo` exits 0 and the target is healthy right after."""
    result = subprocess.run(
        [sys.executable, str(_RESET_SCRIPT), "saucedemo"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"reset failed (exit {result.returncode}): "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    # Immediately after a successful reset the target answers 200.
    resp = httpx.get(_SAUCEDEMO_URL, timeout=10)
    assert resp.status_code == 200


def test_reset_target_unknown_name_fails() -> None:
    """An unknown target exits 2 and names the known targets in its output."""
    result = subprocess.run(
        [sys.executable, str(_RESET_SCRIPT), "nonexistent"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    combined = (result.stdout + result.stderr).lower()
    assert "saucedemo" in combined, combined
