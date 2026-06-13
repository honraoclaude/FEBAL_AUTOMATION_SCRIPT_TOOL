"""D-02 functional coverage of GET /health — live stack over HTTP only."""

import pytest

pytestmark = pytest.mark.functional


async def test_health_returns_200_with_components(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["postgres"] is True
    assert body["redis"] is True
