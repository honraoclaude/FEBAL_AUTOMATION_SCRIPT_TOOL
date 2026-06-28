"""Autonomy gate truth table (JIRA-02 / D-04) — the CORE safety property, keyless.

`may_autofile(conf)` is a PURE structural gate over the SHIPPED settings (never a literal):

    may_autofile = settings.jira_autonomous_enabled AND conf >= settings.jira_confidence_threshold

The truth table this pins (T-09-12 — the elevation-of-privilege mitigation):

  - flag OFF  -> NEVER files, even at conf 100 (autonomy is OFF by default — D-04);
  - flag ON + below the calibrated threshold -> NEVER files;
  - flag ON + AT/above the calibrated threshold -> MAY file.

The threshold is read from settings.jira_confidence_threshold (calibrated by QUAL-03 in Plan
02), never a hardcoded number — proven by driving the gate against monkeypatched settings.

Run: cd apps/api && uv run python -m pytest tests/unit/test_autonomy_gate.py -q
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.defects.autonomy import may_autofile


@pytest.fixture
def _gate(monkeypatch):
    """A helper to set the flag + threshold on the SHIPPED settings singleton per-test."""

    def _set(*, enabled: bool, threshold: int) -> None:
        monkeypatch.setattr(settings, "jira_autonomous_enabled", enabled)
        monkeypatch.setattr(settings, "jira_confidence_threshold", threshold)

    return _set


def test_flag_off_never_files_even_at_full_confidence(_gate) -> None:
    """Flag OFF -> False at ANY confidence (autonomy OFF by default — D-04)."""
    _gate(enabled=False, threshold=70)
    assert may_autofile(100) is False
    assert may_autofile(70) is False
    assert may_autofile(0) is False


def test_flag_on_below_threshold_never_files(_gate) -> None:
    """Flag ON but below the calibrated threshold -> False (the threshold half of the gate)."""
    _gate(enabled=True, threshold=70)
    assert may_autofile(69) is False
    assert may_autofile(0) is False


def test_flag_on_at_or_above_threshold_files(_gate) -> None:
    """Flag ON AND at/above the calibrated threshold -> True (the only filing path)."""
    _gate(enabled=True, threshold=70)
    assert may_autofile(70) is True  # boundary: AT the threshold files
    assert may_autofile(100) is True


def test_gate_reads_the_calibrated_threshold_not_a_literal(_gate) -> None:
    """The cutoff tracks settings.jira_confidence_threshold (calibrated) — never a hardcoded 70."""
    _gate(enabled=True, threshold=90)
    assert may_autofile(80) is False  # 80 < 90 -> below the (raised) calibrated floor
    assert may_autofile(90) is True
