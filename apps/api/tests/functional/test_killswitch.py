"""Functional coverage of the admin kill-switch endpoints (PLAT-06, D-05/D-06).

Live stack over HTTP against the running api container. Proves the manual panic
button: an authenticated admin can trip, read, and clear the global kill-switch,
and the route rejects unauthenticated callers (T-02-08 router-level auth gate).

The flag is RESET in teardown so the live gateway is never left halted for the
rest of the suite or dev use (Pitfall 8 discipline — leave the stack clean).
"""

import pytest

pytestmark = pytest.mark.functional

KILLSWITCH = "/api/admin/llm/killswitch"


@pytest.fixture
async def killswitch_reset(authed_client):
    """Guarantee the kill-switch is cleared after the test, however it ends."""
    yield
    await authed_client.delete(KILLSWITCH)


async def test_trip_read_and_clear_killswitch(authed_client, killswitch_reset):
    # Trip it — authenticated POST returns 200 + active.
    r = await authed_client.post(KILLSWITCH, json={"reason": "functional-test halt"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is True
    assert body["reason"] == "functional-test halt"

    # GET reflects the active state + reason.
    r = await authed_client.get(KILLSWITCH)
    assert r.status_code == 200
    assert r.json() == {"active": True, "reason": "functional-test halt"}

    # DELETE clears it.
    r = await authed_client.delete(KILLSWITCH)
    assert r.status_code == 200
    assert r.json() == {"active": False}

    # GET now reflects the cleared state.
    r = await authed_client.get(KILLSWITCH)
    assert r.status_code == 200
    assert r.json() == {"active": False, "reason": None}


async def test_killswitch_requires_auth(client):
    """Unauthenticated POST is rejected by the router-level auth gate (T-02-08)."""
    r = await client.post(KILLSWITCH, json={"reason": "no-auth"})
    assert r.status_code == 401
