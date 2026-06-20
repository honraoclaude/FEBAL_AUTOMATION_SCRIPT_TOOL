"""N-run stability harness — deterministic planted-spec proof (GEN-05b / D-07).

PLANTED spec (NO gateway, NO provider keys): render the REAL Phase-3 generation skeleton
(app/templates/test_login.py.j2) with FIXED observed SauceDemo slots — the in-cluster URL,
the public demo creds, and the post-login `.inventory_list` success assertion (the element the
seeded-bug build renames). The rendered spec is made base-URL-env-aware (TARGET_BASE_URL, the
SAME env var the generated conftest reads) so the SAME planted spec serves both the standard
run here and the seeded-bug run in test_seeded_bug.py. This proves the run-N-times + accept-iff-
all-green mechanic with ZERO LLM spend.

Asserts:
  - an all-green planted spec is ACCEPTED over N runs (passes vs standard SauceDemo);
  - a deliberately-failing planted spec is REJECTED (not all green) — and the harness
    fail-fasts (does not run all N once it sees red).

graph-marked because the surrounding tracer phase runs under graph_mode; stability itself needs
NO neo4j (T-06-20 sequencing — codegen reads the graph, the RUN phase does not). These tests
drive the harness IN-PROCESS on the HOST (mirroring test_codegen.py's host-driver pattern), so
the Chromium subprocess reaches SauceDemo by its HOST-published port (localhost:8080), not the
in-cluster compose name. The seeded-bug build is reached at localhost:8081.

Subprocess discipline (the grep acceptance criterion is in the SUMMARY): app/services/stability.py
uses asyncio.create_subprocess_exec with an argv LIST and NO pytest.main / shell=True.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

pytestmark = [pytest.mark.functional, pytest.mark.graph]

# The harness runs IN-PROCESS on the host (not via the api container), so the Chromium
# subprocess reaches SauceDemo by its HOST-published port (mirrors test_codegen's host driver).
SAUCEDEMO_HOST_URL = "http://localhost:8080"
_SAUCEDEMO_USER = "standard_user"
_SAUCEDEMO_PASSWORD = "secret_sauce"
_BASE_URL_ENV = "TARGET_BASE_URL"

# Repo root: tests/functional/test_stability.py -> functional -> tests -> api -> apps -> root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_WORKSPACES_ROOT = _REPO_ROOT / "workspaces"
_TEMPLATES_DIR = _REPO_ROOT / "apps" / "api" / "app" / "templates"
_SPEC_TEMPLATE = "test_login.py.j2"


def _render_planted_spec(scenario_name: str, *, fail: bool = False) -> str:
    """Render the ACTUAL generation skeleton with fixed observed slots (a PLANTED spec, no LLM).

    Mirrors app.services.generation exactly but with the in-cluster URL and NO gateway. The
    rendered BASE_URL constant is rewritten to read the TARGET_BASE_URL env var (defaulting to
    the rendered URL) so the SAME planted spec can be pointed at the seeded-bug build by the
    harness — the env-override mechanism the generated conftest uses. When fail=True the
    post-login success assertion is pointed at an element that never exists, so the run goes red
    (proving the harness rejects a non-green spec).
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(enabled_extensions=(), default=False),
        keep_trailing_newline=True,
    )
    rendered = env.get_template(_SPEC_TEMPLATE).render(
        base_url=SAUCEDEMO_HOST_URL,
        username=_SAUCEDEMO_USER,
        password=_SAUCEDEMO_PASSWORD,
        scenario_name=scenario_name,
    )
    # Make BASE_URL env-overridable (TARGET_BASE_URL) — the SAME env var the generated conftest
    # reads — so the seeded-bug run can repoint the SAME spec without re-rendering.
    rendered = rendered.replace("import pytest\n", "import os\n\nimport pytest\n", 1)
    rendered = rendered.replace(
        f'BASE_URL = "{SAUCEDEMO_HOST_URL}"',
        f'BASE_URL = os.environ.get("{_BASE_URL_ENV}", "{SAUCEDEMO_HOST_URL}")',
    )
    if fail:
        # Repoint the success assertion at an element that does not exist -> the run fails.
        rendered = rendered.replace(".inventory_list", ".this_element_never_exists")
    return rendered


def _plant(run_id: str, *, fail: bool = False) -> Path:
    run_dir = _WORKSPACES_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    spec_path = run_dir / "test_login.py"
    spec_path.write_text(
        _render_planted_spec("stability-proof login", fail=fail), encoding="utf-8"
    )
    return spec_path


async def test_all_green_planted_spec_is_accepted_over_n_runs() -> None:
    """An all-green planted spec passes N runs -> run_stability accepts it (D-07)."""
    from app.services.stability import run_stability

    run_id = f"stab-ok-{uuid.uuid4().hex}"
    spec_path = _plant(run_id)
    try:
        result = await run_stability(spec_path, runs=3)
        assert result["accepted"] is True, f"stable spec not accepted: {result}"
        assert result["runs"] == 3
        assert result["passed_count"] == 3
        assert all(r["passed"] for r in result["results"])
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)


async def test_failing_planted_spec_is_rejected() -> None:
    """A deliberately-failing planted spec is rejected (not all green); harness fail-fasts."""
    from app.services.stability import run_stability

    run_id = f"stab-bad-{uuid.uuid4().hex}"
    spec_path = _plant(run_id, fail=True)
    try:
        result = await run_stability(spec_path, runs=3)
        assert result["accepted"] is False, f"failing spec wrongly accepted: {result}"
        assert result["passed_count"] == 0
        # Fail-fast: a single red run rejects without running all N.
        assert len(result["results"]) == 1, f"expected fail-fast after 1 run: {result}"
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)
