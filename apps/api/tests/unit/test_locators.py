"""Pure locator-chain ordering + history tests (EXPL-09) — no browser, no spend.

The async extract_locator_chain only reads attributes off a handle then delegates to the pure
build_locator_chain; these tests exercise that pure ordering + the history merge on fixtures.
"""

from app.services.explorer.locators import build_locator_chain, merge_locator_history


def test_full_priority_order():
    """All attributes present -> chain in data-testid → aria-label → role → text → xpath order."""
    attrs = {
        "data-testid": "add-to-cart",
        "aria-label": "Add to cart",
        "role": "button",
        "text": "Add to cart",
        "xpath": "/html/body/button[1]",
    }
    chain = build_locator_chain(attrs)
    strategies = [c["strategy"] for c in chain]
    assert strategies == ["data-testid", "aria-label", "role", "text", "xpath"]
    # The role tier carries the accessible name.
    role_entry = next(c for c in chain if c["strategy"] == "role")
    assert role_entry["name"] == "Add to cart"


def test_partial_role_and_text_only_plus_xpath():
    """Only role+text -> just those tiers + xpath (absent tiers omitted)."""
    attrs = {"role": "link", "text": "Products", "xpath": "/html/body/a[2]"}
    chain = build_locator_chain(attrs)
    strategies = [c["strategy"] for c in chain]
    assert strategies == ["role", "text", "xpath"]


def test_data_test_alias_produces_data_testid_tier():
    """SauceDemo exposes data-test (NOT data-testid) — both names feed the data-testid tier."""
    attrs = {"data-test": "username", "role": "textbox", "xpath": "//input[1]"}
    chain = build_locator_chain(attrs)
    tid = next(c for c in chain if c["strategy"] == "data-testid")
    assert tid["value"] == "username"


def test_data_testid_wins_over_data_test_when_both_present():
    """When both attributes exist, data-testid is preferred for the tier value."""
    attrs = {"data-testid": "canonical", "data-test": "legacy"}
    chain = build_locator_chain(attrs)
    assert chain[0] == {"strategy": "data-testid", "value": "canonical"}


def test_text_is_truncated_to_80_chars():
    """A long visible text is truncated (token/identity hygiene)."""
    attrs = {"text": "x" * 200}
    chain = build_locator_chain(attrs)
    text_entry = next(c for c in chain if c["strategy"] == "text")
    assert len(text_entry["value"]) == 80


def test_empty_attrs_yields_empty_chain():
    """No attributes and no xpath -> empty chain (nothing to locate by)."""
    assert build_locator_chain({}) == []


def test_history_appends_not_overwrites():
    """A re-observed element APPENDS a step-stamped snapshot; prior entries are preserved."""
    chain_v1 = [{"strategy": "data-testid", "value": "add-to-cart"}]
    chain_v2 = [{"strategy": "data-testid", "value": "add-to-cart-v2"}]

    h1 = merge_locator_history([], chain_v1, step=0)
    assert len(h1) == 1 and h1[0]["step"] == 0 and h1[0]["chain"] == chain_v1

    h2 = merge_locator_history(h1, chain_v2, step=3)
    assert len(h2) == 2
    assert h2[0]["chain"] == chain_v1  # prior snapshot preserved
    assert h2[1]["step"] == 3 and h2[1]["chain"] == chain_v2


def test_history_merge_does_not_mutate_input():
    """merge_locator_history is pure — the existing list is not mutated in place."""
    existing = [{"step": 0, "chain": []}]
    merge_locator_history(existing, [{"strategy": "text", "value": "x"}], step=1)
    assert len(existing) == 1  # caller's list untouched
