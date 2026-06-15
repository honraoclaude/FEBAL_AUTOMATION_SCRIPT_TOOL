"""Single long-lived AsyncGraphDatabase driver for the knowledge-graph seam (PLAT-02).

Mirrors redis_client.py: one module-global driver, opened at app startup and closed
at shutdown via the FastAPI lifespan, reused across every Bolt query.

The Neo4j Python driver IS a connection pool — `AsyncGraphDatabase.driver(...)` opens
a pool of Bolt connections, NOT a single socket. The canonical anti-pattern is one
driver per request (each spins up its own pool); this module owns exactly one driver =
one pool for the whole process. Acquire a short-lived `session()` per unit of work from
this shared driver; never construct a second driver.

Graceful-boot contract (Pitfall 6 / A6): neo4j is graph-profile-gated and is NOT a
`depends_on` of the api service, so the api must boot when neo4j is absent. The driver
is opened LAZILY here — `AsyncGraphDatabase.driver()` does not connect until the first
session/`verify_connectivity()` — so `init_neo4j()` at startup never blocks or fails
on an unreachable neo4j. Connection errors surface only when a graph query actually runs.

`neo4j` 6.2.x is the CLAUDE.md-locked driver (the dead `neo4j-driver` package is NOT used).
"""

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import settings

_driver: AsyncDriver | None = None


def init_neo4j() -> AsyncDriver:
    """Open the shared driver/pool (idempotent). Called from main.py's lifespan startup.

    The driver opens lazily — no socket is established until the first session runs —
    so this never blocks or fails when neo4j is down (graph profile inactive).
    """
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            # graph_mode restarts the neo4j container (new IP) under a long-running api,
            # leaving defunct pooled connections. Liveness-check idle connections before
            # reuse so the driver transparently re-dials the recreated server.
            liveness_check_timeout=0,
        )
    return _driver


async def close_neo4j() -> None:
    """Close the shared driver/pool (idempotent). Called from lifespan shutdown."""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


def get_neo4j() -> AsyncDriver:
    """Return the shared lifespan driver for graph use.

    Opens lazily if init_neo4j() has not run yet (e.g. a unit test importing a graph
    module outside the app lifespan), so callers never get None.
    """
    if _driver is None:
        return init_neo4j()
    return _driver
