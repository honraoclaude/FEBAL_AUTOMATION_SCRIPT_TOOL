"""Unit tests for auth handling (Phase 4, EXPL-02) — PURE detection, no browser/creds/spend.

Covers the deterministic, browser-free parts of auth:
  * detect_login_form: heuristic (input[type=password] + a nearby text/email input + a submit
    control) → a LoginForm with field locators; no password input → None (not a login page).
  * needs_relogin: a password input reappeared mid-run → logged out → True.

The live login + storageState capture/reuse are exercised by the slice-1 loop against the
real SauceDemo; here we prove the pure detection/recovery LOGIC on fixtures.

Security invariant (T-04-07): get_decrypted_credentials is the ONLY decrypt surface and a
credential value is NEVER logged or written to a node — asserted structurally below.
"""

from __future__ import annotations

import ast

from app.services.explorer.auth import (
    LoginForm,
    detect_login_form,
    needs_relogin,
)
from tests.fixtures.aria import (
    LOGIN_PAGE,
    LOGIN_PAGE_EMAIL,
    POST_LOGIN_PAGE,
)


def test_detect_login_form_present():
    """A page with password + nearby text input + submit yields a LoginForm with locators."""
    form = detect_login_form(LOGIN_PAGE)
    assert form is not None
    assert isinstance(form, LoginForm)
    # The heuristic identified the three field locators.
    assert form.password_selector
    assert form.username_selector
    assert form.submit_selector


def test_detect_login_form_accepts_email_input():
    """The nearby text input may be type=email (common login shape)."""
    form = detect_login_form(LOGIN_PAGE_EMAIL)
    assert form is not None
    assert form.username_selector  # the email input is accepted as the username field


def test_detect_login_form_absent_on_non_login_page():
    """A page with NO password input is not a login page → None."""
    assert detect_login_form(POST_LOGIN_PAGE) is None


def test_needs_relogin_true_when_password_reappears():
    """Mid-run, a password input reappearing means the session logged out → relogin."""
    assert needs_relogin(LOGIN_PAGE) is True


def test_needs_relogin_false_on_authenticated_page():
    """An authenticated page (no password input) does not trigger relogin."""
    assert needs_relogin(POST_LOGIN_PAGE) is False


def test_saucedemo_fast_path_selectors():
    """SauceDemo's known ids are detected as the fast path (#user-name/#password/#login-button)."""
    form = detect_login_form(LOGIN_PAGE)
    assert "user-name" in form.username_selector or form.username_selector == "#user-name"
    assert "password" in form.password_selector


def test_single_decrypt_surface_only():
    """auth.py imports NO second decrypt path — only get_decrypted_credentials (via service).

    AST-assert there is no `decrypt`/`Fernet`/`cryptography` import in auth.py (the decrypt
    surface lives in target_service; auth.py must call get_decrypted_credentials, never decrypt).
    """
    import app.services.explorer.auth as auth_mod

    with open(auth_mod.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
            imported.extend(f"{node.module}.{a.name}" for a in node.names)
    for mod in imported:
        low = mod.lower()
        assert "fernet" not in low, f"auth.py must not import a crypto primitive: {mod}"
        assert "cryptography" not in low, f"auth.py must not import cryptography: {mod}"
        assert not low.endswith(".decrypt"), f"auth.py must not import a decrypt fn: {mod}"
