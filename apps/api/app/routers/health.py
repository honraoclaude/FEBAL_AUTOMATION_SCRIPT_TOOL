"""GET /health — pings Postgres (SELECT 1) and Redis (PING).

Returns only boolean component status — no versions, hosts, or config values
(threat T-01-05 accepted on that basis). No auth on this route: the container
healthcheck and verify_stack.py depend on it.
"""

import redis.asyncio as aioredis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

router = APIRouter()


@router.get("/health")
async def health() -> JSONResponse:
    postgres_ok = False
    redis_ok = False

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        postgres_ok = True
    except Exception:
        postgres_ok = False

    try:
        client = aioredis.from_url(settings.redis_url)
        try:
            await client.ping()
            redis_ok = True
        finally:
            await client.aclose()
    except Exception:
        redis_ok = False

    healthy = postgres_ok and redis_ok
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "postgres": postgres_ok,
            "redis": redis_ok,
        },
    )
