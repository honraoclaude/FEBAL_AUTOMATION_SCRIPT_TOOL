"""Wave 0 test scaffolding (01-VALIDATION.md).

D-02: tests are FUNCTIONAL — they hit the RUNNING stack over live HTTP with
real Postgres/Redis. No ASGITransport in-process shortcut, no DB session
fixtures that bypass HTTP. The authed-client and truncate fixtures are added
by plan 01-03.
"""

import os
from collections.abc import AsyncIterator

import httpx
import pytest

# Host-facing API port is 8001 (8000 is held by another local project's container)
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8001")
WEB_BASE = os.environ.get("WEB_BASE_URL", "http://localhost:3000")


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """Live-HTTP client against the running API (compose or hybrid host mode)."""
    async with httpx.AsyncClient(base_url=API_BASE) as c:
        yield c
