"""Unit proof of the ast-validated, key-targeted page-object locator rewrite (HEAL-03, T-08-10).

rewrite_page_object_locator is the script-repo-update half of heal-as-commit (D-03): a SAFE
line-targeted replace keyed by the page-object attr name (the template guarantees one
`self.<attr> = page.locator(<literal>)` line per attr), ast-validated before return. These tests
prove the behavior contract on a fixture page-object source — no DB, no neo4j, no keys.
"""

from __future__ import annotations

import ast

import pytest

from app.services.healing.ingest import rewrite_page_object_locator

# A minimal multi-attr page object mirroring page_object.py.j2's rendered shape (double-quoted
# tojson literals, one self.<attr> = page.locator(...) per attr).
_FIXTURE = '''\
"""Page Object: InventoryPage (AUTO-GENERATED)."""

from playwright.sync_api import Page, expect


class InventoryPage:
    _chains = {"button_add_to_cart": [{"strategy": "data-testid", "value": "add-to-cart-sauce-labs-backpack"}]}

    def __init__(self, page: Page) -> None:
        self.page = page
        self.button_add_to_cart = page.locator("add-to-cart-sauce-labs-backpack")
        self.input_username = page.locator("user-name")
        self.button_login = page.locator("login-button")
'''


def test_rewrite_swaps_only_the_keyed_attr_literal() -> None:
    """The keyed attr's literal is replaced; the other attrs' literals are untouched."""
    new = rewrite_page_object_locator(
        _FIXTURE,
        element_key="button_add_to_cart",
        new_selector='[data-test="add-to-cart-btn"]',
    )
    assert 'self.button_add_to_cart = page.locator("[data-test=\\"add-to-cart-btn\\"]")' in new
    # Other attrs' literals are unchanged.
    assert 'self.input_username = page.locator("user-name")' in new
    assert 'self.button_login = page.locator("login-button")' in new
    # The old literal is gone from the keyed line (but the _chains data dict line is untouched).
    assert 'self.button_add_to_cart = page.locator("add-to-cart-sauce-labs-backpack")' not in new


def test_rewrite_result_always_ast_parses() -> None:
    """The rewritten source is valid Python (ast.parse succeeds)."""
    new = rewrite_page_object_locator(
        _FIXTURE, element_key="input_username", new_selector="username-field"
    )
    ast.parse(new)  # must not raise


def test_rewrite_does_not_touch_the_chains_data_dict() -> None:
    """The _chains DATA dict literal (same value string) is NOT a rewrite target (attr-anchored)."""
    new = rewrite_page_object_locator(
        _FIXTURE,
        element_key="button_add_to_cart",
        new_selector="healed-selector",
    )
    # The _chains dict still carries the ORIGINAL value — only the page.locator(...) sink changed.
    assert '"value": "add-to-cart-sauce-labs-backpack"' in new


def test_unknown_key_is_a_noop() -> None:
    """An element_key with no matching line returns the source UNCHANGED (no crash)."""
    new = rewrite_page_object_locator(
        _FIXTURE, element_key="button_does_not_exist", new_selector="whatever"
    )
    assert new == _FIXTURE


def test_special_chars_in_selector_stay_valid_python() -> None:
    """A selector with quotes/backslashes is escaped (json.dumps) so the result still parses."""
    tricky = 'xpath=//button[@aria-label="Add \\"x\\""]'
    new = rewrite_page_object_locator(
        _FIXTURE, element_key="button_login", new_selector=tricky
    )
    ast.parse(new)  # escaping kept it valid
    # The healed value round-trips through the literal.
    tree = ast.parse(new)
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "locator"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    assert tricky in found


def test_rewrite_raises_when_result_would_be_invalid_python() -> None:
    """A source whose targeted line cannot survive a literal swap raises (never returns broken)."""
    # Construct a source where the surrounding context is already broken so the post-rewrite
    # ast.parse fails — proves the guard rejects rather than returning mutated source.
    broken = (
        "class P:\n"
        "    def __init__(self, page):\n"
        "        self.btn = page.locator(\"old\")\n"
        "        def  # <- dangling, makes the module unparseable after any edit\n"
    )
    with pytest.raises(SyntaxError):
        rewrite_page_object_locator(broken, element_key="btn", new_selector="new")
