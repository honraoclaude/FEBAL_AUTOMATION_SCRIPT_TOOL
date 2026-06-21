"""Risk-based dynamic tier ranking (EXEC-01 / D-02) — pure formula over build_flows output.

rank_risk_flows RANKS the build_flows RECORD LIST (each record already carries the real graph
`risk_score`/`risk_tier`/`id` — NOT a bare risk_score() call) combined with recent failure
history, and returns the top-N by the frozen-weight weighted sum. These tests monkeypatch
`_load_flow_risk` (the bounded graph read) and `failure_rate` (the history read) so NO graph and
NO db are touched — proving the ranking is pure math over the build_flows records:

    combined = risk_weight * record["risk_score"] + failure_weight * failure_rate * 100

Cold start (no history → failure_rate all-zero) → ranking is pure build_flows risk order.
neo4j down (`_load_flow_risk` → []) → empty ranking, no hang.
"""

from __future__ import annotations

import pytest

from app.services import exec_service
from app.services.exec_service import RiskRankWeights, rank_risk_flows


def _records() -> list[dict]:
    """A FABRICATED build_flows record list (each carries the real-graph risk_score shape)."""
    return [
        {"id": "flow-0", "risk_score": 80, "risk_tier": "high"},
        {"id": "flow-1", "risk_score": 20, "risk_tier": "low"},
        {"id": "flow-2", "risk_score": 50, "risk_tier": "medium"},
    ]


@pytest.fixture
def patched(monkeypatch):
    """Default patch: a fixed record list + a fixed failure-rate dict (no graph, no db)."""

    async def _fake_load() -> list[dict]:
        return _records()

    async def _fake_failure(db, flow_ids, *, last_k=10) -> dict[str, float]:
        return {"flow-0": 0.0, "flow-1": 1.0, "flow-2": 0.0}

    monkeypatch.setattr(exec_service, "_load_flow_risk", _fake_load)
    monkeypatch.setattr(exec_service, "failure_rate", _fake_failure)


async def test_ranks_by_weighted_sum_of_graph_risk_plus_failure(patched) -> None:
    # combined = 0.6*risk + 0.4*failure_rate*100:
    #   flow-0: 0.6*80 + 0.4*0*100   = 48
    #   flow-1: 0.6*20 + 0.4*1.0*100 = 12 + 40 = 52
    #   flow-2: 0.6*50 + 0.4*0*100   = 30
    ranked = await rank_risk_flows(db=None)
    ids = [r["id"] for r in ranked]
    assert ids == ["flow-1", "flow-0", "flow-2"]


async def test_each_entry_carries_id_and_spec_path(patched) -> None:
    ranked = await rank_risk_flows(db=None)
    for entry in ranked:
        assert "id" in entry
        assert "spec_path" in entry and entry["spec_path"]
        assert "combined" in entry


async def test_top_n_truncates(monkeypatch) -> None:
    async def _fake_load() -> list[dict]:
        return [{"id": f"flow-{i}", "risk_score": i, "risk_tier": "low"} for i in range(50)]

    async def _fake_failure(db, flow_ids, *, last_k=10) -> dict[str, float]:
        return {}

    monkeypatch.setattr(exec_service, "_load_flow_risk", _fake_load)
    monkeypatch.setattr(exec_service, "failure_rate", _fake_failure)

    ranked = await rank_risk_flows(db=None, weights=RiskRankWeights())
    assert len(ranked) == RiskRankWeights().top_n == 10
    # Highest risk_score (49) first.
    assert ranked[0]["id"] == "flow-49"


async def test_cold_start_is_pure_build_flows_risk_order(monkeypatch) -> None:
    async def _fake_load() -> list[dict]:
        return _records()

    async def _fake_failure(db, flow_ids, *, last_k=10) -> dict[str, float]:
        return {}  # no history → every failure_rate defaults to 0.0

    monkeypatch.setattr(exec_service, "_load_flow_risk", _fake_load)
    monkeypatch.setattr(exec_service, "failure_rate", _fake_failure)

    ranked = await rank_risk_flows(db=None)
    # With failure_rate all-zero the order is pure risk_score desc: 80, 50, 20.
    assert [r["id"] for r in ranked] == ["flow-0", "flow-2", "flow-1"]


async def test_neo4j_down_yields_empty_ranking_no_hang(monkeypatch) -> None:
    async def _fake_load() -> list[dict]:
        return []  # _load_flow_risk's honest-empty on graph down/slow/not-discovered

    async def _fake_failure(db, flow_ids, *, last_k=10) -> dict[str, float]:
        return {}

    monkeypatch.setattr(exec_service, "_load_flow_risk", _fake_load)
    monkeypatch.setattr(exec_service, "failure_rate", _fake_failure)

    ranked = await rank_risk_flows(db=None)
    assert ranked == []


def test_frozen_weights_are_the_assumed_starting_point() -> None:
    w = RiskRankWeights()
    assert w.risk_weight == 0.6
    assert w.failure_weight == 0.4
    assert w.top_n == 10
    with pytest.raises(Exception):
        w.risk_weight = 0.9  # frozen — cannot mutate under callers
