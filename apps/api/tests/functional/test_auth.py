"""D-02 functional coverage of the auth slice (PLAT-03) — live stack over HTTP only.

Behaviors pinned here are the literal content of the VALIDATION Per-Task
Verification row 01-03-T1/T2: httpOnly cookies on login, uniform 401 (no user
enumeration), cookie-only /me, refresh rotation, logout clearing, and the
refresh-token-as-access-token type-claim gate.
"""

import os

import httpx
import pytest

pytestmark = pytest.mark.functional

# conftest.py (imported before test modules) has already loaded the repo-root
# .env fallback, so these are guaranteed present here.
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8001")


def _set_cookie_headers(response: httpx.Response, name: str) -> list[str]:
    """All Set-Cookie headers for the named cookie."""
    return [
        h for h in response.headers.get_list("set-cookie") if h.startswith(f"{name}=")
    ]


def _cookie_value(header: str) -> str:
    """Value portion of a `name=value; attr; ...` Set-Cookie header."""
    return header.split(";", 1)[0].split("=", 1)[1]


async def test_login_sets_httponly_cookies(client):
    r = await client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert r.status_code == 200

    for name in ("access_token", "refresh_token"):
        headers = _set_cookie_headers(r, name)
        assert headers, f"no Set-Cookie issued for {name}"
        lowered = headers[0].lower()
        assert "httponly" in lowered, f"{name} cookie is not HttpOnly: {headers[0]}"
        assert "samesite=lax" in lowered, f"{name} cookie is not SameSite=lax: {headers[0]}"

    # The password value must never appear in the response body
    assert ADMIN_PASSWORD not in r.text


async def test_login_wrong_password_401(client):
    r = await client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": "definitely-not-the-password"},
    )
    assert r.status_code == 401


async def test_login_unknown_email_401(client):
    r_unknown = await client.post(
        "/api/auth/login",
        json={"email": "nobody@example.invalid", "password": "whatever-password"},
    )
    assert r_unknown.status_code == 401

    r_wrong = await client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": "definitely-not-the-password"},
    )
    assert r_wrong.status_code == 401

    # Uniform error: unknown-email and wrong-password bodies are byte-identical
    # (no user enumeration via response differences).
    assert r_unknown.content == r_wrong.content


async def test_me_requires_auth(client, authed_client):
    # No cookies -> 401
    r_anon = await client.get("/api/auth/me")
    assert r_anon.status_code == 401

    # Cookie-bearing client -> 200 with the admin identity
    r_me = await authed_client.get("/api/auth/me")
    assert r_me.status_code == 200
    assert r_me.json()["email"] == ADMIN_EMAIL


async def test_refresh_rotates_access():
    async with httpx.AsyncClient(base_url=API_BASE) as client:
        r_login = await client.post(
            "/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert r_login.status_code == 200
        original_access = _cookie_value(_set_cookie_headers(r_login, "access_token")[0])

        r_refresh = await client.post("/api/auth/refresh")
        assert r_refresh.status_code == 200

        new_headers = _set_cookie_headers(r_refresh, "access_token")
        assert new_headers, "refresh did not issue a new access_token cookie"
        new_access = _cookie_value(new_headers[0])
        assert new_access != original_access, "refresh must rotate the access token"


async def test_logout_clears_cookies(authed_client):
    r = await authed_client.post("/api/auth/logout")
    assert r.status_code == 200

    for name in ("access_token", "refresh_token"):
        headers = _set_cookie_headers(r, name)
        assert headers, f"logout did not issue a clearing Set-Cookie for {name}"
        lowered = headers[0].lower()
        assert "max-age=0" in lowered or "expires=" in lowered, (
            f"logout Set-Cookie does not expire {name}: {headers[0]}"
        )

    # The same client (cookies now cleared from its jar) is unauthenticated again
    r_me = await authed_client.get("/api/auth/me")
    assert r_me.status_code == 401


async def test_refresh_token_rejected_as_access():
    # Log in, capture the refresh token value from its Set-Cookie header
    async with httpx.AsyncClient(base_url=API_BASE) as client:
        r_login = await client.post(
            "/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert r_login.status_code == 200
        refresh_value = _cookie_value(_set_cookie_headers(r_login, "refresh_token")[0])

    # Present the refresh token in the access_token cookie slot: the `type`
    # claim gate in get_current_user must reject it.
    async with httpx.AsyncClient(
        base_url=API_BASE, cookies={"access_token": refresh_value}
    ) as forged:
        r_me = await forged.get("/api/auth/me")
        assert r_me.status_code == 401
