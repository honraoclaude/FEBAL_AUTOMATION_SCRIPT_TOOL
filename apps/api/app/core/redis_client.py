"""Single long-lived redis.asyncio client for the LLM gateway hot path (PLAT-06).

NET-NEW pattern (PATTERNS flag #1). Phase-1 app code touches Redis only for a
once-per-healthcheck ping (health.py opens `from_url(...)` then `aclose()`). That
per-call connect/close is correct for a healthcheck but WRONG for the gateway hot
path, which does GET (kill-switch) + MGET (budget read) + pipeline INCRBY (reconcile)
on EVERY call. This module owns ONE long-lived client, opened at app startup and
closed at shutdown via the FastAPI lifespan, reused across all gateway calls.

`redis.asyncio` is the CLAUDE.md-locked client (the dead `aioredis` package is NOT
used; the `as aioredis` alias in health.py is just a local name).
"""

import redis.asyncio as redis

from app.core.config import settings

_client: redis.Redis | None = None


def init_redis() -> redis.Redis:
    """Open the shared client (idempotent). Called from main.py's lifespan startup.

    `decode_responses=True` so GET/MGET return str (not bytes) — the gateway compares
    budget counter strings to numbers and reads the kill-switch reason as text.
    """
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def close_redis() -> None:
    """Close the shared client (idempotent). Called from lifespan shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_redis() -> redis.Redis:
    """Return the shared lifespan client for gateway/admin use.

    Opens lazily if init_redis() has not run yet (e.g. a unit test importing the
    gateway outside the app lifespan), so callers never get None.
    """
    if _client is None:
        return init_redis()
    return _client
