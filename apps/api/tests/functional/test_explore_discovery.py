"""Graph discovery proof (04-01 Task 3) — LangGraph crawl advances beyond the landing page.

Graph-marked: needs the neo4j graph profile active (run under graph_mode with web stopped).
The crawl BackgroundTask runs INSIDE the api container, so the target's base_url is the
IN-CLUSTER SauceDemo host (http://saucedemo:80).

Behaviors proven:
  Test 1: POST /explore -> poll to passed; assert >= 2 DISTINCT (:Page) fingerprints AND
          >= 1 (:Element) node AND >= 1 (:NavigatesTo) edge tagged with this run_id, plus a
          screenshot file under workspaces/<run_id>/. Two distinct pages + an edge PROVES the
          crawl advanced beyond the landing page (H-2).
  Test 2: a run with explore_max_steps overridden to a tiny value terminates with
          run.stop_reason in {"max_steps","wall_clock","saturation","converged"} (budget halt,
          not unbounded).

Pitfall 8: unique target name per test; assert only nodes for THIS run_id, never globals.

LIVE_LLM: the explore BackgroundTask runs INSIDE the api container and drives the REAL
gateway decide node (operation_type="explore.decide") — there is no in-container mock seam,
so this end-to-end proof needs a real provider key. It is therefore both `graph` (neo4j up)
and `live_llm` (real spend, phase-gate only) marked, and is SKIPPED on the default gate when
no key is present — matching the project's live-test convention. The deterministic loop
logic (graph structure, serialization, budget) is proven by the zero-spend unit suite.
"""

import os
import uuid
from pathlib import Path

import pytest

pytestmark = [pytest.mark.functional, pytest.mark.graph, pytest.mark.live_llm]


def _has_provider_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))


# Skip the live proofs when no provider key is configured (live-test convention).
pytestmark.append(
    pytest.mark.skipif(not _has_provider_key(), reason="no provider key — live_llm proof")
)

SAUCEDEMO_INCLUSTER_URL = "http://saucedemo:80"


def _unique_name(prefix: str = "explore-discovery") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _register_saucedemo_target(authed_client, *, budget_overrides=None) -> int:
    body = {
        "name": _unique_name(),
        "base_url": SAUCEDEMO_INCLUSTER_URL,
        "credentials": {"username": "standard_user", "password": "secret_sauce"},
    }
    if budget_overrides is not None:
        body["budget_overrides"] = budget_overrides
    r = await authed_client.post("/api/targets", json=body)
    assert r.status_code == 201, f"target register failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _host_dsn() -> str:
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("@postgres:", "@localhost:")


async def _run_stop_reason(run_id: str) -> str | None:
    """Read runs.stop_reason for this run_id directly from Postgres (host side)."""
    import asyncpg

    conn = await asyncpg.connect(_host_dsn())
    try:
        return await conn.fetchval("SELECT stop_reason FROM runs WHERE run_id=$1", run_id)
    finally:
        await conn.close()


async def test_explore_discovery_advances_beyond_landing(authed_client, neo4j_session):
    """>= 2 distinct Page fingerprints + >= 1 Element + >= 1 NavigatesTo edge for the run."""
    target_id = await _register_saucedemo_target(authed_client)

    r = await authed_client.post("/api/explore", json={"target_id": target_id})
    assert r.status_code == 202, f"explore not accepted: {r.status_code} {r.text}"
    run_id = r.json()["run_id"]
    assert run_id

    from tests.conftest import poll_until_terminal

    final = await poll_until_terminal(authed_client, run_id, timeout=120.0, interval=2.0)
    assert final["status"] == "passed", f"explore run not passed: {final}"

    # >= 2 DISTINCT Page fingerprints for THIS run (crawl advanced beyond landing — H-2).
    pages = await (
        await neo4j_session.run(
            "MATCH (p:Page) WHERE p.run_id=$rid RETURN count(DISTINCT p.fingerprint) AS c",
            rid=run_id,
        )
    ).single()
    assert pages["c"] >= 2, f"expected >=2 distinct page fingerprints, got {pages['c']}"

    # >= 1 NavigatesTo edge for THIS run.
    edges = await (
        await neo4j_session.run(
            "MATCH (:Page {run_id:$rid})-[:NavigatesTo]->(:Page) RETURN count(*) AS c",
            rid=run_id,
        )
    ).single()
    assert edges["c"] >= 1, f"no NavigatesTo edge for run_id {run_id}"

    # >= 1 Element node for THIS run.
    els = await (
        await neo4j_session.run(
            "MATCH (e:Element) WHERE e.run_id=$rid RETURN count(*) AS c", rid=run_id
        )
    ).single()
    assert els["c"] >= 1, f"no Element node for run_id {run_id}"

    # A screenshot file exists under workspaces/<run_id>/ (evidence, D-01).
    ws = Path(os.environ.get("WORKSPACES_DIR_HOST", "")) if os.environ.get("WORKSPACES_DIR_HOST") else None
    if ws is None:
        # Host layout: repo-root/workspaces (this file: tests/functional -> api -> apps -> root).
        ws = Path(__file__).resolve().parents[3] / "workspaces"
    run_ws = ws / run_id
    shots = list(run_ws.glob("state-*.png")) if run_ws.exists() else []
    assert shots, f"no screenshot under {run_ws}"


async def test_explore_budget_halt(authed_client):
    """A tiny explore_max_steps override terminates with a budget/saturation stop_reason."""
    target_id = await _register_saucedemo_target(authed_client, budget_overrides={"max_steps": 1})

    r = await authed_client.post("/api/explore", json={"target_id": target_id})
    assert r.status_code == 202
    run_id = r.json()["run_id"]

    from tests.conftest import poll_until_terminal

    final = await poll_until_terminal(authed_client, run_id, timeout=120.0, interval=2.0)
    assert final["status"] == "passed", f"explore run not passed: {final}"

    stop_reason = await _run_stop_reason(run_id)
    assert stop_reason in {"max_steps", "wall_clock", "saturation", "converged"}, (
        f"unexpected stop_reason {stop_reason!r} — run was not budget-halted"
    )
