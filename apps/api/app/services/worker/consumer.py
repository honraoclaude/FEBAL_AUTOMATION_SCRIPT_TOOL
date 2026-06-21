"""aio-pika robust consumer with bounded prefetch (EXEC-03) — RESEARCH Pattern 1.

A single stateless worker connects with `connect_robust` (auto-reconnect + state recovery),
sets QoS prefetch to bound concurrent in-flight jobs to browser capacity (settings
.exec_prefetch_count, default 2 — the HARD ceiling under the 3GB WSL cap), and consumes via the
async iterator with per-message `process(requeue=True)` (auto-ack on success / requeue on a
transient exception). Each message body is a JSON job dict handed to run_flow_job.

T-07-02 (poison payload): a message whose body is not valid JSON is caught and ACKED (not
infinitely requeued) so a single malformed message cannot wedge the queue; a job that raises
during execution is requeued once via message.process(requeue=True).

SC3: imports ONLY aio_pika + the worker job runner — no LLM/gateway/explorer.
"""

from __future__ import annotations

import json

import aio_pika
import structlog

from app.services.worker.job import run_flow_job

log = structlog.get_logger()

# The single durable work queue both halves agree on (producer declares the same name).
QUEUE_NAME = "exec.jobs"


async def run_consumer(amqp_url: str, prefetch: int = 2) -> None:
    """Consume exec.jobs forever with bounded prefetch (= parallel browser capacity).

    `connect_robust` gives auto-reconnect + state recovery; `set_qos(prefetch_count=prefetch)`
    caps in-flight jobs (and thus Chromium contexts) at the 3GB-safe default of 2. The async
    iterator + `message.process(requeue=True)` handle ack/nack: success acks, a raising job
    requeues once, and a non-JSON body is acked (T-07-02 — never an infinite redelivery loop).
    """
    connection = await aio_pika.connect_robust(amqp_url)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=prefetch)  # = parallel browser capacity (2)
        queue = await channel.declare_queue(QUEUE_NAME, durable=True)
        log.info("worker_consuming", queue=QUEUE_NAME, prefetch=prefetch)
        async with queue.iterator() as it:
            async for message in it:
                try:
                    job = json.loads(message.body)
                except (ValueError, TypeError) as exc:
                    # Poison/malformed payload: ack-and-drop, never infinitely requeue (T-07-02).
                    await message.ack()
                    log.error("worker_bad_payload", error=str(exc))
                    continue
                async with message.process(requeue=True):
                    await run_flow_job(job)
