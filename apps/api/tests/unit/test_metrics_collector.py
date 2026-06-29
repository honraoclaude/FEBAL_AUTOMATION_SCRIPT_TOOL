"""DomainMetricsCollector unit proof (INFRA-04) — pure, keyless, no DB.

The collector is the SYNC sync-over-async bridge's read side: it reads the module-global
_snapshot floats O(1) and yields one GaugeMetricFamily per non-None metric. It NEVER touches
the DB on the scrape path (T-11-02) and NEVER raises when a source is down — a None snapshot key
OMITS its gauge (honest absence, D-05 — never a fake 0).

These tests poke _snapshot directly (the refresh loop is exercised by the integration test over a
real Postgres) so they stay keyless and run on the default lane.

Run: cd apps/api && uv run python -m pytest tests/unit/test_metrics_collector.py -q
"""

from __future__ import annotations

import pytest

from app.core import metrics

_GAUGES = {
    "qa_platform_heal_success_rate": "heal_success_rate",
    "qa_platform_classification_precision": "classification_precision",
    "qa_platform_coverage_percent": "coverage_percent",
    "qa_platform_llm_cost_usd_total": "llm_cost_usd_total",
}


@pytest.fixture(autouse=True)
def _reset_snapshot():
    """Each test owns the snapshot — restore the all-None initial state afterward."""
    saved = dict(metrics._snapshot)
    yield
    metrics._snapshot.clear()
    metrics._snapshot.update(saved)


def _collect_by_name() -> dict[str, float]:
    families = list(metrics.DomainMetricsCollector().collect())
    return {f.name: f.samples[0].value for f in families}


def test_collect_yields_all_four_gauges_from_a_populated_snapshot() -> None:
    metrics._snapshot.update(
        heal_success_rate=0.92,
        classification_precision=0.85,
        coverage_percent=42.5,
        llm_cost_usd_total=12.34,
    )

    families = list(metrics.DomainMetricsCollector().collect())
    assert len(families) == 4
    by_name = {f.name: f.samples[0].value for f in families}
    assert by_name == {
        "qa_platform_heal_success_rate": 0.92,
        "qa_platform_classification_precision": 0.85,
        "qa_platform_coverage_percent": 42.5,
        "qa_platform_llm_cost_usd_total": 12.34,
    }


def test_collect_omits_a_none_gauge_and_never_raises() -> None:
    # A down source sets its key None — its gauge must NOT be yielded (never a fake 0).
    metrics._snapshot.update(
        heal_success_rate=None,
        classification_precision=0.7,
        coverage_percent=None,
        llm_cost_usd_total=0.0,  # a real $0 IS a value — it must still be emitted
    )

    by_name = _collect_by_name()
    assert "qa_platform_heal_success_rate" not in by_name
    assert "qa_platform_coverage_percent" not in by_name
    assert by_name["qa_platform_classification_precision"] == 0.7
    # $0.0 is a real measurement, not a missing source — it is emitted.
    assert by_name["qa_platform_llm_cost_usd_total"] == 0.0


def test_collect_with_all_none_yields_nothing() -> None:
    for key in _GAUGES.values():
        metrics._snapshot[key] = None
    assert list(metrics.DomainMetricsCollector().collect()) == []
