"""Wave 0 test scaffolding (01-VALIDATION.md) + plan 01-03 auth fixtures.

D-02: tests are FUNCTIONAL — they hit the RUNNING stack over live HTTP with
real Postgres/Redis. No ASGITransport in-process shortcut, no DB session
fixtures that bypass HTTP.
"""

import asyncio
import os
import time
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


def _host_bolt_uri() -> str:
    """NEO4J_URI rewritten for host-side Bolt (in-cluster 'neo4j' host → localhost).

    Mirrors the redis host rewrite in tests/unit/conftest.py: the compose env points
    the api at `bolt://neo4j:7687`, but a host-run test reaches the same DB at
    `bolt://localhost:7687` (the 7687 port published by the neo4j service).
    """
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    return uri.replace("://neo4j:", "://localhost:")


@pytest.fixture
async def neo4j_session():
    """Host-side Bolt session against the neo4j graph profile (mark tests `graph`).

    Connects a SHORT-LIVED driver to bolt://localhost:7687 and yields one session for
    a downstream functional test to assert Page/NavigatesTo nodes; closes both on
    teardown. Only usable when neo4j is up (run under graph_mode, web stopped) — tests
    that use it MUST carry the `graph` marker. neo4j is imported lazily inside the
    fixture so importing this conftest never requires neo4j when the graph suite is
    not being run.
    """
    from neo4j import AsyncGraphDatabase

    driver = AsyncGraphDatabase.driver(
        _host_bolt_uri(),
        auth=(
            os.environ.get("NEO4J_USER", "neo4j"),
            os.environ.get("NEO4J_PASSWORD", "please-change"),
        ),
    )
    session = driver.session()
    try:
        yield session
    finally:
        await session.close()
        await driver.close()


# Terminal states for an execution run (Plans 02-04 produce these). poll_until_terminal
# polls AFTER a 202-accepted enqueue rather than asserting immediately (RESEARCH run_id
# poll contract): a freshly enqueued run is not yet terminal.
_TERMINAL_STATUSES = {"passed", "failed"}


async def poll_until_terminal(
    client: httpx.AsyncClient,
    run_id: str,
    timeout: float = 60.0,
    interval: float = 1.0,
) -> dict:
    """Poll GET /api/executions/{run_id} until status is terminal, or raise on timeout.

    Mirrors reset_target._wait_for_health's monotonic-deadline loop. Returns the final
    execution JSON (status in {"passed","failed"}). Consumed by Plans 02-04 functional
    tests; the endpoint does not exist yet, so this helper is defined but not called by
    the current suite (importing it must not require the endpoint to exist).
    """
    deadline = time.monotonic() + timeout
    last = "no attempt made"
    while time.monotonic() < deadline:
        resp = await client.get(f"/api/executions/{run_id}")
        if resp.status_code == 200:
            body = resp.json()
            if body.get("status") in _TERMINAL_STATUSES:
                return body
            last = f"status={body.get('status')!r}"
        else:
            last = f"HTTP {resp.status_code}"
        await asyncio.sleep(interval)
    raise TimeoutError(
        f"run {run_id} not terminal within {timeout}s (last: {last})"
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
