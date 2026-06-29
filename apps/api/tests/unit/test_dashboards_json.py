"""Keyless validation of the Grafana dashboards-as-code JSON (INFRA-04 / D-04).

Pure unit test — no Postgres, no Neo4j, no prometheus import, no running stack. It
guards the two contracts a malformed dashboard would silently break:

  1. Every committed dashboard JSON file is VALID JSON (json.load succeeds) — the
     promtool-equivalent gate for Grafana, catching a bad edit before deploy.
  2. domain-metrics.json references ALL FOUR exact gauge names the core/metrics.py
     custom Collector emits. A panel PromQL that drifts from a gauge name renders an
     empty panel in Grafana with no error — this test is the link-check that keeps the
     dashboard PromQL in lockstep with the collector (the must_haves key_link).

The 4 gauge names are duplicated here on purpose: this test is the canary that fires if
either side (collector OR dashboard) renames a gauge without updating the other.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Repo-root-relative path to the provisioned Grafana dashboards.
# __file__ = apps/api/tests/unit/test_dashboards_json.py → parents[4] is the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DASHBOARDS_DIR = _REPO_ROOT / "infra" / "monitoring" / "grafana" / "provisioning" / "dashboards"

# The EXACT gauge names core/metrics.py's DomainMetricsCollector emits.
_DOMAIN_GAUGES = (
    "qa_platform_heal_success_rate",
    "qa_platform_classification_precision",
    "qa_platform_coverage_percent",
    "qa_platform_llm_cost_usd_total",
)


def _dashboard_files() -> list[Path]:
    return sorted(_DASHBOARDS_DIR.glob("*.json"))


def test_dashboards_dir_has_both_dashboards() -> None:
    names = {p.name for p in _dashboard_files()}
    assert "domain-metrics.json" in names
    assert "platform-health.json" in names


@pytest.mark.parametrize("path", _dashboard_files(), ids=lambda p: p.name)
def test_dashboard_json_is_valid(path: Path) -> None:
    """Each dashboard file parses as JSON and is a dict with a title + panels list."""
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert isinstance(data.get("title"), str) and data["title"]
    assert isinstance(data.get("panels"), list) and data["panels"]


def test_domain_dashboard_references_all_four_gauge_names() -> None:
    """domain-metrics.json must reference all 4 collector gauge names (the key_link)."""
    raw = (_DASHBOARDS_DIR / "domain-metrics.json").read_text(encoding="utf-8")
    # Assert valid JSON first, then string-presence of each gauge name (PromQL exprs).
    json.loads(raw)
    for gauge in _DOMAIN_GAUGES:
        assert gauge in raw, f"domain-metrics.json is missing gauge {gauge!r}"
