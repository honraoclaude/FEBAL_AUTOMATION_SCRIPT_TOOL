"""Single long-lived AsyncElasticsearch client for the full-text search seam (DASH-06).

Mirrors neo4j_driver.py: one module-global client, opened at app startup and closed at
shutdown via the FastAPI lifespan, reused across every search / on-write index call.

The AsyncElasticsearch client IS a connection pool — `AsyncElasticsearch(url)` constructs a
pool of HTTP connections over elastic-transport, NOT a single socket. The anti-pattern is one
client per request (each spins up its own pool); this module owns exactly one client = one
pool for the whole process. Never construct a second client.

Graceful-boot contract (10-04 Pitfall, the neo4j-driver precedent): elasticsearch is
`search`-profile-gated and is NOT a `depends_on` of the api service, so the api must boot when
ES is absent. The client is constructed LAZILY here — `AsyncElasticsearch(url)` does not open a
socket until the first request — so `init_es()` at startup never blocks or fails on an
unreachable ES. Connection errors (elasticsearch.exceptions.ConnectionError) surface only when
a search query or an on-write index actually runs; on the read path the main.py 503 handler
turns them into an honest "search unavailable", and on the write path the indexer swallows them.

`elasticsearch` 9.4.x is the CLAUDE.md-locked client (client major MUST equal the ES server
major 9.x; an 8.x client against a 9.x server is forbidden).
"""

from elasticsearch import AsyncElasticsearch

from app.core.config import settings

_es: AsyncElasticsearch | None = None


def init_es() -> AsyncElasticsearch:
    """Construct the shared client/pool (idempotent). Called from main.py's lifespan startup.

    The client opens lazily — no socket is established until the first request runs — so this
    never blocks or fails when ES is down (search profile inactive).
    """
    global _es
    if _es is None:
        _es = AsyncElasticsearch(settings.elasticsearch_url)
    return _es


async def close_es() -> None:
    """Close the shared client/pool (idempotent). Called from lifespan shutdown."""
    global _es
    if _es is not None:
        await _es.close()
        _es = None


def get_es() -> AsyncElasticsearch:
    """Return the shared lifespan client for search/index use.

    Opens lazily if init_es() has not run yet (e.g. a unit test importing a search module
    outside the app lifespan), so callers never get None.
    """
    if _es is None:
        return init_es()
    return _es
