"""CI workflow contract — keyless yaml-parse + start/poll/exit-mapping assertions (EXEC-02 / D-08).

This proves the CI trigger contract WITHOUT a live GitHub runner or a reachable API (the live
trigger is Manual-Only, RESEARCH A5 — needs a self-hosted runner / tunnel). We parse
.github/workflows/run-suite.yml as yaml and assert the same-engine CI contract holds:

  - it is a workflow_dispatch trigger with a `tier` input (D-08 manual CI start);
  - it POSTs to /api/executions to START a run and polls GET /api/executions/{run_id} for status
    (the SAME engine code path — never `pytest` directly in CI);
  - it presents the SCOPED CI_TOKEN as a Bearer and reads CI_TOKEN + PLATFORM_API_URL from
    `secrets` (never inlining a literal token — Pitfall 7 / T-07-07);
  - the token is NEVER echoed into the logs (no `echo $CI_TOKEN`);
  - the documented status->exit mapping is passed->0 / failed->1 (D-08).

NOTE: yaml's `on:` key is the boolean True under YAML 1.1 truthy-key coercion (PyYAML
safe_load), so the trigger block is looked up by BOTH `"on"` and `True` keys.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

# tests/unit/test_ci_workflow_contract.py -> unit -> tests -> api -> apps -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "run-suite.yml"


def _load_workflow() -> dict:
    assert _WORKFLOW_PATH.exists(), f"CI workflow missing: {_WORKFLOW_PATH}"
    return yaml.safe_load(_WORKFLOW_PATH.read_text(encoding="utf-8"))


def _trigger_block(wf: dict) -> dict:
    # PyYAML coerces the bare `on:` key to the boolean True (YAML 1.1 truthy keys).
    return wf.get("on", wf.get(True)) or {}


def _workflow_text() -> str:
    return _WORKFLOW_PATH.read_text(encoding="utf-8")


def test_workflow_parses_as_yaml_with_workflow_dispatch_and_tier_input() -> None:
    """The workflow is valid yaml with a workflow_dispatch trigger carrying a `tier` input."""
    wf = _load_workflow()
    trigger = _trigger_block(wf)
    assert "workflow_dispatch" in trigger, f"expected workflow_dispatch trigger, got {trigger}"
    inputs = (trigger["workflow_dispatch"] or {}).get("inputs", {})
    assert "tier" in inputs, f"expected a `tier` input on workflow_dispatch, got {inputs}"


def test_workflow_starts_and_polls_the_executions_engine_route() -> None:
    """It POSTs to /api/executions (start) and polls GET /api/executions/{run_id} (status)."""
    text = _workflow_text()
    # Start: POST to /api/executions (the same-engine start route, D-08). The curl is split
    # across lines with `\` continuations, so match POST and the executions URL with DOTALL.
    assert "/api/executions" in text, "workflow must call the /api/executions engine route"
    assert re.search(
        r"-X\s+POST.*\$PLATFORM_API_URL/api/executions", text, flags=re.DOTALL
    ), "workflow must POST to /api/executions to START a run"
    # Poll: GET /api/executions/<run_id> for status.
    assert re.search(r"\$PLATFORM_API_URL/api/executions/\$run_id", text), (
        "workflow must poll GET /api/executions/{run_id} for status"
    )
    # SAME engine path — never a direct pytest invocation in CI (D-08). Ignore comment lines
    # (the header documents the no-pytest rule); assert no NON-comment line invokes pytest.
    non_comment = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    assert "pytest" not in non_comment, (
        "CI must NOT run pytest directly — it calls the engine (D-08)"
    )


def test_workflow_uses_scoped_secret_token_and_never_inlines_or_echoes_it() -> None:
    """CI_TOKEN + PLATFORM_API_URL come from `secrets`; the token is never inlined or echoed."""
    text = _workflow_text()
    # Both values are sourced from GitHub Actions secrets (no literal credential in the yaml).
    assert "secrets.CI_TOKEN" in text, "CI_TOKEN must come from secrets"
    assert "secrets.PLATFORM_API_URL" in text, "PLATFORM_API_URL must come from secrets"
    # The token is presented as a Bearer on the start/poll calls.
    assert "Authorization: Bearer $CI_TOKEN" in text, "token must be a Bearer on the API calls"
    # NEVER echoed into the logs (Pitfall 7 / T-07-07) — no `echo`-ing the token.
    assert not re.search(r"echo\s+[\"']?\$?\{?\s*CI_TOKEN", text, flags=re.IGNORECASE), (
        "CI_TOKEN must never be echoed into the workflow logs"
    )
    # No literal JWT/token string inlined (a real token has dotted base64 segments).
    assert not re.search(r"eyJ[A-Za-z0-9_-]+\.", text), "no literal JWT token may be inlined"


def test_workflow_documents_passed_zero_failed_one_mapping() -> None:
    """The status->exit mapping is passed->exit 0 and failed->exit 1 (D-08 conclusion mapping)."""
    text = _workflow_text()
    # passed -> exit 0
    assert re.search(r"passed\)[^\n]*exit 0", text), "passed must map to exit 0"
    # failed (and killed) -> exit 1
    assert re.search(r"failed[^\n]*exit 1", text), "failed must map to exit 1"


def test_ci_token_setting_exists_and_defaults_none() -> None:
    """settings.ci_token (env CI_TOKEN) exists as the scoped start+poll credential, default None."""
    from app.core.config import Settings

    field = Settings.model_fields.get("ci_token")
    assert field is not None, "Settings must declare a ci_token field (env CI_TOKEN)"
    assert field.default is None, "ci_token must default to None so the api boots without it"
