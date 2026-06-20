"""SC2 functional proofs for generation (03-03 Task 3).

Two surfaces here:

1. Auth gate (T-03-13) — runs on the DEFAULT gate (functional only): both /generate-*
   endpoints reject an unauthenticated client with 401. No spend, no provider keys.

2. live_llm end-to-end (the REAL-spend proof of SC2) — SKIPPED on the default gate. With
   real provider keys present it drives explore -> generate-bdd -> generate-scripts for one
   run_id and asserts BOTH artifacts exist and the spec is ast-parseable. This is the only
   path that actually exercises the live provider; it is `live_llm`-marked so the default
   `not live_llm and not e2e and not graph` gate stays zero-spend.
"""

import ast
import os
import uuid

import pytest

SAUCEDEMO_INCLUSTER_URL = "http://saucedemo:80"


def _has_provider_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def _unique_name(prefix: str = "gen-target") -> str:
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


@pytest.mark.functional
async def test_generate_requires_auth(client):
    """Both generation endpoints reject an unauthenticated client with 401 (T-03-13)."""
    # Valid-shaped body so a 401-vs-422 ordering quirk can never mask the gate.
    body = {"run_id": "deadbeef"}

    r_bdd = await client.post("/api/generate-bdd", json=body)
    assert r_bdd.status_code == 401, f"generate-bdd auth gate: {r_bdd.status_code}"

    r_scripts = await client.post("/api/generate-scripts", json=body)
    assert r_scripts.status_code == 401, f"generate-scripts auth gate: {r_scripts.status_code}"


@pytest.mark.functional
@pytest.mark.live_llm
@pytest.mark.graph
@pytest.mark.skipif(not _has_provider_key(), reason="no provider key — live generation proof (SC2 Manual-Only)")
async def test_generate_bdd_and_scripts_end_to_end(authed_client):
    """live_llm: explore -> generate-bdd -> generate-scripts -> both artifacts exist (SC2).

    The real-spend proof of SC2 — needs provider keys AND the neo4j graph profile (the
    explore crawl writes the graph the generator grounds on). Skipped on the default gate.
    """
    from tests.conftest import poll_until_terminal

    target_id = await _register_saucedemo_target(authed_client)

    r = await authed_client.post("/api/explore", json={"target_id": target_id})
    assert r.status_code == 202, f"explore not accepted: {r.status_code} {r.text}"
    run_id = r.json()["run_id"]

    final = await poll_until_terminal(authed_client, run_id, timeout=90.0, interval=1.5)
    assert final["status"] == "passed", f"explore run not passed: {final}"

    r_bdd = await authed_client.post("/api/generate-bdd", json={"run_id": run_id})
    assert r_bdd.status_code == 200, f"generate-bdd failed: {r_bdd.status_code} {r_bdd.text}"
    feature_path = r_bdd.json()["feature_path"]
    assert feature_path.endswith("login.feature")

    # Slice 3 supersedes the Phase-3 plain-spec generate-scripts with the approved-scenario
    # codegen (D-01): codegen reads status=approved only, so generate scenarios then approve
    # them before generate-scripts.
    r_gen = await authed_client.post("/api/generate-scenarios", json={"run_id": run_id})
    assert r_gen.status_code == 200, f"generate-scenarios failed: {r_gen.text}"
    scenario_ids = r_gen.json()["scenario_ids"]
    assert scenario_ids, "expected at least one draft scenario"
    for sid in scenario_ids:
        r_appr = await authed_client.post(f"/api/scenarios/{sid}/approve")
        assert r_appr.status_code == 200, f"approve {sid} failed: {r_appr.text}"

    r_scripts = await authed_client.post("/api/generate-scripts", json={"run_id": run_id})
    assert r_scripts.status_code == 200, (
        f"generate-scripts failed: {r_scripts.status_code} {r_scripts.text}"
    )
    project_root = r_scripts.json()["project_root"]
    assert project_root.endswith("/target") or project_root.endswith("\\target")

    # The codegen runs in the api container; assert the generated project tree exists and every
    # generated .py is ast-parseable (read from inside that container; artifacts live under
    # workspaces/<run_id>/target/).
    import subprocess

    check = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "infra/docker-compose.yml",
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            (
                "import ast,pathlib;"
                f"root=pathlib.Path('/app/workspaces/{run_id}/target');"
                "subs=['pages','steps','features','conftest.py'];"
                "ok=all((root/s).exists() for s in subs);"
                "[ast.parse((p).read_text()) for p in root.rglob('*.py')];"
                "print('tree ok' if ok else 'missing tree')"
            ),
        ],
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, f"project ast-parse failed: {check.stderr}"
    assert "tree ok" in check.stdout, f"project tree incomplete: {check.stdout}"
