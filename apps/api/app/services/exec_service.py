"""Execution service (EXEC-03) — the producer half + test_run row management.

Mirrors run_service.py for the row-management half (create_test_run with a fresh uuid4().hex
run_id, status 'queued'), and the AMQP producer half is NET-NEW (RESEARCH Pattern 2): publish one
PERSISTENT message per job to the durable `exec.jobs` queue, awaiting the broker's confirm before
returning. Later slices add the tier→selector resolution, risk-based ranking, and kill/purge.

The producer uses connect_robust + a transient connection per enqueue (the api is not a long-lived
consumer); the worker (consumer.py) owns the long-lived robust connection. The queue is declared
durable on BOTH sides so a message survives a broker restart.

SC3: imports ONLY aio_pika, the DB session/model, settings — no LLM/gateway/explorer.
"""

from __future__ import annotations

import json
import uuid

import aio_pika
import structlog
from aio_pika import DeliveryMode, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.execution_history import TestRun

log = structlog.get_logger()

# The single durable work queue both halves agree on (consumer declares the same name).
QUEUE_NAME = "exec.jobs"


async def create_test_run(
    db: AsyncSession, tier: str, selector: str | None = None
) -> TestRun:
    """Create a TestRun with a fresh hex run_id in status 'queued' (mirrors create_run)."""
    run = TestRun(run_id=uuid.uuid4().hex, tier=tier, selector=selector, status="queued")
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def enqueue_jobs(run_id: str, jobs: list[dict]) -> None:
    """Publish one PERSISTENT message per job to the durable exec.jobs queue (Pattern 2).

    Each job dict gets the run_id stamped in, is serialized to JSON, and published via the
    default exchange with DeliveryMode.PERSISTENT and routing_key=exec.jobs. The channel is
    opened in publisher-confirm mode so default_exchange.publish AWAITS the broker's confirm
    before returning — a returned enqueue means the broker has the message durably.
    """
    if settings.amqp_url is None:
        raise RuntimeError("AMQP_URL is unset — the queue profile must be up to enqueue jobs")

    connection = await aio_pika.connect_robust(settings.amqp_url)
    async with connection:
        # publisher_confirms=True (the default) makes publish() await the broker confirm.
        channel = await connection.channel()
        await channel.declare_queue(QUEUE_NAME, durable=True)
        for job in jobs:
            body = json.dumps({**job, "run_id": run_id}).encode("utf-8")
            await channel.default_exchange.publish(
                Message(body, delivery_mode=DeliveryMode.PERSISTENT),
                routing_key=QUEUE_NAME,
            )
    log.info("enqueue_jobs", run_id=run_id, count=len(jobs))
