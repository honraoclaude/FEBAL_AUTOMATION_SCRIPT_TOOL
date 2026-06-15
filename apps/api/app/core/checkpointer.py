"""Lifespan AsyncPostgresSaver — durable, resumable LangGraph run state (Phase 4, EXPL-05).

NET-NEW lifespan-singleton mirroring core/neo4j_driver.py / core/redis_client.py: one
module-global psycopg3 `AsyncConnectionPool` + one `AsyncPostgresSaver`, opened at app
startup and closed at shutdown via the FastAPI lifespan, reused across every exploration
run (checkpoints keyed by thread_id=run_id).

CRITICAL ties to RESEARCH pitfalls:
  - Pitfall 1 (DSN collision): the checkpointer needs a PLAIN psycopg3 `postgresql://`
    conninfo, NOT the SQLAlchemy `postgresql+asyncpg://` DSN. settings.checkpoint_dsn
    strips the `+asyncpg`. Same DB, two drivers (asyncpg for SQLAlchemy, psycopg3 here).
  - Pitfall 6 (Alembic): the four checkpoint tables (checkpoints, checkpoint_writes,
    checkpoint_blobs, checkpoint_migrations) are owned by `checkpointer.setup()` — an
    IDEMPOTENT call run at lifespan STARTUP, NEVER added to the Alembic migration chain.
  - The package is `psycopg` (psycopg3), NOT `psycopg3`/`psycopg2`.

The pool is capped at max_size=4 (single concurrent run for this phase; Pitfall 2 memory
budget under the 3 GB WSL cap). autocommit=True + dict_row is the AsyncPostgresSaver
contract for the shared-pool form (RESEARCH Pattern 2).
"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None


async def init_checkpointer() -> AsyncPostgresSaver:
    """Open the shared pool + saver and run setup() ONCE (idempotent). Lifespan startup.

    Unlike the lazy neo4j/redis singletons, this MUST connect at startup because
    setup() issues DDL to create the checkpoint tables. It coexists with the asyncpg
    SQLAlchemy engine on the SAME Postgres via the plain checkpoint_dsn (Pitfall 1).
    """
    global _pool, _checkpointer
    if _checkpointer is None:
        _pool = AsyncConnectionPool(
            conninfo=settings.checkpoint_dsn,
            max_size=4,
            open=False,  # open() explicitly below so the pool is ready before setup()
            kwargs={"autocommit": True, "row_factory": dict_row},
        )
        await _pool.open()
        _checkpointer = AsyncPostgresSaver(_pool)
        # Creates the checkpoint tables OUTSIDE Alembic — idempotent (Pitfall 6).
        await _checkpointer.setup()
    return _checkpointer


async def close_checkpointer() -> None:
    """Close the saver pool (idempotent). Called from lifespan shutdown."""
    global _pool, _checkpointer
    if _pool is not None:
        await _pool.close()
    _pool = None
    _checkpointer = None


def get_checkpointer() -> AsyncPostgresSaver:
    """Return the shared lifespan checkpointer.

    Raises if init_checkpointer() has not run — unlike neo4j/redis this is NOT lazy,
    because setup() must have created the tables at startup before any run compiles a
    graph against it. The explorer driver calls this inside run_explore.
    """
    if _checkpointer is None:
        raise RuntimeError(
            "checkpointer not initialized — init_checkpointer() must run in the lifespan startup"
        )
    return _checkpointer
