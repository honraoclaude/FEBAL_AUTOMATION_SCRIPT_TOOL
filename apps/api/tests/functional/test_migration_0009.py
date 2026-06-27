"""Migration 0009 reversibility proof (defect-intelligence schema) — needs a real Postgres.

Migration 0009 (down_revision='0008') adds the defect-intelligence schema:
  - `classifications` (the per-failure 3-way class + 0-100 confidence + cited-evidence JSON);
  - `defects` (the draft-review row: status/fingerprint/jira_key — the JIRA-04 traceability link);
  - `test_results.error_text` (the Phase-7 persistence gap closed — Pitfall 1: the classifier reads it).

This functional test runs the SAME `alembic upgrade head && downgrade -1 && upgrade head`
round-trip the phase gate requires (the 0008 reverse-order discipline), via the alembic API on
the running Postgres, and asserts the round-trip is clean AND that `test_results.error_text`
exists after the final upgrade. Mirrors the keyless harness style: it SKIPS cleanly when Postgres
is not reachable (the `_port_open` skip discipline from test_healing_mutations.py) so the default
keyless suite never hard-fails on a missing service.

Run: cd apps/api && uv run python -m pytest tests/functional/test_migration_0009.py -q
"""

from __future__ import annotations

import socket
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings

pytestmark = [pytest.mark.functional]


def _pg_host_port() -> tuple[str, int]:
    """Parse host/port out of the SQLAlchemy DATABASE_URL (postgresql+asyncpg://...)."""
    parsed = urlparse(settings.database_url)
    return parsed.hostname or "localhost", parsed.port or 5432


def _pg_up() -> bool:
    """Cheap TCP up-check — skip cleanly when Postgres is not reachable (harness discipline)."""
    host, port = _pg_host_port()
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _sync_url() -> str:
    """A SYNC psycopg3 URL for inspection (alembic env owns its own async engine).

    asyncpg can't drive SQLAlchemy's sync inspector and psycopg2 is not installed (the repo
    ships psycopg[binary]==3.x for the langgraph checkpointer). Route the sync inspector through
    the `postgresql+psycopg://` (psycopg3) dialect explicitly rather than the bare
    `postgresql://` form, which would default to psycopg2.
    """
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


def _alembic_cfg() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    return cfg


def _require_pg() -> None:
    if not _pg_up():
        pytest.skip("Postgres is not reachable — skipping the migration round-trip proof")


def test_migration_0009_round_trips_and_adds_error_text() -> None:
    """upgrade head -> downgrade -1 -> upgrade head is clean; test_results.error_text exists."""
    _require_pg()
    cfg = _alembic_cfg()

    # Ensure we start at head (0009 after this plan lands), then prove the reversible round-trip.
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")  # 0009 -> 0008 (drops defects/classifications + error_text)
    command.upgrade(cfg, "head")  # 0008 -> 0009 (re-adds them) — round-trip clean

    engine = create_engine(_sync_url())
    try:
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("test_results")}
        assert "error_text" in cols, "test_results.error_text missing after upgrade to 0009"

        tables = set(insp.get_table_names())
        assert "classifications" in tables, "classifications table missing after upgrade"
        assert "defects" in tables, "defects table missing after upgrade"

        # The downgrade half is proven by the up/down/up above completing without error; a final
        # sanity that error_text is actually a column we can select (no row needed).
        with engine.connect() as conn:
            conn.execute(text("SELECT error_text FROM test_results LIMIT 0"))
    finally:
        engine.dispose()
