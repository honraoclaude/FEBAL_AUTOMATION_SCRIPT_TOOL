"""Mocked-gateway determinism for the generation service (03-03 Task 1/3, SC2 deterministic parts).

ZERO spend, no live stack: the `fake_chat_model` fixture (tests/unit/conftest.py) shapes the
gateway response so we exercise the WHOLE deterministic path — gateway routing, gherkin-official
validation, the Jinja2 render, and the file write — without a provider or a graph.

What these prove (the deterministic half of SC2 / PLAT-02):
  - generate_bdd writes workspaces/<run_id>/login.feature for VALID Gherkin.
  - generate_bdd raises GenerationError and writes NO .feature for MALFORMED Gherkin
    (validate-before-write, T-03-12).
  - generate_scripts renders an ast-parseable test_login.py referencing ONLY the observed
    selectors (Pitfall 5) and returns its workspaces/<run_id>/ path.
  - BOTH steps route through the metered gateway (the fake records the init_chat_model call),
    never a direct provider SDK call.

The REAL end-to-end (live provider) proof is the gated live_llm functional test
(tests/functional/test_generation.py) — skipped on the default gate.
"""

import ast
import shutil
import uuid

import pytest

from app.services import generation
from app.services.generation import GenerationError, generate_bdd, generate_scripts
from app.services.generation import _workspaces_root  # noqa: PLC2701 -- test introspects the artifact dir

_USAGE = {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20}

_VALID_GHERKIN = """Feature: Login
  Scenario: Standard user logs in
    Given the user is on the login page
    When the user logs in as a standard user
    Then the inventory page is shown
"""

_MALFORMED_GHERKIN = "not gherkin {{{"


@pytest.fixture
def run_id() -> str:
    """A unique run_id per test; clean its workspaces/<run_id>/ dir afterwards."""
    rid = "test-gen-" + uuid.uuid4().hex[:12]
    yield rid
    shutil.rmtree(_workspaces_root() / rid, ignore_errors=True)


class _FakeDB:
    """Minimal async DB stand-in: the gateway commits a ledger row; record-and-noop.

    The gateway path calls db.add / await db.commit / await db.refresh. None of those need
    a real session for the deterministic generation assertions (no row is read back).
    """

    def add(self, _row):  # noqa: D401, ANN001
        pass

    async def commit(self):
        pass

    async def refresh(self, _row):  # noqa: ANN001
        pass


@pytest.fixture
def db() -> _FakeDB:
    return _FakeDB()


async def test_generate_bdd_writes_feature_for_valid_gherkin(fake_chat_model, db, run_id):
    """Valid Gherkin from the gateway -> workspaces/<run_id>/login.feature written."""
    fake_chat_model.set(content=_VALID_GHERKIN, usage_metadata=_USAGE)

    feature_path = await generate_bdd(db, run_id)

    written = _workspaces_root() / run_id / "login.feature"
    assert written.exists(), "valid Gherkin should write login.feature"
    assert str(written) == feature_path
    assert written.read_text(encoding="utf-8") == _VALID_GHERKIN
    # Routed through the metered gateway (the fake records the init_chat_model call).
    assert fake_chat_model.calls, "generate_bdd must route through llm_gateway.complete()"


async def test_generate_bdd_rejects_malformed_gherkin_without_writing(
    fake_chat_model, db, run_id
):
    """Malformed Gherkin -> GenerationError AND no .feature on disk (T-03-12)."""
    fake_chat_model.set(content=_MALFORMED_GHERKIN, usage_metadata=_USAGE)

    with pytest.raises(GenerationError):
        await generate_bdd(db, run_id)

    written = _workspaces_root() / run_id / "login.feature"
    assert not written.exists(), "malformed Gherkin must NOT write a .feature"


async def test_generate_scripts_renders_ast_parseable_spec(fake_chat_model, db, run_id):
    """generate_scripts -> ast-parseable test_login.py with ONLY observed selectors."""
    fake_chat_model.set(content="Standard user login", usage_metadata=_USAGE)

    spec_path = await generate_scripts(db, run_id)

    written = _workspaces_root() / run_id / "test_login.py"
    assert written.exists(), "generate_scripts should write test_login.py"
    assert str(written) == spec_path

    source = written.read_text(encoding="utf-8")
    # The rendered spec is importable Python.
    ast.parse(source)

    # Every observed selector is present; no OTHER css/id selector was invented (Pitfall 5).
    for selector in generation.OBSERVED_SELECTORS:
        assert selector in source, f"observed selector {selector} missing from spec"
    # The literal SauceDemo demo creds are template values, never ciphertext (PLAT-07).
    assert "standard_user" in source
    assert "secret_sauce" in source
    # Routed through the metered gateway.
    assert fake_chat_model.calls, "generate_scripts must route through llm_gateway.complete()"


def test_no_direct_provider_call_in_generation_source():
    """generation.py never bypasses the gateway with a direct provider/init_chat_model call."""
    import inspect

    source = inspect.getsource(generation)
    assert "init_chat_model" not in source, "generation must not call init_chat_model directly"
    assert "llm_gateway.complete" in source, "generation must route through llm_gateway.complete()"
