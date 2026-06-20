"""Freehand-selector AST gate + Element-Repository locator lookup (GEN-05a / D-05).

Deterministic, NO keys, NO neo4j. The selector-gate tests scan rendered source STRINGS (the
exact `.py` text codegen produces) and the locator test maps element-repository rows (a fake
driver) to page-object attributes. Together they enforce the locked invariant: EVERY locator
comes from the Phase-5 Element Repository by key; the LLM/template fills only non-locator slots
and NEVER a freehand selector literal in a spec/step module.

Detection contract under test:
  - In SPEC/STEP modules, a string-literal first arg to a selector sink
    (page.locator / get_by_role / get_by_text / get_by_test_id / get_by_label /
    get_by_placeholder, and page.fill/click/... with a CSS-string first arg) is a VIOLATION.
  - A raw CSS/XPath string CONSTANT anywhere in a spec/step module (regex fallback:
    ^#, ^., ^//, [attr=) is a VIOLATION.
  - A reference to a page-object ATTRIBUTE (self.login_button / page_obj.add_to_cart) is ALLOWED.
  - A literal locator inside a PAGE-OBJECT module is ALLOWED (the single sanctioned home), and
    `assert_page_object_literals_are_repo_sourced` fails when a page-object literal is NOT in
    the supplied repo chain entries.
  - page_object_locators maps each element key → its top-priority repo chain entry (fake driver);
    the value is repo-sourced, never invented.
"""

from __future__ import annotations

import pytest

from app.services.codegen.locators import page_object_locators
from app.services.gates.selector_gate import (
    SelectorGateError,
    assert_no_freehand_selectors,
    assert_page_object_literals_are_repo_sourced,
    scan_for_freehand_selectors,
)
from tests.fixtures.kg_scenarios import ADD_TO_CART_KEY, INVENTORY_FP


# --- Spec/step source fixtures (the rendered .py text the gate scans) --------------------

_STEP_WITH_LOCATOR_LITERAL = '''
from pytest_bdd import then


@then("the cart updates")
def cart_updates(page):
    page.locator("#foo").click()
'''

_STEP_WITH_GET_BY_ROLE_LITERAL = '''
from pytest_bdd import when


@when("the user logs in")
def login(page):
    page.get_by_role("button", name="Login").click()
'''

_STEP_WITH_GET_BY_TEST_ID_LITERAL = '''
from pytest_bdd import when


@when("the user adds an item")
def add(page):
    page.get_by_test_id("add-to-cart").click()
'''

_STEP_WITH_FILL_CSS_LITERAL = '''
from pytest_bdd import when


@when("the user types a name")
def fill(page):
    page.fill("#user-name", "standard_user")
'''

_STEP_WITH_RAW_CSS_CONSTANT = '''
LOGIN = "#login"
ITEM = ".x"
XP = "//div[@id='a']"
ATTR = "[data-x=1]"
'''

_STEP_CLEAN_PAGE_OBJECT_REFERENCES = '''
from pytest_bdd import given, when, then


@given("the inventory page")
def inventory(login_page):
    login_page.goto()


@when("the user adds an item")
def add(inventory_page):
    inventory_page.add_to_cart.click()


@then("the cart updates")
def assert_cart(self, inventory_page):
    inventory_page.assert_cart_badge()
'''


# --- Page-object source fixtures (literals ALLOWED here) ---------------------------------

_PAGE_OBJECT_WITH_REPO_LITERAL = '''
class InventoryPage:
    def __init__(self, page):
        self.page = page
        self.add_to_cart = page.locator("#add-to-cart")

    def assert_cart_badge(self):
        from playwright.sync_api import expect
        expect(self.add_to_cart).to_be_visible()
'''

_PAGE_OBJECT_WITH_FOREIGN_LITERAL = '''
class InventoryPage:
    def __init__(self, page):
        self.page = page
        self.add_to_cart = page.locator("#NOT-IN-REPO")
'''


# --- scan_for_freehand_selectors: spec/step VIOLATIONS ----------------------------------


@pytest.mark.parametrize(
    "source",
    [
        _STEP_WITH_LOCATOR_LITERAL,
        _STEP_WITH_GET_BY_ROLE_LITERAL,
        _STEP_WITH_GET_BY_TEST_ID_LITERAL,
        _STEP_WITH_FILL_CSS_LITERAL,
    ],
)
def test_selector_sink_literal_in_step_is_violation(source: str) -> None:
    violations = scan_for_freehand_selectors(source, is_page_object=False)
    assert violations, "expected a freehand-selector violation in a step module"


def test_raw_css_xpath_constants_in_step_are_violations() -> None:
    violations = scan_for_freehand_selectors(
        _STEP_WITH_RAW_CSS_CONSTANT, is_page_object=False
    )
    # All four raw CSS/XPath/attr constants must be caught by the regex fallback.
    assert len(violations) >= 4, violations


def test_page_object_attribute_reference_is_allowed() -> None:
    violations = scan_for_freehand_selectors(
        _STEP_CLEAN_PAGE_OBJECT_REFERENCES, is_page_object=False
    )
    assert violations == [], f"page-object references must not be flagged: {violations}"


# --- scan_for_freehand_selectors: page-object ALLOWANCE ---------------------------------


def test_literal_in_page_object_is_allowed() -> None:
    violations = scan_for_freehand_selectors(
        _PAGE_OBJECT_WITH_REPO_LITERAL, is_page_object=True
    )
    assert violations == [], f"page-object literals are the sanctioned home: {violations}"


def test_same_literal_rejected_in_step_but_allowed_in_page_object() -> None:
    assert scan_for_freehand_selectors(_PAGE_OBJECT_WITH_REPO_LITERAL, is_page_object=False)
    assert scan_for_freehand_selectors(_PAGE_OBJECT_WITH_REPO_LITERAL, is_page_object=True) == []


# --- assert_no_freehand_selectors (the codegen caller) -----------------------------------


def test_assert_no_freehand_selectors_raises_on_step_literal() -> None:
    with pytest.raises(SelectorGateError):
        assert_no_freehand_selectors(_STEP_WITH_LOCATOR_LITERAL, is_page_object=False)


def test_assert_no_freehand_selectors_passes_clean_step() -> None:
    assert_no_freehand_selectors(_STEP_CLEAN_PAGE_OBJECT_REFERENCES, is_page_object=False)


def test_assert_no_freehand_selectors_passes_page_object_literal() -> None:
    assert_no_freehand_selectors(_PAGE_OBJECT_WITH_REPO_LITERAL, is_page_object=True)


# --- assert_page_object_literals_are_repo_sourced ----------------------------------------


def test_page_object_literal_in_repo_chains_passes() -> None:
    # The literal "#add-to-cart" must equal a supplied repo chain entry.
    assert_page_object_literals_are_repo_sourced(
        _PAGE_OBJECT_WITH_REPO_LITERAL, repo_chains={"#add-to-cart"}
    )


def test_page_object_literal_not_in_repo_chains_fails() -> None:
    with pytest.raises(SelectorGateError):
        assert_page_object_literals_are_repo_sourced(
            _PAGE_OBJECT_WITH_FOREIGN_LITERAL, repo_chains={"#add-to-cart"}
        )


# --- page_object_locators: repo-sourced, never invented ----------------------------------


class _FakeRepoDriver:
    """A fake driver whose element_repository read yields one inventory element with a chain.

    Mirrors kg/reader.element_repository's deserialized output (chain = prioritized list of
    {strategy, value}); the gate must pick the TOP-priority chain entry per element.
    """

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.calls: list[str] = []

    def session(self):
        return _FakeRepoSession(self)


class _FakeRepoResult:
    def __init__(self, records: list[dict]):
        self._records = records

    def __aiter__(self):
        async def _gen():
            for rec in self._records:
                yield rec

        return _gen()


class _FakeRepoTx:
    def __init__(self, driver: "_FakeRepoDriver"):
        self._driver = driver

    async def run(self, cypher: str, **params):
        self._driver.calls.append(cypher)
        return _FakeRepoResult(self._driver._rows)


class _FakeRepoSession:
    def __init__(self, driver: "_FakeRepoDriver"):
        self._driver = driver

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute_read(self, tx_func):
        return await tx_func(_FakeRepoTx(self._driver))


def _repo_rows() -> list[dict]:
    # Raw rows as reader._read returns BEFORE element_repository deserializes chain_json.
    import json

    return [
        {
            "key": ADD_TO_CART_KEY,
            "role": "button",
            "label": "Add to cart",
            "chain_json": json.dumps(
                [
                    {"strategy": "css", "value": "#add-to-cart"},
                    {"strategy": "role", "value": "button"},
                ]
            ),
            "history_json": "[]",
            "page_fp": INVENTORY_FP,
            "page_url": "https://www.saucedemo.com/inventory.html",
            "first_seen": None,
            "last_verified": None,
        }
    ]


async def test_page_object_locators_uses_top_priority_repo_chain() -> None:
    driver = _FakeRepoDriver(_repo_rows())
    attrs = await page_object_locators(INVENTORY_FP, driver=driver)
    # Deterministic snake_case attr name from role+label; value = top chain entry (repo-sourced).
    assert attrs == {"button_add_to_cart": "#add-to-cart"}


async def test_page_object_locators_filters_to_page_fingerprint() -> None:
    rows = _repo_rows()
    rows.append(
        {
            "key": "fp-other#button:Foo",
            "role": "button",
            "label": "Foo",
            "chain_json": '[{"strategy": "css", "value": "#foo"}]',
            "history_json": "[]",
            "page_fp": "fp-other",
            "page_url": "https://example.test/other",
            "first_seen": None,
            "last_verified": None,
        }
    )
    driver = _FakeRepoDriver(rows)
    attrs = await page_object_locators(INVENTORY_FP, driver=driver)
    # Only the inventory-page element is returned (filtered by page fingerprint).
    assert attrs == {"button_add_to_cart": "#add-to-cart"}
