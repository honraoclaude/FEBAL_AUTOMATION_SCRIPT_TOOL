"""Migration 0010 reversibility proof (users.role column, PLAT-04) — needs a real Postgres.

Migration 0010 (down_revision='0009') adds the RBAC `role` column to `users`:
  - `users.role` String(16), server_default='admin', NOT NULL — so EXISTING rows (the seeded
    admin) gain a valid role with no data backfill (Pitfall 6 / Runtime State Inventory).

This test runs the SAME `alembic upgrade head && downgrade -1 && upgrade head` round-trip the
phase gate requires (the 0009 reverse-order discipline, mirrored), via the alembic API on the
running Postgres, and asserts:
  - after `upgrade head`, `users.role` exists AND every existing users row reads role='admin'
    (the server_default applied to the seeded admin row);
  - `downgrade -1` (0010 -> 0009) drops the column;
  - `upgrade head` (0009 -> 0010) re-adds it cleanly (up/down/up reversible).

Mirrors the keyless harness style: it SKIPS cleanly when Postgres is not reachable (the
`_port_open` skip discipline) so the default keyless suite never hard-fails on a missing service.

Run: cd apps/api && uv run python -m pytest tests/integration/test_migration_0010.py -q
"""

from __future__ import annotations

import socket
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings

pytestmark = [pytest.mark.integration]


def _pg_host_port() -> tuple[str, int]:
    """Parse host/port out of the SQLAlchemy DATABASE_URL (postgresql+asyncpg://...)."""
    parsed = urlparse(settings.database_url)
    return parsed.hostname or "localhost", parsed.port or 5432


def _pg_up() -> bool:
    """Cheap TCP up-check — skip cleanly when Postgres is not reachable (harness discipline)."""
    host, port = _pg_host_port()
    # The alembic env + sync inspector reach Postgres on the HOST (localhost), not the in-cluster
    # 'postgres' hostname; rewrite for the up-check the same way _sync_url does for the engine.
    host = "localhost" if host == "postgres" else host
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _host_url() -> str:
    """The DATABASE_URL rewritten for host-side use (in-cluster 'postgres' host -> localhost)."""
    return settings.database_url.replace("@postgres:", "@localhost:")


def _sync_url() -> str:
    """A SYNC psycopg3 URL for inspection (alembic env owns its own async engine).

    asyncpg can't drive SQLAlchemy's sync inspector and psycopg2 is not installed (the repo
    ships psycopg[binary]==3.x for the langgraph checkpointer). Route the sync inspector through
    the `postgresql+psycopg://` (psycopg3) dialect explicitly.
    """
    return _host_url().replace("postgresql+asyncpg://", "postgresql+psycopg://")


def _alembic_cfg() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", _host_url())
    return cfg


def _require_pg() -> None:
    if not _pg_up():
        pytest.skip("Postgres is not reachable — skipping the migration round-trip proof")


def test_migration_0010_round_trips_and_sets_admin_role() -> None:
    """upgrade head -> downgrade -1 -> upgrade head is clean; users.role exists + admin row='admin'."""
    _require_pg()
    cfg = _alembic_cfg()

    # Ensure we start at head (0010 after this plan lands), then prove the reversible round-trip.
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")  # 0010 -> 0009 (drops users.role)
    command.upgrade(cfg, "head")  # 0009 -> 0010 (re-adds it) — round-trip clean

    engine = create_engine(_sync_url())
    try:
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("users")}
        assert "role" in cols, "users.role missing after upgrade to 0010"

        with engine.connect() as conn:
            # Every existing users row (incl. the seeded admin) got a valid role via server_default.
            null_or_blank = conn.execute(
                text("SELECT count(*) FROM users WHERE role IS NULL OR role = ''")
            ).scalar_one()
            assert null_or_blank == 0, "some users row has a NULL/blank role after 0010"
            # The seeded admin row specifically reads 'admin'.
            admin_role = conn.execute(
                text("SELECT role FROM users WHERE email = :e"),
                {"e": settings.admin_email},
            ).scalar_one_or_none()
            assert admin_role == "admin", f"seeded admin role is {admin_role!r}, expected 'admin'"
    finally:
        engine.dispose()


def test_migration_0010_downgrade_drops_role() -> None:
    """After downgrade to 0009 the role column is gone; re-upgrade restores it (left at head)."""
    _require_pg()
    cfg = _alembic_cfg()

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")  # 0010 -> 0009
    engine = create_engine(_sync_url())
    try:
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("users")}
        assert "role" not in cols, "users.role should be dropped after downgrade to 0009"
    finally:
        engine.dispose()
    # Restore head so the rest of the suite (and the dev stack) sees the column.
    command.upgrade(cfg, "head")
