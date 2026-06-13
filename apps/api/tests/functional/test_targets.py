"""D-02 functional coverage of the target registry CRUD (PLAT-01) — live stack only.

Behaviors pinned here are the literal content of the VALIDATION Per-Task
Verification row 01-05-T1/T2: register/edit/soft-delete a target via the API
with server-side defaults applied (origin allowlist = base-URL origin,
sandbox = false), auth required on every route, and validation rejections.

Pitfall 8: every test creates uniquely-named targets (uuid suffix) and never
asserts global row counts — only entities the test itself created.
"""

import uuid

import pytest

pytestmark = pytest.mark.functional

BASE_URL = "http://localhost:8080"


def _unique_name(prefix: str = "target") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _payload(**overrides) -> dict:
    """Minimal valid TargetCreate body with a unique name; override per test."""
    body = {
        "name": _unique_name(),
        "base_url": BASE_URL,
        "credentials": {
            "username": "standard_user",
            "password": f"pw-{uuid.uuid4().hex[:8]}",
        },
    }
    body.update(overrides)
    return body


async def test_register_target_minimal_defaults(authed_client, clean_targets):
    """POST with only name/base_url/credentials applies server-side defaults (D-05)."""
    payload = _payload()
    r = await authed_client.post("/api/targets", json=payload)
    assert r.status_code == 201, r.text

    body = r.json()
    assert body["name"] == payload["name"]
    # HttpUrl normalization may append a trailing slash — compare modulo that.
    assert body["base_url"].rstrip("/") == BASE_URL
    # Default allowlist is the base_url origin (scheme://host:port), server-computed.
    assert body["origin_allowlist"] == [BASE_URL]
    assert body["sandbox"] is False
    assert body["is_active"] is True
    assert body["budget_overrides"] is None
    assert "id" in body and "created_at" in body and "updated_at" in body


async def test_register_target_full_fields(authed_client, clean_targets):
    """Explicit allowlist, sandbox, and budget overrides are echoed back."""
    allowlist = [BASE_URL, "http://cdn.localhost:8081"]
    budgets = {
        "max_steps": 100,
        "max_depth": 5,
        "wall_clock_seconds": 600,
        "token_budget": 50000,
    }
    r = await authed_client.post(
        "/api/targets",
        json=_payload(
            origin_allowlist=allowlist, sandbox=True, budget_overrides=budgets
        ),
    )
    assert r.status_code == 201, r.text

    body = r.json()
    assert body["origin_allowlist"] == allowlist
    assert body["sandbox"] is True
    assert body["budget_overrides"] is not None
    for key, value in budgets.items():
        assert body["budget_overrides"][key] == value


async def test_list_and_get(authed_client, clean_targets):
    """A created target appears in the list and is fetchable by id; bogus id 404s."""
    payload = _payload()
    r_create = await authed_client.post("/api/targets", json=payload)
    assert r_create.status_code == 201, r_create.text
    target_id = r_create.json()["id"]

    r_list = await authed_client.get("/api/targets")
    assert r_list.status_code == 200
    listed = {t["id"]: t for t in r_list.json()}
    assert target_id in listed
    assert listed[target_id]["name"] == payload["name"]

    r_get = await authed_client.get(f"/api/targets/{target_id}")
    assert r_get.status_code == 200
    assert r_get.json()["name"] == payload["name"]

    r_missing = await authed_client.get("/api/targets/999999")
    assert r_missing.status_code == 404


async def test_edit_target(authed_client, clean_targets):
    """PATCH updates name/base_url (D-07 edit)."""
    r_create = await authed_client.post("/api/targets", json=_payload())
    assert r_create.status_code == 201, r_create.text
    target_id = r_create.json()["id"]

    new_name = _unique_name("renamed")
    new_base_url = "http://localhost:9090"
    r_patch = await authed_client.patch(
        f"/api/targets/{target_id}",
        json={"name": new_name, "base_url": new_base_url},
    )
    assert r_patch.status_code == 200, r_patch.text

    body = r_patch.json()
    assert body["name"] == new_name
    assert body["base_url"].rstrip("/") == new_base_url


async def test_soft_delete_and_reactivate(authed_client, clean_targets):
    """DELETE deactivates without deleting the row; PATCH reactivates (D-07)."""
    r_create = await authed_client.post("/api/targets", json=_payload())
    assert r_create.status_code == 201, r_create.text
    target_id = r_create.json()["id"]

    r_delete = await authed_client.delete(f"/api/targets/{target_id}")
    assert r_delete.status_code == 204

    # Default list excludes inactive targets.
    r_list = await authed_client.get("/api/targets")
    assert r_list.status_code == 200
    assert target_id not in {t["id"] for t in r_list.json()}

    # include_inactive=true shows the soft-deleted row with is_active false.
    r_all = await authed_client.get("/api/targets", params={"include_inactive": "true"})
    assert r_all.status_code == 200
    inactive = {t["id"]: t for t in r_all.json()}
    assert target_id in inactive
    assert inactive[target_id]["is_active"] is False

    # PATCH {is_active: true} restores it to the default list.
    r_restore = await authed_client.patch(
        f"/api/targets/{target_id}", json={"is_active": True}
    )
    assert r_restore.status_code == 200
    assert r_restore.json()["is_active"] is True

    r_list_after = await authed_client.get("/api/targets")
    assert target_id in {t["id"] for t in r_list_after.json()}


async def test_requires_auth(client):
    """Every registry endpoint rejects an unauthenticated client with 401."""
    # Valid-shaped bodies so a 401-vs-422 ordering quirk can never mask the gate.
    r_post = await client.post("/api/targets", json=_payload())
    assert r_post.status_code == 401

    r_list = await client.get("/api/targets")
    assert r_list.status_code == 401

    r_get = await client.get("/api/targets/1")
    assert r_get.status_code == 401

    r_patch = await client.patch("/api/targets/1", json={"name": _unique_name()})
    assert r_patch.status_code == 401

    r_delete = await client.delete("/api/targets/1")
    assert r_delete.status_code == 401


async def test_validation(authed_client, clean_targets):
    """Malformed input is rejected at the boundary (T-01-19)."""
    # base_url without a scheme -> 422 (HttpUrl)
    r_bad_url = await authed_client.post(
        "/api/targets", json=_payload(base_url="not-a-url")
    )
    assert r_bad_url.status_code == 422

    # Negative budget override values -> 422 (ge=1 bounds)
    r_bad_budget = await authed_client.post(
        "/api/targets", json=_payload(budget_overrides={"max_steps": -5})
    )
    assert r_bad_budget.status_code == 422

    # Duplicate name -> 409
    payload = _payload()
    r_first = await authed_client.post("/api/targets", json=payload)
    assert r_first.status_code == 201, r_first.text
    r_dup = await authed_client.post(
        "/api/targets", json={**_payload(), "name": payload["name"]}
    )
    assert r_dup.status_code == 409
