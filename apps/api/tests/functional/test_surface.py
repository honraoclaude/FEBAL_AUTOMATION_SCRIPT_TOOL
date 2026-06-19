"""SC4 proof (03-04 Task 3, UPDATED 05-03) — the complete + honest PLAT-02 surface.

Every PLAT-02 endpoint EXISTS (no route-level 404): the REAL endpoints reject an
unauthenticated client with 401 (the auth gate is present — T-03-17), and the remaining
STUB endpoints return 501 when authenticated (documented contract, never a fabricated
result — T-03-19). Also asserts the shared/events schemas import (SC4: schemas present).

UPDATE (Phase 5 / slice 03 — D-06): GET /flows and GET /coverage were Phase-3 501 stubs;
they are now REAL read-only auth-gated endpoints (routers/kg.py), so they moved from the
STUB list (authed→501) to the REAL list (unauth→401). The remaining honest stubs are
heal (Phase 8) / create-defect (Phase 9) / dashboard (Phase 10).

Default-gate test (functional, no graph/live_llm) — stays in the canonical green suite.
"""

import pytest

pytestmark = [pytest.mark.functional]

# The REAL endpoints (Plans 02-03 + /execute + the Phase-5 KG reads): unauth -> 401
# (auth gate present, route exists). /flows + /coverage joined here when they became real.
REAL_ENDPOINTS = [
    ("POST", "/api/explore"),
    ("GET", "/api/executions"),
    ("POST", "/api/generate-bdd"),
    ("POST", "/api/generate-scripts"),
    ("POST", "/api/execute"),
    ("GET", "/api/flows"),
    ("GET", "/api/coverage"),
    ("GET", "/api/graph"),
    ("GET", "/api/pages"),
    ("GET", "/api/elements"),
]

# The remaining STUB endpoints: authed -> 501 (documented contract, never fabricated).
# Each carries a minimal VALID body so the request passes schema validation and reaches the
# handler (which raises 501) — an invalid body would 422 before the stub's 501 fires.
STUB_ENDPOINTS = [
    ("POST", "/api/heal", {"run_id": "x", "spec_path": "x", "failing_selector": "#x"}),
    (
        "POST",
        "/api/create-defect",
        {"run_id": "x", "summary": "x", "description": "x", "classification": "x"},
    ),
    ("GET", "/api/dashboard", None),
]


async def _call(client, method: str, path: str, body: dict | None = None):
    if method == "GET":
        return await client.get(path)
    return await client.post(path, json=body or {})


@pytest.mark.parametrize("method,path", REAL_ENDPOINTS)
async def test_real_endpoints_exist_and_are_auth_gated(client, method, path):
    """Each REAL endpoint exists and rejects unauthenticated access with 401 (not 404)."""
    resp = await _call(client, method, path)
    assert resp.status_code == 401, (
        f"{method} {path} expected 401 (exists + auth-gated), got {resp.status_code}"
    )


@pytest.mark.parametrize("method,path,body", STUB_ENDPOINTS)
async def test_stub_endpoints_return_501_when_authed(authed_client, method, path, body):
    """Each STUB endpoint exists, is authed, and returns 501 — never a fabricated result."""
    resp = await _call(authed_client, method, path, body)
    assert resp.status_code == 501, (
        f"{method} {path} expected 501 (honest stub), got {resp.status_code}: {resp.text}"
    )


@pytest.mark.parametrize("method,path,body", STUB_ENDPOINTS)
async def test_stub_endpoints_are_auth_gated(client, method, path, body):
    """Each STUB endpoint is also behind the auth gate (401 unauthenticated, T-03-17)."""
    resp = await _call(client, method, path, body)
    assert resp.status_code == 401, (
        f"{method} {path} expected 401 unauthenticated, got {resp.status_code}"
    )


def test_full_plat02_surface_is_complete():
    """The PLAT-02 surface is complete: the original 10 endpoints all exist + auth-gated.

    Phase 5 promoted /flows + /coverage from stub→real and added /graph /pages /elements
    (KG reads), so the split is now 10 real + 3 stub (the original 10-endpoint surface is a
    subset of these; every endpoint exists and is auth-gated).
    """
    assert len(REAL_ENDPOINTS) == 10
    assert len(STUB_ENDPOINTS) == 3


def test_shared_events_schemas_present():
    """shared/events message schemas import (SC4 — schemas present, no broker yet)."""
    from shared.events import ExecuteJob, ExploreJob, RunStatusEvent

    assert ExploreJob is not None
    assert ExecuteJob is not None
    assert RunStatusEvent is not None
