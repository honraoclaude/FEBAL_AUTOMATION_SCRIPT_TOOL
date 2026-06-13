"""Wave 0 test scaffolding (01-VALIDATION.md) + plan 01-03 auth fixtures.

D-02: tests are FUNCTIONAL — they hit the RUNNING stack over live HTTP with
real Postgres/Redis. No ASGITransport in-process shortcut, no DB session
fixtures that bypass HTTP.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

# Fallback: load repo-root .env (same values the stack was seeded with) without
# overriding anything already exported in the environment.
_REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPO_ROOT / ".env", override=False)

# Host-facing API port is 8001 (8000 is held by another local project's container)
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8001")
WEB_BASE = os.environ.get("WEB_BASE_URL", "http://localhost:3000")

# Admin credentials the stack was seeded with (D-03)
ADMIN_EMAIL = os.environ["ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]


def _host_dsn() -> str:
    """DATABASE_URL rewritten for host-side asyncpg (no +asyncpg, localhost not 'postgres')."""
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


def pytest_collection_modifyitems(items: list) -> None:
    """Run all functional (pytest-asyncio) tests before any e2e (Playwright) tests.

    `uv run pytest tests` collects both suites into ONE process. pytest-asyncio
    (functional) drives an asyncio event loop; pytest-playwright (e2e) drives its
    own. If pytest's default file order interleaves them, an async functional
    fixture can tear down while Playwright's loop is still running, raising
    "Cannot run the event loop while another loop is running" / "Runner is closed".

    Sorting e2e last makes the two loop regimes strictly sequential within the
    single process, so the canonical one-command full-suite run is green. Tests
    keyed by path: anything under tests/e2e/ sorts after everything else; order is
    otherwise stable.
    """
    items.sort(key=lambda item: 1 if (os.sep + "e2e" + os.sep) in str(item.fspath) else 0)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Live-HTTP client against the running API (compose or hybrid host mode)."""
    async with httpx.AsyncClient(base_url=API_BASE) as c:
        yield c


@pytest.fixture
async def authed_client() -> AsyncIterator[httpx.AsyncClient]:
    """Client that has logged in as the seeded admin and holds the auth cookies."""
    async with httpx.AsyncClient(base_url=API_BASE) as c:
        r = await c.post(
            "/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
        yield c


@pytest.fixture
async def clean_targets() -> AsyncIterator[None]:
    """Truncate the targets table after a test (no-op until plan 01-05 creates it).

    Request explicitly (or mark autouse in a module) in tests that write targets.
    """
    yield
    import asyncpg

    conn = await asyncpg.connect(_host_dsn())
    try:
        exists = await conn.fetchval("SELECT to_regclass('public.targets') IS NOT NULL")
        if exists:
            await conn.execute("TRUNCATE TABLE targets RESTART IDENTITY CASCADE")
    finally:
        await conn.close()
