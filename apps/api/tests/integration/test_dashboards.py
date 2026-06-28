"""Dashboard aggregation + role-gate proof (DASH-01/02/03 + the 403 matrix).

Two layers, the test_defects_router / test_role_assign discipline (in-process over the real app +
real Postgres via SessionLocal; no running HTTP stack):

  - test_dashboards_aggregates: seeds runs/scenarios/results/defects/classifications and calls the
    dashboards.{executive,qa,developer} SERVICE functions directly, asserting the UI-SPEC shapes —
    coverage + pass-rate + defect trends + KPIs (exec); run history + failed tests + RUN-RELATIVE
    artifact refs (qa); root-cause groupings + error trend + module breakdown (dev); and that empty
    data yields honest empty aggregates.
  - the role matrix (Task 3): GET /api/dashboards/{executive,qa,developer} + /api/coverage/flows
    reachable only by the permitted roles (403 otherwise), 401 unauthenticated.

coverage relies on the graph mine; here it is monkeypatched (keyless). The verdict vocabulary is
passed | flaky | product_failure | aborted — there is NO 'failed' verdict (CHECKER LOW-1); failed
tests = verdict IN (product_failure, aborted).

Run: cd apps/api && uv run python -m pytest tests/integration/test_dashboards.py -x -q
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
        for tbl in ("scenarios", "test_results", "test_runs", "test_artifacts",
                    "classifications", "defects"):
            await conn.execute(f"DELETE FROM {tbl} WHERE run_id = $1", run_id)
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def _reset_engine_pool():
    from app.db.session import engine

    await engine.dispose()
    yield
    await engine.dispose()


async def _seed(run_id: str) -> None:
    """Seed a full lifecycle slice for ONE run: 3 flows with assorted verdicts + a defect."""
    from app.db.session import SessionLocal
    from app.models.defects import Classification, Defect
    from app.models.execution_history import TestArtifact, TestResult, TestRun
    from app.models.scenario import Scenario

    async with SessionLocal() as db:
        db.add(TestRun(run_id=run_id, tier="regression", status="failed",
                       total=3, passed=1, failed=1, flaky=1))
        # flow-0 approved+passing (covered), flow-1 approved+product_failure, flow-2 flaky
        db.add(Scenario(run_id=run_id, flow_id="flow-0", feature_name="f0",
                        gherkin_text="x", then_refs=[], status="approved"))
        db.add(Scenario(run_id=run_id, flow_id="flow-1", feature_name="f1",
                        gherkin_text="x", then_refs=[], status="approved"))
        db.add(TestResult(run_id=run_id, flow_id="flow-0", verdict="passed",
                          attempts=1, exit_codes=[0], duration_ms=10))
        db.add(TestResult(run_id=run_id, flow_id="flow-1", verdict="product_failure",
                          attempts=2, exit_codes=[1, 1], duration_ms=20,
                          error_text="AssertionError: boom"))
        db.add(TestResult(run_id=run_id, flow_id="flow-2", verdict="flaky",
                          attempts=2, exit_codes=[1, 0], duration_ms=15))
        db.add(TestArtifact(run_id=run_id, flow_id="flow-1", kind="screenshot",
                            path="flow-1/t/shot.png"))
        db.add(Classification(run_id=run_id, flow_id="flow-1", classification="product_defect",
                              confidence=90, evidence={"error_text": "boom"}))
        db.add(Defect(run_id=run_id, flow_id="flow-1", classification="product_defect",
                      confidence=90, fingerprint="fp-abc", jira_label="fp-abc", status="draft"))
        await db.commit()


def _patch_mine(monkeypatch, n_flows: int = 3) -> None:
    from app.services import coverage_dash

    async def _fake_mine(driver=None):  # noqa: ANN001, ARG001
        return {"flows": [{"id": f"flow-{i}"} for i in range(n_flows)], "bounded": True}

    monkeypatch.setattr(coverage_dash, "mine_flows_from_neo4j", _fake_mine)


# --- the aggregations -------------------------------------------------------------------------


@_loop_module
async def test_dashboards_aggregates(monkeypatch) -> None:
    from app.db.session import SessionLocal
    from app.services import dashboards

    run_id = f"dash-{uuid.uuid4().hex}"
    try:
        _patch_mine(monkeypatch, 3)
        await _seed(run_id)

        async with SessionLocal() as db:
            # --- EXECUTIVE: coverage + pass-rate trend + defects trend + KPIs ---
            exe = await dashboards.executive(db)
            assert exe["coverage"]["total_discovered"] == 3
            assert exe["coverage"]["covered"] == 1  # only flow-0 (approved + passing)
            assert isinstance(exe["pass_rate_trend"], list)
            assert isinstance(exe["defects_trend"], list)
            assert sum(d["count"] for d in exe["defects_trend"]) >= 1
            # pass_rate KPI is a PERCENT 0..100 (the x100 conversion documented for the UI meter)
            assert 0.0 <= exe["kpis"]["pass_rate_percent"] <= 100.0
            assert exe["kpis"]["open_defects"] >= 1  # the draft defect is "open" (!= rejected)

            # --- QA: run history + failed tests + RUN-RELATIVE artifact refs ---
            qa = await dashboards.qa(db)
            assert any(r.run_id == run_id for r in qa["runs"])  # list_runs shape (TestRun rows)
            failed = {f["flow_id"]: f for f in qa["failed_tests"]}
            assert "flow-1" in failed  # product_failure is a failed test
            assert "flow-0" not in failed  # passed is not
            arts = failed["flow-1"]["artifacts"]
            assert arts and arts[0]["kind"] == "screenshot"
            # RUN-RELATIVE path, never an absolute fs path
            p = arts[0]["path"]
            assert p == "flow-1/t/shot.png"
            assert not p.startswith("/") and ":" not in p

            # --- DEVELOPER: root-cause groupings + error trend + module breakdown ---
            dev = await dashboards.developer(db)
            groups = dev["root_cause_groups"]
            assert groups and groups[0]["count"] >= 1
            assert "classification" in groups[0] and "fingerprint" in groups[0]
            assert isinstance(dev["errors_trend"], list)
            mods = {m["flow_id"]: m["failure_count"] for m in dev["module_breakdown"]}
            assert mods.get("flow-1", 0) >= 1  # the product_failure flow appears
    finally:
        await _delete_run(run_id)


@_loop_module
async def test_empty_data_is_honest_empty(monkeypatch) -> None:
    """No data -> empty lists + 0 KPIs, never fabricated rows."""
    from app.db.session import SessionLocal
    from app.services import dashboards

    _patch_mine(monkeypatch, 0)
    async with SessionLocal() as db:
        exe = await dashboards.executive(db)
        assert exe["coverage"]["total_discovered"] == 0
        assert exe["coverage"]["coverage_percent"] == 0.0
        qa = await dashboards.qa(db)
        assert isinstance(qa["failed_tests"], list)
        dev = await dashboards.developer(db)
        assert isinstance(dev["root_cause_groups"], list)
        assert isinstance(dev["module_breakdown"], list)


# --- the role matrix (Task 3): per-route require_role(...) — 200 allowed / 403 denied / 401 unauth


def _stub_user(role: str):
    def _dep():
        class _U:
            id = 1
            email = "u@example.com"

        u = _U()
        u.role = role
        return u

    return _dep


def _make_app(role: str | None):
    from app.core.security import get_current_user
    from app.main import app

    app.dependency_overrides.clear()
    if role is not None:
        app.dependency_overrides[get_current_user] = _stub_user(role)
    return app


# endpoint -> (allowed roles, denied roles) per the rbac.py matrix.
_MATRIX = {
    "/api/dashboards/executive": (
        ["admin", "qa_lead"],
        ["developer", "qa_engineer"],
    ),
    "/api/dashboards/qa": (
        ["admin", "qa_lead", "qa_engineer"],
        ["developer"],
    ),
    "/api/dashboards/developer": (
        ["admin", "qa_lead", "developer"],
        ["qa_engineer"],
    ),
    "/api/coverage/flows": (
        ["admin", "qa_lead", "developer"],
        ["qa_engineer"],
    ),
}


@_loop_module
@pytest.mark.parametrize("path", list(_MATRIX))
async def test_role_matrix_allowed_and_denied(monkeypatch, path: str) -> None:
    """Each route: permitted roles 200; disallowed roles 403; unauthenticated 401."""
    _patch_mine(monkeypatch, 0)  # executive/coverage mine the graph — keep keyless
    allowed, denied = _MATRIX[path]
    try:
        for role in allowed:
            app = _make_app(role)
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.get(path)
            assert resp.status_code == 200, f"{role} on {path} should be 200, got {resp.status_code}: {resp.text}"

        for role in denied:
            app = _make_app(role)
            async with httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                resp = await c.get(path)
            assert resp.status_code == 403, f"{role} on {path} should be 403, got {resp.status_code}"

        # unauthenticated -> 401
        app = _make_app(None)
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.get(path)
        assert resp.status_code == 401, f"unauth on {path} should be 401, got {resp.status_code}"
    finally:
        _make_app(None).dependency_overrides.clear()
