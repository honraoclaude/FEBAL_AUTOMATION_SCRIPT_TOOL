"""DASH-05 traceability — the read-time cross-store join + the role-gated router.

Two layers (the test_dashboards / test_defects_router discipline — in-process over the real app +
real Postgres via SessionLocal; no running HTTP stack):

  - test_chain_from_each_entry_id: seeds a full lifecycle slice (flow ↔ scenario ↔ execution ↔
    artifact ↔ defect on shared run_id+flow_id keys) and calls the traceability.chain SERVICE
    from EACH of the four entry ids (run_id / scenario_id / flow_id / defect_id), asserting the
    same assembled chain. Plus the honest-gap cases (a flow with no execution → executions=[]) and
    the no-match case (an unknown id → entry echoed, every segment empty).
  - the router (Task 2): GET /api/traceability is role-gated (the rbac.py matrix: admin/qa_lead/
    developer 200, qa_engineer 403, unauth 401), requires EXACTLY one entry id (422 for zero or
    multiple), returns the chain for each entry, and returns the honest empty chain for an unknown
    id (200, NOT 404).

The flow segment mines the graph; here mine_flows_from_neo4j is monkeypatched (keyless). The
graph-marked live variant runs under graph_mode. The single-write-path discipline holds: the
service joins on READ only — a static-source assertion guards that no write-Cypher entered it.

Run: cd apps/api && uv run python -m pytest tests/integration/test_traceability.py -x -q
"""

from __future__ import annotations

import inspect
import re
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


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def _reset_engine_pool():
    """Dispose the shared SQLAlchemy engine pool around this module so its asyncpg connections
    bind to THIS module's event loop (the Windows cross-loop teardown discipline)."""
    from app.db.session import engine

    await engine.dispose()
    yield
    await engine.dispose()


async def _delete_run(run_id: str) -> None:
    conn = await asyncpg.connect(_host_dsn())
    try:
        for tbl in (
            "scenarios",
            "test_results",
            "test_runs",
            "test_artifacts",
            "classifications",
            "defects",
        ):
            await conn.execute(f"DELETE FROM {tbl} WHERE run_id = $1", run_id)
    finally:
        await conn.close()


async def _seed(run_id: str) -> dict:
    """Seed a full lifecycle slice for ONE run; returns the created scenario/defect ids.

    flow-0: scenario(approved) + passing execution + screenshot artifact (a complete chain).
    flow-1: scenario(approved) + product_failure execution + a classified defect (with jira_key).
    flow-9: scenario(approved) ONLY — no execution/defect (the honest-gap case).
    """
    from app.db.session import SessionLocal
    from app.models.defects import Classification, Defect
    from app.models.execution_history import TestArtifact, TestResult, TestRun
    from app.models.scenario import Scenario

    ids: dict = {}
    async with SessionLocal() as db:
        db.add(
            TestRun(run_id=run_id, tier="regression", status="failed", total=2, passed=1, failed=1, flaky=0)
        )
        s0 = Scenario(run_id=run_id, flow_id="flow-0", feature_name="f0",
                      gherkin_text="x", then_refs=[], status="approved")
        s1 = Scenario(run_id=run_id, flow_id="flow-1", feature_name="f1",
                      gherkin_text="x", then_refs=[], status="approved")
        s9 = Scenario(run_id=run_id, flow_id="flow-9", feature_name="f9",
                      gherkin_text="x", then_refs=[], status="approved")
        db.add_all([s0, s1, s9])
        db.add(TestResult(run_id=run_id, flow_id="flow-0", verdict="passed",
                          attempts=1, exit_codes=[0], duration_ms=10))
        db.add(TestResult(run_id=run_id, flow_id="flow-1", verdict="product_failure",
                          attempts=2, exit_codes=[1, 1], duration_ms=20,
                          error_text="AssertionError: boom"))
        db.add(TestArtifact(run_id=run_id, flow_id="flow-0", kind="screenshot",
                            path="flow-0/t/shot.png"))
        db.add(Classification(run_id=run_id, flow_id="flow-1", classification="product_defect",
                              confidence=90, evidence={"error_text": "boom"}))
        d1 = Defect(run_id=run_id, flow_id="flow-1", classification="product_defect",
                    confidence=90, fingerprint="fp-trace", jira_label="fp-trace",
                    jira_key="PROJ-7", status="draft")
        db.add(d1)
        await db.commit()
        await db.refresh(s0)
        await db.refresh(s1)
        await db.refresh(d1)
        ids = {"scenario0_id": s0.id, "scenario1_id": s1.id, "defect1_id": d1.id}
    return ids


def _patch_mine(monkeypatch, flow_ids: list[str]) -> None:
    from app.services import traceability

    async def _fake_mine(driver=None):  # noqa: ANN001, ARG001
        return {
            "flows": [
                {"id": fid, "name": f"Flow {fid}", "category": "core",
                 "risk_tier": "low", "step_count": 3}
                for fid in flow_ids
            ],
            "bounded": True,
        }

    monkeypatch.setattr(traceability, "mine_flows_from_neo4j", _fake_mine)


# --- Task 1: the cross-store chain from each of the four entry ids ----------------------------


@_loop_module
async def test_chain_from_each_entry_id(monkeypatch) -> None:
    from app.db.session import SessionLocal
    from app.services import traceability

    run_id = f"trace-{uuid.uuid4().hex}"
    try:
        _patch_mine(monkeypatch, ["flow-0", "flow-1", "flow-9"])
        ids = await _seed(run_id)

        async with SessionLocal() as db:
            # --- entry by run_id: the whole run's chain across flow-0/flow-1/flow-9 ---
            by_run = await traceability.chain(db, run_id=run_id)
            assert by_run["entry"] == {"type": "run", "id": run_id}
            scn_flows = {s["flow_id"] for s in by_run["scenarios"]}
            assert {"flow-0", "flow-1"} <= scn_flows  # flow-9 has no TestResult so not in run flows
            exec_flows = {e["flow_id"] for e in by_run["executions"]}
            assert exec_flows == {"flow-0", "flow-1"}
            # the passing execution carries its parent run tier/status (the TestRun join)
            assert any(e["verdict"] == "passed" and e["tier"] == "regression"
                       for e in by_run["executions"])
            assert any(d["jira_key"] == "PROJ-7" for d in by_run["defects"])
            assert any(a["kind"] == "screenshot" for a in by_run["artifacts"])
            # scripts are convention-derived (NOT a stored column)
            assert by_run["scripts"] and all(s["derived"] is True for s in by_run["scripts"])
            assert run_id in by_run["scripts"][0]["path"]

            # --- entry by scenario_id (flow-1): resolves run+flow, assembles its chain ---
            by_scn = await traceability.chain(db, scenario_id=ids["scenario1_id"])
            assert by_scn["entry"] == {"type": "scenario", "id": str(ids["scenario1_id"])}
            assert {e["flow_id"] for e in by_scn["executions"]} == {"flow-1"}
            assert by_scn["defects"] and by_scn["defects"][0]["flow_id"] == "flow-1"
            # the flow segment came from the mined graph (best-effort, READ-only)
            assert by_scn["flow"] is not None and by_scn["flow"]["flow_id"] == "flow-1"

            # --- entry by flow_id: every scenario/execution/defect carrying that flow ---
            by_flow = await traceability.chain(db, flow_id="flow-1")
            assert by_flow["entry"] == {"type": "flow", "id": "flow-1"}
            assert {e["flow_id"] for e in by_flow["executions"]} == {"flow-1"}
            assert by_flow["defects"][0]["jira_key"] == "PROJ-7"

            # --- entry by defect_id: resolves run+flow, assembles the chain ---
            by_def = await traceability.chain(db, defect_id=ids["defect1_id"])
            assert by_def["entry"] == {"type": "defect", "id": str(ids["defect1_id"])}
            assert {e["flow_id"] for e in by_def["executions"]} == {"flow-1"}
            assert by_def["scenarios"] and by_def["scenarios"][0]["flow_id"] == "flow-1"

            # --- HONEST GAP: flow-9 has an approved scenario but NO execution/defect ---
            by_gap = await traceability.chain(db, flow_id="flow-9")
            assert by_gap["scenarios"] and by_gap["scenarios"][0]["flow_id"] == "flow-9"
            assert by_gap["executions"] == []  # honest empty — never a fabricated node
            assert by_gap["defects"] == []
            assert by_gap["artifacts"] == []

            # --- NO MATCH: an unknown id echoes the entry, every segment empty/null ---
            by_none = await traceability.chain(db, run_id="does-not-exist")
            assert by_none["entry"] == {"type": "run", "id": "does-not-exist"}
            assert by_none["flow"] is None
            assert by_none["scenarios"] == []
            assert by_none["executions"] == []
            assert by_none["defects"] == []
    finally:
        await _delete_run(run_id)


@_loop_module
async def test_graph_down_degrades_honestly(monkeypatch) -> None:
    """A down graph → flow=null + a note; the relational chain still assembles (never a 500)."""
    from app.db.session import SessionLocal
    from app.services import traceability

    run_id = f"trace-{uuid.uuid4().hex}"

    async def _boom(driver=None):  # noqa: ANN001, ARG001
        raise RuntimeError("graph down")

    try:
        await _seed(run_id)
        monkeypatch.setattr(traceability, "mine_flows_from_neo4j", _boom)
        async with SessionLocal() as db:
            ch = await traceability.chain(db, flow_id="flow-1")
            assert ch["flow"] is None
            assert ch["flow_note"] and "unavailable" in ch["flow_note"].lower()
            # the relational segments still assembled
            assert {e["flow_id"] for e in ch["executions"]} == {"flow-1"}
    finally:
        await _delete_run(run_id)


def test_no_write_cypher_in_traceability() -> None:
    """The single-write-path discipline: the service holds NO write-Cypher (READ-only join).

    Mirrors the kg writer-gate discipline — scan the SOURCE for write-Cypher keywords, skipping
    prose lines (comments + docstring) so the documentation may name the forbidden keywords.
    """
    from app.services import traceability

    src = inspect.getsource(traceability)
    code_lines = []
    in_doc = False
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            # toggle for a one-line docstring vs a block; treat the module docstring as prose
            if stripped.count('"""') == 2 or stripped.count("'''") == 2:
                continue
            in_doc = not in_doc
            continue
        if in_doc or stripped.startswith("#"):
            continue
        code_lines.append(line)
    code = "\n".join(code_lines)
    # The single-write-path keywords (Cypher writes): MERGE / CREATE / SET x= / DELETE.
    assert not re.search(r"\bMERGE\b", code)
    assert not re.search(r"\bCREATE \b", code)
    assert not re.search(r"\bSET\s+\w+\s*=", code)
    assert not re.search(r"\bDELETE\b", code)


# --- Task 2: the role-gated router (matrix + exactly-one-entry-id + honest empty) -------------


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


@_loop_module
async def test_router_role_matrix(monkeypatch) -> None:
    """admin/qa_lead/developer 200; qa_engineer 403; unauthenticated 401 (the rbac.py matrix)."""
    _patch_mine(monkeypatch, [])
    path = "/api/traceability?run_id=any"
    try:
        for role in ("admin", "qa_lead", "developer"):
            app = _make_app(role)
            async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(path)
            assert resp.status_code == 200, f"{role}: {resp.status_code} {resp.text}"

        app = _make_app("qa_engineer")
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(path)
        assert resp.status_code == 403, resp.text

        app = _make_app(None)
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(path)
        assert resp.status_code == 401, resp.text
    finally:
        _make_app(None).dependency_overrides.clear()


@_loop_module
async def test_router_requires_exactly_one_entry_id(monkeypatch) -> None:
    """Zero ids → 422; multiple ids → 422 (the router never silently picks one)."""
    _patch_mine(monkeypatch, [])
    try:
        app = _make_app("admin")
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # zero entry ids
            r0 = await c.get("/api/traceability")
            assert r0.status_code == 422, r0.text
            # two entry ids
            r2 = await c.get("/api/traceability?run_id=a&flow_id=flow-0")
            assert r2.status_code == 422, r2.text
    finally:
        _make_app(None).dependency_overrides.clear()


@_loop_module
async def test_router_returns_chain_for_each_entry(monkeypatch) -> None:
    """Each single entry id returns the chain shape; an unknown id → 200 honest empty (not 404)."""
    from app.db.session import SessionLocal  # noqa: F401 -- import discipline parity

    run_id = f"trace-{uuid.uuid4().hex}"
    try:
        _patch_mine(monkeypatch, ["flow-0", "flow-1", "flow-9"])
        ids = await _seed(run_id)
        app = _make_app("admin")

        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            for query in (
                f"run_id={run_id}",
                f"scenario_id={ids['scenario1_id']}",
                "flow_id=flow-1",
                f"defect_id={ids['defect1_id']}",
            ):
                resp = await c.get(f"/api/traceability?{query}")
                assert resp.status_code == 200, f"{query}: {resp.text}"
                body = resp.json()
                assert "entry" in body and "scenarios" in body and "executions" in body
                assert any(e["flow_id"] == "flow-1" for e in body["executions"])

            # an unknown id → an honest empty chain at 200 (NOT a 404)
            resp = await c.get("/api/traceability?run_id=nope-unknown")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["entry"] == {"type": "run", "id": "nope-unknown"}
            assert body["scenarios"] == [] and body["executions"] == [] and body["defects"] == []
    finally:
        await _delete_run(run_id)
        _make_app(None).dependency_overrides.clear()
