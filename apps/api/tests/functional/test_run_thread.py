"""run_id traceability sweep (03-04 Task 3) — explore -> generate -> execute -> result.

The whole tracer is threaded by ONE run_id: /explore returns it, generate-bdd/scripts write
artifacts under workspaces/<run_id>/, /execute runs the generated spec and writes the
executions row keyed BY that run_id, and the explored Page nodes in Neo4j carry it too.

live_llm + graph: needs real provider keys (generate-* spend) AND the neo4j graph profile
(run under graph_mode with web stopped). Off the default gate. The generated spec here is
the REAL LLM-rendered skeleton (not a planted one) — proving the full money-metered path.

Pitfall 8: unique target name; assert only THIS run_id; clean up workspaces/<run_id>/.
Pitfall 2: poll_until_terminal after each 202 — never assert immediately.
"""

import os
import shutil
import uuid
from pathlib import Path

import pytest

from tests.conftest import poll_until_terminal

pytestmark = [pytest.mark.functional, pytest.mark.live_llm, pytest.mark.graph]

# Skip cleanly when no provider key is configured (live_llm contract, RESEARCH Pitfall 6).
_HAS_KEY = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))

SAUCEDEMO_INCLUSTER_URL = "http://saucedemo:80"
_WORKSPACES_ROOT = Path(__file__).resolve().parents[4] / "workspaces"


def _unique_name(prefix: str = "thread-target") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _register_saucedemo_target(authed_client) -> int:
    body = {
        "name": _unique_name(),
        "base_url": SAUCEDEMO_INCLUSTER_URL,
        "credentials": {"username": "standard_user", "password": "secret_sauce"},
    }
    r = await authed_client.post("/api/targets", json=body)
    assert r.status_code == 201, f"target register failed: {r.status_code} {r.text}"
    return r.json()["id"]


@pytest.mark.skipif(not _HAS_KEY, reason="no provider key — live_llm path skipped")
async def test_run_id_threads_explore_generate_execute_result(authed_client, neo4j_session):
    """One run_id threads explore -> generate-bdd -> generate-scripts -> execute -> result."""
    target_id = await _register_saucedemo_target(authed_client)

    # 1) explore -> run_id (the thread's anchor).
    r = await authed_client.post("/api/explore", json={"target_id": target_id})
    assert r.status_code == 202, f"explore not accepted: {r.text}"
    run_id = r.json()["run_id"]
    assert run_id
    final = await poll_until_terminal(authed_client, run_id, timeout=120.0, interval=2.0)
    assert final["status"] == "passed", f"explore not passed: {final}"

    try:
        # 2) generate-bdd for the SAME run_id (real LLM spend).
        rb = await authed_client.post("/api/generate-bdd", json={"run_id": run_id})
        assert rb.status_code == 200, f"generate-bdd failed: {rb.text}"
        assert rb.json()["run_id"] == run_id

        # Slice 3 rewired POST /generate-scripts to the approved-scenario PROJECT codegen
        # (a tree, not a single test_login.py). The /execute leg below still runs the Phase-3
        # plain-spec convention (workspaces/<run_id>/test_login.py — its execution-engine
        # integration with the codegen tree is Phase 7), so this thread renders that retained
        # plain spec directly via the generation service for the execute leg.
        from app.db.session import SessionLocal
        from app.services import generation

        async with SessionLocal() as gdb:
            spec_path = await generation.generate_scripts(gdb, run_id)
        assert spec_path.endswith("test_login.py")

        # 3) execute the LLM-generated spec for the SAME run_id.
        re = await authed_client.post("/api/execute", json={"run_id": run_id})
        assert re.status_code == 202, f"execute not accepted: {re.text}"
        assert re.json()["run_id"] == run_id
        exec_final = await poll_until_terminal(
            authed_client, run_id, timeout=180.0, interval=2.0
        )
        assert exec_final["status"] == "passed", f"execute not passed: {exec_final}"

        # 4a) the SAME run_id is in the executions ledger row.
        rows = (await authed_client.get("/api/executions")).json()["executions"]
        row = next((e for e in rows if e["run_id"] == run_id), None)
        assert row is not None and row["status"] == "passed"

        # 4b) the SAME run_id tags the explored Page nodes in Neo4j (traceability).
        result = await neo4j_session.run(
            "MATCH (p:Page) WHERE p.run_id=$rid RETURN count(p) AS c", rid=run_id
        )
        record = await result.single()
        assert record["c"] >= 1, f"no Page nodes for run_id {run_id}"
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)
