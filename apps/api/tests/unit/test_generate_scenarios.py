"""Unit: generate_scenarios (GEN-01 / GEN-03 / D-07). Mocked gateway + fake driver, no keys.

Covers: the mocked-gateway happy path (draft row written, status draft), the two gate-failure
paths (malformed Gherkin + vacuous Then → GenerationError, NO row), and the no-key fallback
(gateway raises → a deterministic minimal valid+resolvable draft is written).
"""

import json
from decimal import Decimal

import pytest

from app.schemas.llm import LLMResult
from app.services import generation
from app.services.gates.gherkin_lint import GenerationError
from tests.fixtures.kg_scenarios import INVENTORY_FP, INVENTORY_PAGE_DETAIL, fake_driver

_RUN_ID = "gen-run-1"

# A single mined flow whose terminal page is the fixture inventory page (resolves in the gate).
_FLOW = {
    "id": "flow-0",
    "name": "Add to cart",
    "risk_tier": "high",
    "step_count": 2,
    "node_fps": ["fp-login", INVENTORY_FP],
}

_VALID_GHERKIN = (
    "Feature: Add to cart\n"
    "  Scenario: Add an item\n"
    "    Given the inventory page\n"
    "    When the user adds an item\n"
    "    Then the inventory page is shown\n"
)


class _FakeScenario:
    def __init__(self, sid):
        self.id = sid


@pytest.fixture
def patched_generation(monkeypatch):
    """Patch the KG reads + driver + create_scenario so generate_scenarios runs with no neo4j/DB.

    Returns a controller exposing `.created` (the captured create_scenario kwargs) and a
    `.set_complete(fn)` to install a fake gateway complete().
    """
    drv = fake_driver()
    created: list[dict] = []

    async def _fake_flows_source(*, driver=None):  # noqa: ANN001
        return {"nodes": {}, "edges": []}

    async def _fake_build_flows(graph, run_id, *, weights=None):  # noqa: ANN001
        return [_FLOW]

    async def _fake_page_detail(fingerprint, *, driver=None):  # noqa: ANN001
        return INVENTORY_PAGE_DETAIL if fingerprint == INVENTORY_FP else None

    async def _fake_create_scenario(db, **kwargs):  # noqa: ANN001
        created.append(kwargs)
        return _FakeScenario(len(created))

    monkeypatch.setattr(generation, "get_neo4j", lambda: drv)
    monkeypatch.setattr(generation, "build_flows", _fake_build_flows)

    import app.services.kg.reader as reader

    monkeypatch.setattr(reader, "flows_source", _fake_flows_source)
    monkeypatch.setattr(reader, "page_detail", _fake_page_detail)
    monkeypatch.setattr(
        generation.scenario_service, "create_scenario", _fake_create_scenario
    )

    class Controller:
        def __init__(self):
            self.created = created
            self.driver = drv

        def set_complete(self, fn):
            monkeypatch.setattr(generation.llm_gateway, "complete", fn)

        def raise_complete(self, exc):
            async def _raiser(db, messages, **kwargs):  # noqa: ANN001
                raise exc

            monkeypatch.setattr(generation.llm_gateway, "complete", _raiser)

    ctl = Controller()
    return ctl


def _result(content):
    return LLMResult(
        content=content, input_tokens=10, output_tokens=5, cost_usd=Decimal("0"),
        cache_hit=False, provider="fake", model="fake:test", run_id=_RUN_ID,
        operation_type="generate.bdd",
    )


async def test_happy_path_writes_draft_row(patched_generation):
    payload = {
        "gherkin": _VALID_GHERKIN,
        "then_refs": [
            {"then_text": "the inventory page is shown", "kind": "page",
             "ref": {"page_fingerprint": INVENTORY_FP}},
        ],
    }

    async def _complete(db, messages, **kwargs):  # noqa: ANN001
        return _result(json.dumps(payload))

    patched_generation.set_complete(_complete)
    ids = await generation.generate_scenarios(db=None, run_id=_RUN_ID)
    assert ids == [1]
    assert len(patched_generation.created) == 1
    row = patched_generation.created[0]
    assert row["run_id"] == _RUN_ID
    assert row["flow_id"] == "flow-0"
    assert row["gherkin_text"] == _VALID_GHERKIN


async def test_malformed_gherkin_raises_and_writes_no_row(patched_generation):
    payload = {"gherkin": "not gherkin {{{", "then_refs": [
        {"then_text": "x", "kind": "page", "ref": {"page_fingerprint": INVENTORY_FP}},
    ]}

    async def _complete(db, messages, **kwargs):  # noqa: ANN001
        return _result(json.dumps(payload))

    patched_generation.set_complete(_complete)
    with pytest.raises(GenerationError):
        await generation.generate_scenarios(db=None, run_id=_RUN_ID)
    assert patched_generation.created == []


async def test_vacuous_then_raises_and_writes_no_row(patched_generation):
    # A Then whose page ref does NOT resolve → vacuous → GenerationError, no row.
    payload = {"gherkin": _VALID_GHERKIN, "then_refs": [
        {"then_text": "ghost", "kind": "page", "ref": {"page_fingerprint": "fp-nope"}},
    ]}

    async def _complete(db, messages, **kwargs):  # noqa: ANN001
        return _result(json.dumps(payload))

    patched_generation.set_complete(_complete)
    with pytest.raises(GenerationError):
        await generation.generate_scenarios(db=None, run_id=_RUN_ID)
    assert patched_generation.created == []


async def test_no_key_fallback_writes_resolvable_draft(patched_generation):
    # Gateway raises a provider/auth error (empty-key path) → deterministic minimal pair.
    patched_generation.raise_complete(RuntimeError("provider auth error: no API key"))
    ids = await generation.generate_scenarios(db=None, run_id=_RUN_ID)
    assert ids == [1]
    row = patched_generation.created[0]
    # The fallback's single Then asserts the flow's terminal page (fp-inventory) — resolvable.
    assert row["then_refs"][0]["kind"] == "page"
    assert row["then_refs"][0]["ref"]["page_fingerprint"] == INVENTORY_FP
    # And the fallback Gherkin is valid (it passed validate_gherkin to be persisted).
    assert "Feature:" in row["gherkin_text"]
