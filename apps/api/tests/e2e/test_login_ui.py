"""Playwright e2e for the login flow (plan 01-04 — VALIDATION row PLAT-03/e2e).

Runs on the HOST against the live web tier (WEB_BASE, default
http://localhost:3000) per RESEARCH A7. Touches every 01-UI-SPEC §1 login
state (default / submitting / error) plus the D-04 refresh-resume path.

Credentials come from the environment (ADMIN_EMAIL / ADMIN_PASSWORD — the
values the stack was seeded with, loaded from the repo-root .env by
tests/conftest.py). Zero hardcoded credentials in this file.
"""

import os

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

WEB_BASE = os.environ.get("WEB_BASE_URL", "http://localhost:3000")
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]


def _login(page: Page) -> None:
    """Drive the login form with the seeded admin credentials."""
    page.goto(f"{WEB_BASE}/login")
    page.get_by_label("Email").fill(ADMIN_EMAIL)
    page.get_by_label("Password").fill(ADMIN_PASSWORD)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url("**/targets")


def test_unauthenticated_redirects_to_login(page: Page) -> None:
    """proxy.ts bounces cookie-less visits to protected routes to /login."""
    page.goto(f"{WEB_BASE}/targets")
    page.wait_for_url("**/login")
    assert page.url.rstrip("/").endswith("/login")


def test_login_happy_path(page: Page) -> None:
    """Walking skeleton: UI -> rewrite -> API -> Postgres -> cookie -> /targets."""
    _login(page)
    expect(
        page.get_by_role("heading", name="Target Applications")
    ).to_be_visible()


def test_login_bad_password_shows_uniform_error(page: Page) -> None:
    """UI-SPEC §1 error state: exact uniform message, email kept, password cleared."""
    page.goto(f"{WEB_BASE}/login")
    page.get_by_label("Email").fill(ADMIN_EMAIL)
    page.get_by_label("Password").fill("definitely-not-the-password")
    page.get_by_role("button", name="Log in").click()

    expect(
        page.get_by_text("Invalid email or password.", exact=True)
    ).to_be_visible()
    expect(page.get_by_label("Email")).to_have_value(ADMIN_EMAIL)
    expect(page.get_by_label("Password")).to_have_value("")


def test_logout_returns_to_login(page: Page) -> None:
    """Sidebar 'Log out' clears the session; protected routes bounce again."""
    _login(page)
    page.get_by_role("button", name="Log out").click()
    page.wait_for_url("**/login")

    page.goto(f"{WEB_BASE}/targets")
    page.wait_for_url("**/login")
    assert page.url.rstrip("/").endswith("/login")


def test_expired_access_cookie_resumes_via_refresh(page: Page) -> None:
    """D-04 7-day session: an expired access cookie (refresh cookie intact)
    resumes via the login page's silent refresh — no credential re-entry.

    Simulates the 30-min access-token expiry by clearing only the
    access_token cookie; the 7-day refresh_token cookie (path=/api/auth)
    survives. proxy.ts bounces /targets -> /login, the silent refresh-on-mount
    probe mints a new access cookie, and router.replace lands on /targets.
    """
    _login(page)
    page.context.clear_cookies(name="access_token")

    page.goto(f"{WEB_BASE}/targets")
    page.wait_for_url("**/targets")
    expect(
        page.get_by_role("heading", name="Target Applications")
    ).to_be_visible()
