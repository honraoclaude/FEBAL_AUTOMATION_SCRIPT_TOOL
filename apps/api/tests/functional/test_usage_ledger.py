"""Functional: a gateway complete() driven inside the LIVE api container lands
exactly one llm_usage ledger row with the correct fields (PLAT-06, D-09).

The provider is mocked INSIDE the container (init_chat_model monkeypatched to a
fake AIMessage) so no real key/spend is needed, but everything else — Settings,
the async DB session, the real Postgres write, the structlog event — is the live
stack. The row is read back from Postgres over the host DSN (asyncpg).
"""

import os
import subprocess
import uuid
from pathlib import Path

import asyncpg
import pytest

pytestmark = pytest.mark.functional

# tests/functional/ -> parents[4] = repo root (matches test_credential_security.py).
REPO_ROOT = Path(__file__).resolve().parents[4]

# In-container driver: patch init_chat_model, call complete(), print the run_id.
# Runs inside `docker compose exec api` so the ledger row + structlog event are
# produced by the real container against the real Postgres/Redis.
_DRIVER = r'''
import asyncio, sys
import app.services.llm_gateway as gw
from app.core.llm_pricing import PRICING

run_id = sys.argv[1]
op = sys.argv[2]
model = "anthropic:" + PRICING[0].model

class _Msg:
    content = "live-ledger-ok"
    usage_metadata = {"input_tokens": 1234, "output_tokens": 567, "total_tokens": 1801}
    response_metadata = {}

class _Chat:
    async def ainvoke(self, messages):
        return _Msg()

gw.init_chat_model = lambda *a, **k: _Chat()

async def main():
    from app.db.session import SessionLocal
    async with SessionLocal() as db:
        # no_cache=True forces the miss/spend path: this test verifies a REAL computed
        # cost lands one cache_hit=false row. Without it, an identical prior call's
        # 24h-TTL cache entry (Plan 03) would serve a $0 cache_hit=true row and the
        # cost/cache_hit assertions below would flake by run order.
        res = await gw.complete(
            db, [{"role": "user", "content": "probe"}],
            operation_type=op, run_id=run_id, model=model, max_tokens=256,
            no_cache=True,
        )
        print("RESULT_COST", res.cost_usd)

asyncio.run(main())
'''


def _host_dsn() -> str:
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


def _run_driver(run_id: str, op: str) -> str:
    proc = subprocess.run(
        [
            "docker", "compose",
            "-f", "infra/docker-compose.yml",
            "--env-file", ".env",
            "exec", "-T", "api",
            "uv", "run", "python", "-c", _DRIVER, run_id, op,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert proc.returncode == 0, f"driver failed: {proc.stdout}\n{proc.stderr}"
    return proc.stdout


@pytest.fixture
async def clean_llm_usage():
    """Remove only the rows this test created (by run_id), after the test."""
    created_run_ids: list[str] = []
    yield created_run_ids
    if not created_run_ids:
        return
    conn = await asyncpg.connect(_host_dsn())
    try:
        await conn.execute(
            "DELETE FROM llm_usage WHERE run_id = ANY($1::text[])", created_run_ids
        )
    finally:
        await conn.close()


async def test_complete_writes_one_ledger_row(clean_llm_usage):
    run_id = f"led-{uuid.uuid4().hex[:12]}"
    op = "test.usage_ledger"
    clean_llm_usage.append(run_id)

    _run_driver(run_id, op)

    conn = await asyncpg.connect(_host_dsn())
    try:
        rows = await conn.fetch("SELECT * FROM llm_usage WHERE run_id = $1", run_id)
    finally:
        await conn.close()

    assert len(rows) == 1, f"expected exactly one ledger row, got {len(rows)}"
    row = rows[0]
    assert row["operation_type"] == op
    assert row["provider"] == "anthropic"
    assert row["model"].startswith("anthropic:")
    assert row["input_tokens"] == 1234
    assert row["output_tokens"] == 567
    assert row["cost_usd"] > 0
    assert row["cache_hit"] is False
