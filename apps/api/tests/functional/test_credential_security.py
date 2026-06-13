"""PLAT-07 credential-leak tests (VALIDATION row PLAT-07) — the phase's security teeth.

D-06: target credentials are write-only. These tests assert the three leak
surfaces are closed against the LIVE stack:
  1. API responses (structural whitelist-by-omission on TargetResponse)
  2. the database at rest (Fernet ciphertext only; decrypt round-trips)
  3. captured API logs (structlog redaction + no payload echo)

Pitfall 8: unique-per-test names and secrets (uuid suffix); no global counts.
"""

import os
import subprocess
import uuid
from pathlib import Path

import asyncpg
import pytest
from cryptography.fernet import Fernet, MultiFernet

# conftest.py loads the repo-root .env before test modules import, so Settings
# resolves TARGET_CREDENTIAL_KEY identically to the running api container.
from app.core.config import settings

pytestmark = pytest.mark.functional

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_URL = "http://localhost:8080"


def _unique_name(prefix: str = "sec-target") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _payload(username: str, password: str) -> dict:
    return {
        "name": _unique_name(),
        "base_url": BASE_URL,
        "credentials": {"username": username, "password": password},
    }


def _host_dsn() -> str:
    """DATABASE_URL rewritten for host-side asyncpg (no +asyncpg, localhost not 'postgres')."""
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


def _fernet() -> MultiFernet:
    return MultiFernet([Fernet(k) for k in settings.credential_keys])


async def _fetch_ciphertext(name: str) -> tuple[bytes, bytes]:
    """Raw encrypted_username/encrypted_password bytes for a target, straight from Postgres."""
    conn = await asyncpg.connect(_host_dsn())
    try:
        row = await conn.fetchrow(
            "SELECT encrypted_username, encrypted_password FROM targets WHERE name = $1",
            name,
        )
    finally:
        await conn.close()
    assert row is not None, f"target {name!r} not found in DB"
    return bytes(row["encrypted_username"]), bytes(row["encrypted_password"])


async def test_credentials_never_in_response(authed_client, clean_targets):
    """The plaintext password appears in NO response; TargetResponse has no credential key."""
    password = f"secret_sauce-{uuid.uuid4().hex}"
    payload = _payload("standard_user", password)

    r_post = await authed_client.post("/api/targets", json=payload)
    assert r_post.status_code == 201, r_post.text
    assert password not in r_post.text
    body = r_post.json()
    assert "credentials" not in body
    assert "password" not in body
    assert body["has_credentials"] is True
    target_id = body["id"]

    r_list = await authed_client.get("/api/targets")
    assert r_list.status_code == 200
    assert password not in r_list.text

    r_get = await authed_client.get(f"/api/targets/{target_id}")
    assert r_get.status_code == 200
    assert password not in r_get.text

    r_patch = await authed_client.patch(
        f"/api/targets/{target_id}", json={"name": _unique_name("renamed")}
    )
    assert r_patch.status_code == 200
    assert password not in r_patch.text
    assert "credentials" not in r_patch.json()


async def test_db_column_is_ciphertext_roundtrip(authed_client, clean_targets):
    """DB columns hold Fernet ciphertext (no plaintext bytes); decrypt round-trips."""
    username = f"user-{uuid.uuid4().hex[:8]}"
    password = f"pw-{uuid.uuid4().hex}"
    payload = _payload(username, password)

    r = await authed_client.post("/api/targets", json=payload)
    assert r.status_code == 201, r.text

    enc_username, enc_password = await _fetch_ciphertext(payload["name"])

    # Plaintext must not appear in the raw stored bytes.
    assert username.encode() not in enc_username
    assert password.encode() not in enc_password

    # Fernet/MultiFernet keyed from settings.credential_keys round-trips exactly.
    fernet = _fernet()
    assert fernet.decrypt(enc_username).decode() == username
    assert fernet.decrypt(enc_password).decode() == password


async def test_logs_contain_no_plaintext(authed_client, clean_targets):
    """API container logs captured around a registration round-trip hold no plaintext password."""
    password = f"leakcheck-{uuid.uuid4().hex}"
    payload = _payload("log_probe_user", password)

    r_post = await authed_client.post("/api/targets", json=payload)
    assert r_post.status_code == 201, r_post.text
    r_get = await authed_client.get(f"/api/targets/{r_post.json()['id']}")
    assert r_get.status_code == 200

    proc = subprocess.run(
        [
            "docker", "compose",
            "-f", "infra/docker-compose.yml",
            "--env-file", ".env",
            "logs", "api", "--since", "2m",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"log capture failed: {proc.stderr}"
    captured = proc.stdout + proc.stderr
    # Guard against a vacuous pass: the window must contain the requests we just made.
    assert captured.strip(), "no api logs captured in the 2m window"
    assert password not in captured, "plaintext password leaked into api logs"


async def test_update_credentials_write_only(authed_client, clean_targets):
    """PATCHed credentials are accepted, never echoed, re-encrypted, and decryptable."""
    payload = _payload(f"user-{uuid.uuid4().hex[:8]}", f"pw-{uuid.uuid4().hex}")
    r_create = await authed_client.post("/api/targets", json=payload)
    assert r_create.status_code == 201, r_create.text
    target_id = r_create.json()["id"]

    original_enc_username, original_enc_password = await _fetch_ciphertext(
        payload["name"]
    )

    new_username = f"rotated-{uuid.uuid4().hex[:8]}"
    new_password = f"rotated-pw-{uuid.uuid4().hex}"
    r_patch = await authed_client.patch(
        f"/api/targets/{target_id}",
        json={"credentials": {"username": new_username, "password": new_password}},
    )
    assert r_patch.status_code == 200, r_patch.text

    # Response stays credential-free.
    assert new_password not in r_patch.text
    body = r_patch.json()
    assert "credentials" not in body
    assert body["has_credentials"] is True

    # Ciphertext changed and decrypts to the NEW values.
    enc_username, enc_password = await _fetch_ciphertext(payload["name"])
    assert enc_username != original_enc_username
    assert enc_password != original_enc_password
    fernet = _fernet()
    assert fernet.decrypt(enc_username).decode() == new_username
    assert fernet.decrypt(enc_password).decode() == new_password
