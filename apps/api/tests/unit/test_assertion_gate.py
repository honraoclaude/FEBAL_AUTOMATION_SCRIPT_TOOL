"""Unit: the structured Then→KG no-vacuous gate (GEN-03 / D-03) on a FAKE driver.

No neo4j, no keys. Covers all four vacuous classes + the edge_type-allow-list injection-safety
case, and asserts NO Cypher runs for an unknown kind / disallowed edge_type (via the fake
driver's call log).
"""

import pytest

from app.services.gates.assertion_gate import assert_non_vacuous, resolve_then_refs
from app.services.gates.gherkin_lint import GenerationError
from tests.fixtures.kg_scenarios import (
    THEN_REFS_ALL_RESOLVABLE,
    THEN_REFS_DISALLOWED_EDGE,
    THEN_REFS_EMPTY,
    THEN_REFS_NO_REF,
    THEN_REFS_UNKNOWN_KIND,
    THEN_REFS_UNRESOLVABLE,
    fake_driver,
)


async def test_all_resolvable_returns_empty():
    drv = fake_driver()
    unresolved = await resolve_then_refs(THEN_REFS_ALL_RESOLVABLE, driver=drv)
    assert unresolved == []
    # one query per Then (edge + element + page).
    assert len(drv.calls) == 3


async def test_then_with_no_ref_is_vacuous():
    drv = fake_driver()
    unresolved = await resolve_then_refs(THEN_REFS_NO_REF, driver=drv)
    assert unresolved == ["something good happens"]
    # No ref values → NO query built.
    assert drv.calls == []


async def test_unresolvable_ref_is_vacuous():
    drv = fake_driver()
    unresolved = await resolve_then_refs(THEN_REFS_UNRESOLVABLE, driver=drv)
    assert unresolved == ["the ghost page is shown"]
    # A query DID run (the page check) — it just resolved false.
    assert len(drv.calls) == 1


async def test_unknown_kind_is_vacuous_and_runs_no_cypher():
    drv = fake_driver()
    unresolved = await resolve_then_refs(THEN_REFS_UNKNOWN_KIND, driver=drv)
    assert unresolved == ["the vibe is correct"]
    assert drv.calls == []  # unknown kind → NO Cypher


async def test_disallowed_edge_type_is_vacuous_and_runs_no_cypher():
    # Injection safety: an edge_type outside {Creates,Updates,Deletes} → vacuous + NO query.
    drv = fake_driver()
    unresolved = await resolve_then_refs(THEN_REFS_DISALLOWED_EDGE, driver=drv)
    assert unresolved == ["the cart is owned"]
    assert drv.calls == []  # disallowed edge_type → NO Cypher built


async def test_zero_thens_is_vacuous():
    drv = fake_driver()
    unresolved = await resolve_then_refs(THEN_REFS_EMPTY, driver=drv)
    # Nothing to resolve → empty list, but assert_non_vacuous still rejects (no Thens).
    assert unresolved == []
    with pytest.raises(GenerationError):
        await assert_non_vacuous(THEN_REFS_EMPTY, driver=drv)


async def test_assert_non_vacuous_passes_when_all_resolve():
    drv = fake_driver()
    await assert_non_vacuous(THEN_REFS_ALL_RESOLVABLE, driver=drv)  # no raise


async def test_assert_non_vacuous_raises_on_unresolved():
    drv = fake_driver()
    with pytest.raises(GenerationError):
        await assert_non_vacuous(THEN_REFS_UNRESOLVABLE, driver=drv)
