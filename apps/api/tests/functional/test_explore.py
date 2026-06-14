"""SC1 functional proof (03-02 Task 3) — explore → terminal status → Neo4j nodes.

Graph-marked: needs the neo4j graph profile active (run under graph_mode with web
stopped — memory budget). The crawl BackgroundTask runs INSIDE the api container, so
the registered target's base_url is the IN-CLUSTER SauceDemo host (http://saucedemo:80),
not the host-published :8080 — the container reaches the demo target by its compose name.

Flow proven here (SC1):
  1. register a SauceDemo target (unique name; standard_user/secret_sauce).
  2. POST /api/explore → 202 + run_id.
  3. poll_until_terminal (NEVER assert immediately after the 202 — Pitfall 2) until the
     RUN row (explore path) reaches "passed" via GET /api/executions/{run_id}.
  4. query Neo4j for >= 1 (:Page)-[:NavigatesTo]->(:Page) edge tagged with THIS run_id.

Pitfall 8: unique target name per test; assert only nodes for THIS run_id, never globals.
"""

import uuid

import pytest

pytestmark = [pytest.mark.functional, pytest.mark.graph]

# In-cluster SauceDemo host — the crawl runs in the api container and reaches the demo
# target by its compose service name, not the host-published localhost:8080.
SAUCEDEMO_INCLUSTER_URL = "http://saucedemo:80"


def _unique_name(prefix: str = "explore-target") -> str:
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


async def test_explore_writes_page_navigatesto_for_run_id(authed_client, neo4j_session):
    """POST /explore → poll to passed → >= 1 NavigatesTo edge in Neo4j for the run_id."""
    target_id = await _register_saucedemo_target(authed_client)

    r = await authed_client.post("/api/explore", json={"target_id": target_id})
    assert r.status_code == 202, f"explore not accepted: {r.status_code} {r.text}"
    run_id = r.json()["run_id"]
    assert run_id, "explore did not return a run_id"

    # NEVER assert immediately after the 202 — poll the run_id-keyed status to terminal.
    from tests.conftest import poll_until_terminal

    final = await poll_until_terminal(authed_client, run_id, timeout=90.0, interval=1.5)
    assert final["status"] == "passed", f"explore run not passed: {final}"

    # Real Page/NavigatesTo nodes exist for THIS run_id (SC1).
    result = await neo4j_session.run(
        "MATCH (a:Page)-[:NavigatesTo]->(b:Page) WHERE a.run_id=$rid RETURN count(*) AS c",
        rid=run_id,
    )
    record = await result.single()
    assert record["c"] >= 1, f"no NavigatesTo edge for run_id {run_id}"


async def test_explore_requires_auth(client):
    """POST /explore rejects an unauthenticated client with 401 (T-03-07)."""
    r = await client.post("/api/explore", json={"target_id": 1})
    assert r.status_code == 401

    r_list = await client.get("/api/executions")
    assert r_list.status_code == 401

    r_get = await client.get("/api/executions/anything")
    assert r_get.status_code == 401
