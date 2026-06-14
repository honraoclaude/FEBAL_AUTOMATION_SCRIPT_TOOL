"""SC3 + FIX 2/FIX 3 proof (03-04 Task 3) — /execute runs the run's spec to a result row.

FIX 2 (deterministic runnable proof, ZERO LLM spend): we PLANT the spec by rendering the
ACTUAL Jinja2 skeleton (app/templates/test_login.py.j2) with the FIXED observed SauceDemo
slots — NOT a hand-written stub. This proves the GENERATED skeleton itself runs green
against live SauceDemo with no provider call, so the test is graph-marked but carries NO
live_llm marker.

FIX 3 (missing-spec 404): POST /execute with an unknown run_id (no workspaces/<id>/spec on
disk) → 404.

Graph-marked because the surrounding tracer phase runs under graph_mode; /execute itself
needs only Postgres + the SauceDemo target reachable from the api container. The subprocess
(`uv run pytest <spec>`) launches Chromium inside the api container, which reaches SauceDemo
by its in-cluster compose name (http://saucedemo:80) — so the planted spec uses that URL.

Pitfall 8: unique run_id per test; assert only THIS run_id's row; clean up workspaces/<id>/.
Pitfall 2: never assert immediately after the 202 — poll_until_terminal to a terminal status.
"""

import shutil
import uuid
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

from tests.conftest import poll_until_terminal

pytestmark = [pytest.mark.functional, pytest.mark.graph]

# The spec runs INSIDE the api container, so it must reach SauceDemo by its in-cluster
# compose name (mirrors test_explore.py) — not the host-published localhost:8080.
SAUCEDEMO_INCLUSTER_URL = "http://saucedemo:80"
_SAUCEDEMO_USER = "standard_user"
_SAUCEDEMO_PASSWORD = "secret_sauce"

# Repo root: tests/functional/test_execute.py -> functional -> tests -> api -> apps -> root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_WORKSPACES_ROOT = _REPO_ROOT / "workspaces"
_TEMPLATES_DIR = _REPO_ROOT / "apps" / "api" / "app" / "templates"
_SPEC_TEMPLATE = "test_login.py.j2"


def _render_real_template(scenario_name: str) -> str:
    """Render the ACTUAL generation Jinja2 skeleton with fixed observed slots (FIX 2).

    Mirrors app.services.generation._jinja_env / generate_scripts exactly, but with the
    in-cluster SauceDemo URL and NO LLM — the rendered text is the same skeleton the real
    generate-scripts path would produce.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(enabled_extensions=(), default=False),
        keep_trailing_newline=True,
    )
    template = env.get_template(_SPEC_TEMPLATE)
    return template.render(
        base_url=SAUCEDEMO_INCLUSTER_URL,
        username=_SAUCEDEMO_USER,
        password=_SAUCEDEMO_PASSWORD,
        scenario_name=scenario_name,
    )


def _plant_spec(run_id: str) -> Path:
    """Write workspaces/<run_id>/test_login.py from the rendered real template (FIX 2)."""
    run_dir = _WORKSPACES_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    spec_path = run_dir / "test_login.py"
    spec_path.write_text(_render_real_template("execute-proof login"), encoding="utf-8")
    return spec_path


async def test_execute_runs_rendered_template_to_passed(authed_client):
    """Plant the rendered skeleton → POST /execute → poll → executions row 'passed' (SC3)."""
    run_id = f"exec-{uuid.uuid4().hex}"
    _plant_spec(run_id)
    try:
        r = await authed_client.post("/api/execute", json={"run_id": run_id})
        assert r.status_code == 202, f"execute not accepted: {r.status_code} {r.text}"
        assert r.json()["run_id"] == run_id

        # NEVER assert immediately after the 202 — poll the run_id-keyed Execution row.
        final = await poll_until_terminal(authed_client, run_id, timeout=120.0, interval=2.0)
        assert final["status"] == "passed", f"execute run not passed: {final}"

        # The executions ledger row carries the result + spec_path (FIX 1 / SC3).
        rows = (await authed_client.get("/api/executions")).json()["executions"]
        row = next((e for e in rows if e["run_id"] == run_id), None)
        assert row is not None, f"no executions row for run_id {run_id}"
        assert row["status"] == "passed"
        assert row["output"], "executions row has empty output"
        assert row["spec_path"], "executions row has no spec_path"
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)


async def test_execute_unknown_run_id_404(authed_client):
    """POST /execute for a run_id with no planted spec → 404 (FIX 3)."""
    unknown = f"missing-{uuid.uuid4().hex}"
    assert not (_WORKSPACES_ROOT / unknown / "test_login.py").exists()
    r = await authed_client.post("/api/execute", json={"run_id": unknown})
    assert r.status_code == 404, f"expected 404 for missing spec, got {r.status_code} {r.text}"


async def test_execute_requires_auth(client):
    """POST /execute rejects an unauthenticated client with 401 (T-03-17)."""
    r = await client.post("/api/execute", json={"run_id": "anything"})
    assert r.status_code == 401
