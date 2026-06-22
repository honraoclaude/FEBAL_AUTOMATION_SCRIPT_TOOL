"""reconcile_verdict table tests (HEAL-02 / Pitfall 4) — a heal is NOT a flake.

The journal-driven verdict override sits next to `classify_retry` and is PURE (no I/O, stdlib
only, table-testable). A journal'd `auto_heal` overrides `passed`/`flaky` -> `auto_healed`; a
`quarantine` -> `quarantined`; a `fail_as_defect` -> `product_failure`; no journal events leave
the exit verdict unchanged. The verdicts are ADDITIVE to the String(16) verdict column (no schema
change, RESEARCH A5).
"""

from __future__ import annotations

import pytest

from app.services.worker.classifier import reconcile_verdict


@pytest.mark.parametrize(
    ("exit_verdict", "events", "expected"),
    [
        # auto_heal overrides any exit verdict (a heal is NOT a flake).
        ("passed", [{"outcome": "auto_heal"}], "auto_healed"),
        ("flaky", [{"outcome": "auto_heal"}], "auto_healed"),
        ("product_failure", [{"outcome": "auto_heal"}], "auto_healed"),
        # quarantine -> quarantined.
        ("product_failure", [{"outcome": "quarantine"}], "quarantined"),
        ("passed", [{"outcome": "quarantine"}], "quarantined"),
        # fail_as_defect -> product_failure (feeds Phase 9).
        ("product_failure", [{"outcome": "fail_as_defect"}], "product_failure"),
        ("passed", [{"outcome": "fail_as_defect"}], "product_failure"),
        # no journal events -> exit verdict unchanged.
        ("passed", [], "passed"),
        ("flaky", [], "flaky"),
        ("product_failure", [], "product_failure"),
        # None journal -> unchanged (defensive).
        ("passed", None, "passed"),
    ],
)
def test_reconcile_verdict_table(exit_verdict, events, expected) -> None:
    assert reconcile_verdict(exit_verdict, events) == expected


def test_auto_heal_precedence_over_quarantine_and_fail() -> None:
    """When a flow records multiple outcomes, auto_heal wins, then quarantine, then fail."""
    events = [
        {"outcome": "fail_as_defect"},
        {"outcome": "quarantine"},
        {"outcome": "auto_heal"},
    ]
    assert reconcile_verdict("flaky", events) == "auto_healed"


def test_quarantine_precedence_over_fail() -> None:
    events = [{"outcome": "fail_as_defect"}, {"outcome": "quarantine"}]
    assert reconcile_verdict("product_failure", events) == "quarantined"


def test_malformed_events_are_ignored() -> None:
    """Non-dict / unknown-outcome events never crash and never spuriously override."""
    events = ["nope", 42, {"no_outcome_key": 1}, {"outcome": "unknown"}]
    assert reconcile_verdict("passed", events) == "passed"
