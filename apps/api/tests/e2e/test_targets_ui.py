"""Playwright e2e for the target registry UI (plan 01-06 — VALIDATION row
PLAT-01/e2e).

Runs on the HOST against the live web tier (WEB_BASE, default
http://localhost:3000), the same pattern as test_login_ui.py. Each test logs in
through the UI with the seeded admin (ADMIN_EMAIL / ADMIN_PASSWORD from the
repo-root .env via conftest) and registers targets with uuid-unique names, so
the suite is re-runnable without manual cleanup.

The headline guarantee (D-06 / threat T-01-22): a password typed at registration
NEVER appears anywhere in the edit dialog or page body — credentials are
write-only and the API response is credential-free by construction.
"""

import os
import uuid

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

WEB_BASE = os.environ.get("WEB_BASE_URL", "http://localhost:3000")
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]

MASK_HELPER = "Stored encrypted and never shown. Enter new values to replace them."


def _login(page: Page) -> None:
    """Drive the login form with the seeded admin credentials, land on /targets."""
    page.goto(f"{WEB_BASE}/login")
    page.get_by_label("Email").fill(ADMIN_EMAIL)
    page.get_by_label("Password").fill(ADMIN_PASSWORD)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url("**/targets")


def _unique_name() -> str:
    return f"e2e-target-{uuid.uuid4().hex[:12]}"


def _register(page: Page, name: str, *, password: str = "s3cret-pw") -> None:
    """Open the register dialog, fill it, submit; returns once the row exists."""
    page.get_by_role("button", name="Register target").first.click()
    dialog = page.get_by_role("dialog")
    dialog.get_by_label("Name", exact=True).fill(name)
    dialog.get_by_label("Base URL", exact=True).fill("https://example.com")
    dialog.get_by_label("Username", exact=True).fill("explorer")
    dialog.get_by_label("Password", exact=True).fill(password)
    dialog.get_by_role("button", name="Register target").click()
    # Dialog closes and the new row appears.
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(page.get_by_role("cell", name=name, exact=True)).to_be_visible()


def test_register_target_via_dialog(page: Page) -> None:
    """Register through the dialog -> toast, row visible with Active badge + mono URL."""
    _login(page)
    name = _unique_name()
    _register(page, name)

    # Success toast (success-only; bottom-right).
    expect(page.get_by_text("Target registered")).to_be_visible()

    row = page.get_by_role("row").filter(has_text=name)
    expect(row.get_by_text("Active", exact=True)).to_be_visible()
    # Base URL cell uses Geist Mono (UI-SPEC monospace rule). The API normalizes
    # the URL via Pydantic HttpUrl (adds a trailing slash), so match by prefix.
    url_cell = row.get_by_text("https://example.com")
    expect(url_cell).to_be_visible()
    assert "font-mono" in (url_cell.get_attribute("class") or "")


def test_edit_dialog_masks_credentials(page: Page) -> None:
    """Edit mode never prefils credentials; the registration password is absent
    from the entire page body (D-06 / T-01-22)."""
    _login(page)
    name = _unique_name()
    secret = f"pw-{uuid.uuid4().hex}"
    _register(page, name, password=secret)

    row = page.get_by_role("row").filter(has_text=name)
    row.get_by_role("button", name=f"Actions for {name}").click()
    page.get_by_role("menuitem", name="Edit").click()

    dialog = page.get_by_role("dialog")
    # Credentials are EMPTY with the masked placeholder + helper copy.
    expect(dialog.get_by_label("Username", exact=True)).to_have_value("")
    expect(dialog.get_by_label("Password", exact=True)).to_have_value("")
    expect(dialog.get_by_label("Username", exact=True)).to_have_attribute(
        "placeholder", "••••••••"
    )
    expect(dialog.get_by_text(MASK_HELPER)).to_be_visible()

    # The registration password must not appear anywhere in the page.
    expect(page.locator("body")).not_to_contain_text(secret)

    # Change the name only -> Save changes -> row updates.
    new_name = f"{name}-edited"
    dialog.get_by_label("Name", exact=True).fill(new_name)
    dialog.get_by_role("button", name="Save changes").click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(page.get_by_role("cell", name=new_name, exact=True)).to_be_visible()
    # Still no plaintext password after the round-trip.
    expect(page.locator("body")).not_to_contain_text(secret)


def test_deactivate_flow(page: Page) -> None:
    """Row menu -> Deactivate -> confirm -> row muted with Inactive badge;
    the menu then offers Reactivate."""
    _login(page)
    name = _unique_name()
    _register(page, name)

    row = page.get_by_role("row").filter(has_text=name)
    row.get_by_role("button", name=f"Actions for {name}").click()
    page.get_by_role("menuitem", name="Deactivate").click()

    # Confirmation copy visible.
    expect(page.get_by_text(f"Deactivate {name}?")).to_be_visible()
    expect(
        page.get_by_text(
            "The platform will stop running against this target. Its history "
            "is kept and you can reactivate it later."
        )
    ).to_be_visible()
    page.get_by_role("button", name="Deactivate", exact=True).click()

    # Row turns muted with the Inactive badge.
    row = page.get_by_role("row").filter(has_text=name)
    expect(row.get_by_text("Inactive", exact=True)).to_be_visible()

    # Menu now offers Reactivate (not Deactivate).
    row.get_by_role("button", name=f"Actions for {name}").click()
    expect(page.get_by_role("menuitem", name="Reactivate")).to_be_visible()


def test_validation_errors_inline(page: Page) -> None:
    """Empty submit -> 'Name is required'; invalid URL -> exact URL error; no toast."""
    _login(page)
    page.get_by_role("button", name="Register target").first.click()
    dialog = page.get_by_role("dialog")

    # Submit empty.
    dialog.get_by_role("button", name="Register target").click()
    expect(dialog.get_by_text("Name is required")).to_be_visible()

    # Provide a name but an invalid URL.
    dialog.get_by_label("Name", exact=True).fill(_unique_name())
    dialog.get_by_label("Base URL", exact=True).fill("not-a-url")
    dialog.get_by_role("button", name="Register target").click()
    expect(
        dialog.get_by_text(
            "Enter a valid URL (including http:// or https://)"
        )
    ).to_be_visible()

    # No success toast was shown on a failed submit.
    expect(page.get_by_text("Target registered")).to_have_count(0)
