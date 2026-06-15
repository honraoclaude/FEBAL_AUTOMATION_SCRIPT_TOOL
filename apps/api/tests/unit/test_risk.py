"""Pure risk-classifier + origin-allowlist tests (EXPL-07/08, D-03/D-04) — no stack, no spend.

The safety layer is PURE CODE — these tables are the contract the act gate enforces BEFORE
any click/goto. is_destructive is a deny-list match (sandbox lifts the deny); is_off_origin
is an allowlist membership check on the URL origin.
"""

import pytest

from app.services.explorer.risk import DENY_VERBS, is_destructive, is_off_origin


@pytest.mark.parametrize(
    "label",
    [
        "Delete account",
        "Remove item",
        "Destroy workspace",
        "Send message",
        "Pay now",
        "Purchase",
        "Checkout",
        "Submit order",
        "Place order",
        "Logout",
        "Sign out",
        "Cancel subscription",
        "Deactivate user",
        "Wipe data",
        "Reset password",
    ],
)
def test_deny_verbs_are_destructive_on_non_sandbox(label):
    """Every deny verb in the label trips is_destructive on a non-sandbox target."""
    assert is_destructive({"label": label}, sandbox=False) is True


@pytest.mark.parametrize(
    "label",
    ["Home", "View products", "Add to cart", "Go to dashboard", "Read more", "About us"],
)
def test_safe_verbs_are_allowed(label):
    """Safe navigation/read actions match no deny verb (default-allow)."""
    assert is_destructive({"label": label}, sandbox=False) is False


def test_deny_verb_in_confirm_text_is_caught():
    """A benign label with a destructive confirm dialog still trips the deny-list."""
    action = {"label": "OK", "confirm_text": "This will permanently delete your account"}
    assert is_destructive(action, sandbox=False) is True


def test_sandbox_lifts_the_deny():
    """A restorable sandbox target lifts the deny — the same destructive action is allowed (D-03)."""
    action = {"label": "Delete account", "confirm_text": "Are you sure?"}
    assert is_destructive(action, sandbox=False) is True
    assert is_destructive(action, sandbox=True) is False


def test_deny_list_is_the_research_set():
    """The deny-list is exactly the RESEARCH canonical set (frozen, no LLM)."""
    assert "delete" in DENY_VERBS and "submit order" in DENY_VERBS
    assert isinstance(DENY_VERBS, frozenset)


def test_off_origin_url_is_refused():
    """A URL whose origin is not in the allowlist is off-origin (refused, D-04)."""
    allow = ["https://www.saucedemo.com"]
    assert is_off_origin("https://evil.example.com/steal", allow) is True


def test_in_allowlist_url_is_allowed():
    """A URL on an allowlisted origin (incl. the base_url origin) is in-scope, any path/query."""
    allow = ["https://www.saucedemo.com"]
    assert is_off_origin("https://www.saucedemo.com/inventory.html?x=1", allow) is False


def test_origin_comparison_ignores_path_and_is_case_insensitive():
    """Allowlist membership compares scheme://host[:port], case-insensitively, ignoring path."""
    allow = ["https://WWW.SauceDemo.com/login"]  # allowlist entry carries a path + mixed case
    assert is_off_origin("https://www.saucedemo.com/cart.html", allow) is False


def test_relative_or_garbage_url_is_off_origin():
    """A URL with no resolvable scheme+host is treated as off-origin (fail-closed)."""
    assert is_off_origin("/relative/path", ["https://www.saucedemo.com"]) is True
    assert is_off_origin("not a url", ["https://www.saucedemo.com"]) is True


def test_empty_allowlist_refuses_everything():
    """An empty/None allowlist refuses every navigation (fail-closed)."""
    assert is_off_origin("https://www.saucedemo.com/", []) is True
    assert is_off_origin("https://www.saucedemo.com/", None) is True
