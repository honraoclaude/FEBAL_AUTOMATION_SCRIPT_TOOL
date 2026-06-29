"""GET /metrics integration proof (INFRA-04) — real Postgres, keyless graph.

The test_dashboards discipline (in-process over the real app + real Postgres via SessionLocal; no
running HTTP stack). It seeds the 4 metric SOURCES, runs the refresh ONCE over a real session
(metrics._refresh_once), then scrapes GET /metrics through ASGITransport and asserts the Prometheus
text body carries the 4 gauges with the computed values.

coverage mines the graph — monkeypatched keyless (the test_dashboards _patch_mine precedent). One
test also asserts /metrics stays 200 when a source is DOWN (T-11-03 graceful degrade) — a missing
source omits its gauge but never 500s the scrape.

Run: cd apps/api && uv run python -m pytest tests/integration/test_metrics_endpoint.py -q
"""

from __future__ import annotations

import uuid

import asyncpg
import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

pytestmark = [pytest.mark.integration]

_loop_module = pytest.mark.asyncio(loop_scope="module")


def _host_dsn() -> str:
    from app.core.config import settings

    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


async def _delete_run(run_id: str) -> None:
    conn = await asyncpg.connect(_host_dsn())
    try:
        for tbl in ("heal_audit", "defects", "llm_usage"):
            await conn.execute(f"DELETE FROM {tbl} WHERE run_id = $1", run_id)
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def _reset_engine_pool():
    from app.db.session import engine

    await engine.dispose()
    yield
    await engine.dispose()


def _patch_mine(monkeypatch, n_flows: int = 0) -> None:
    """Keep the coverage source keyless — fake the graph mine (test_dashboards precedent)."""
    from app.services import coverage_dash

    async def _fake_mine(driver=None):  # noqa: ANN001, ARG001
        return {"flows": [{"id": f"flow-{i}"} for i in range(n_flows)], "bounded": True}

    monkeypatch.setattr(coverage_dash, "mine_flows_from_neo4j", _fake_mine)


async def _seed(run_id: str, *, applied: int, rejected: int) -> None:
    """Seed the 4 metric sources for one run: heal_audit, defects, llm_usage."""
    from app.db.session import SessionLocal
    from app.models.defects import Defect
    from app.models.heal_audit import HealAudit
    from app.models.llm_usage import LLMUsage

    async with SessionLocal() as db:
        # heal_audit: 3 auto_heal (landed) + 1 fail_as_defect over one element → success 3/4 = 0.75
        for _ in range(3):
            db.add(HealAudit(element_key="btn", run_id=run_id, flow_id="flow-0",
                             before_chain=[], after_chain=[{"strategy": "css", "value": "#a"}],
                             confidence=0.9, outcome="auto_heal", live_match_count=1))
        db.add(HealAudit(element_key="btn", run_id=run_id, flow_id="flow-0",
                         before_chain=[], after_chain=None,
                         confidence=0.1, outcome="fail_as_defect", live_match_count=0))
        # defects: `applied` + `rejected` reviewed rows → precision = applied/(applied+rejected)
        for _ in range(applied):
            db.add(Defect(run_id=run_id, flow_id="flow-0", classification="product_defect",
                          confidence=90, fingerprint="fp", jira_label="fp", status="applied"))
        for _ in range(rejected):
            db.add(Defect(run_id=run_id, flow_id="flow-1", classification="automation",
                          confidence=50, fingerprint="fp2", jira_label="fp2", status="rejected"))
        # a draft defect must NOT count toward precision (neither applied nor rejected)
        db.add(Defect(run_id=run_id, flow_id="flow-2", classification="infrastructure",
                      confidence=30, fingerprint="fp3", jira_label="fp3", status="draft"))
        # llm_usage: two rows → total cost 1.5 + 2.25 = 3.75
        db.add(LLMUsage(run_id=run_id, operation_type="explore", provider="anthropic",
                        model="claude", input_tokens=10, output_tokens=5, cost_usd=1.5))
        db.add(LLMUsage(run_id=run_id, operation_type="generate", provider="anthropic",
                        model="claude", input_tokens=20, output_tokens=8, cost_usd=2.25))
        await db.commit()


async def _scrape() -> httpx.Response:
    from app.main import app

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get("/metrics")


@_loop_module
async def test_metrics_endpoint_exposes_the_four_gauges(monkeypatch) -> None:
    from app.core import metrics

    _patch_mine(monkeypatch, 0)  # coverage source up but 0 flows → coverage_percent 0.0 (a value)
    run_id = f"metrics-{uuid.uuid4().hex}"
    try:
        await _seed(run_id, applied=3, rejected=1)  # precision = 3/4 = 0.75
        await metrics._refresh_once()  # populate the snapshot from real Postgres

        resp = await _scrape()
        assert resp.status_code == 200
        body = resp.text
        for name in (
            "qa_platform_heal_success_rate",
            "qa_platform_classification_precision",
            "qa_platform_coverage_percent",
            "qa_platform_llm_cost_usd_total",
        ):
            assert name in body, f"{name} missing from /metrics body"

        samples = {
            line.split(" ")[0]: float(line.split(" ")[1])
            for line in body.splitlines()
            if line and not line.startswith("#")
        }
        assert samples["qa_platform_heal_success_rate"] == pytest.approx(0.75)
        assert samples["qa_platform_classification_precision"] == pytest.approx(0.75)
        assert samples["qa_platform_llm_cost_usd_total"] == pytest.approx(3.75)
    finally:
        await _delete_run(run_id)


@_loop_module
async def test_zero_reviewed_omits_classification_precision(monkeypatch) -> None:
    """D-05 honest absence: zero applied+rejected defects → the precision gauge is ABSENT."""
    from app.core import metrics

    _patch_mine(monkeypatch, 0)
    run_id = f"metrics-{uuid.uuid4().hex}"
    try:
        await _seed(run_id, applied=0, rejected=0)  # only a draft defect — nothing reviewed
        await metrics._refresh_once()

        resp = await _scrape()
        assert resp.status_code == 200
        assert "qa_platform_classification_precision" not in resp.text
    finally:
        await _delete_run(run_id)


@_loop_module
async def test_metrics_stays_200_when_a_source_is_down(monkeypatch) -> None:
    """T-11-03: a source raising during refresh sets its key None — /metrics still 200, gauge absent."""
    from app.core import metrics
    from app.services import coverage_dash

    _patch_mine(monkeypatch, 0)

    async def _boom(driver=None):  # noqa: ANN001, ARG001
        raise RuntimeError("coverage source down")

    monkeypatch.setattr(coverage_dash, "coverage", _boom)
    run_id = f"metrics-{uuid.uuid4().hex}"
    try:
        await _seed(run_id, applied=1, rejected=1)
        await metrics._refresh_once()  # coverage raises internally → key None, never propagates

        resp = await _scrape()
        assert resp.status_code == 200
        assert "qa_platform_coverage_percent" not in resp.text
        # the other sources still resolved
        assert "qa_platform_llm_cost_usd_total" in resp.text
    finally:
        await _delete_run(run_id)
