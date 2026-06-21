"""Execution worker container entrypoint (EXEC-03) — `python -m app.worker_main`.

The SAME uv project + image as the api (RESEARCH Open Q1: reuse the api image with a different
`command:`), so it shares get_redis(), SessionLocal, all models/services. Mirrors main.py's
lifespan STARTUP shape minimally:
  - configure_logging() + init_redis() — the worker publishes progress + (Plan 03) reads the
    kill flag via the SAME shared lifespan client (never a second client);
  - run the aio-pika consumer loop until shutdown.

It does NOT init neo4j (D-03b — neo4j is OFF during the run phase) or the LangGraph checkpointer,
and it imports NOTHING from the LLM gateway / LangChain / LangGraph / explorer path (SC3 — the
tests/unit/test_no_llm_in_worker.py grep gate covers this file too).
"""

from __future__ import annotations

import asyncio

import structlog

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.redis_client import close_redis, init_redis
from app.services.worker.consumer import run_consumer

log = structlog.get_logger()


async def _main() -> None:
    configure_logging()
    init_redis()  # the shared client the worker publishes progress / reads the kill flag with
    if settings.amqp_url is None:
        raise RuntimeError("AMQP_URL is unset — the worker needs the queue broker to consume")
    log.info("worker_starting", prefetch=settings.exec_prefetch_count)
    try:
        await run_consumer(settings.amqp_url, settings.exec_prefetch_count)
    finally:
        await close_redis()


if __name__ == "__main__":
    asyncio.run(_main())
