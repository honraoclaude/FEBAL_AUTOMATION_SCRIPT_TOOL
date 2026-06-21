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

import asyncio
import json
import uuid
from dataclasses import dataclass

import aio_pika
import structlog
from aio_pika import DeliveryMode, Message
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.kg.flows as kg_flows
import app.services.kg.reader as kg_reader
from app.core.config import settings
from app.core.redis_client import get_redis
from app.models.execution_history import TestResult, TestRun
from app.models.scenario import Scenario

log = structlog.get_logger()

# The single durable work queue both halves agree on (consumer declares the same name).
QUEUE_NAME = "exec.jobs"

# --- Tier → pytest-bdd selector resolution (EXEC-01 / D-01, RESEARCH Pattern 5) -------------
#
# The tag tiers map to a native pytest-bdd marker selector (`-m <tag>`); `full` is no filter
# (every approved spec). The selector tokens are CONSTANTS — resolve_tier never echoes the raw
# client string into argv (T-07-05). `risk-based` is a valid tier but its selection is dynamic
# (computed by rank_risk_flows), so it carries no -m marker here.
TIER_SELECTOR: dict[str, list[str]] = {
    "smoke": ["-m", "smoke"],
    "sanity": ["-m", "sanity"],
    "regression": ["-m", "regression"],
    "full": [],
}

# The full allow-list of accepted tiers (the tag tiers + the dynamic risk-based tier).
_VALID_TIERS = frozenset({*TIER_SELECTOR.keys(), "risk-based"})


def resolve_tier(tier: str) -> list[str]:
    """Resolve a tier name to its pytest-bdd marker selector tokens (a fresh copy).

    Tag tiers → ``["-m", "<tag>"]``; ``full`` and ``risk-based`` → ``[]`` (no -m filter:
    full runs everything, risk-based is selected dynamically). An unknown tier raises
    ValueError (the router maps it to 422 — V5 input validation, T-07-05). The returned list
    is a COPY of the constant, never the shared mutable list, and the tokens are constants —
    the raw client string is never reflected into argv.
    """
    if tier not in _VALID_TIERS:
        raise ValueError(f"unknown tier {tier!r} (allowed: {sorted(_VALID_TIERS)})")
    # risk-based has no -m filter (dynamic); tag/full come from the selector map.
    return list(TIER_SELECTOR.get(tier, []))


# --- Risk-based dynamic tier ranking (EXEC-01 / D-02, RESEARCH Pattern 6) -------------------
#
# D-03b SEQUENCING: risk-based MUST resolve HERE — while neo4j is UP and BEFORE the run phase.
# rank_risk_flows materializes the top-N spec list from the live graph; ONLY THEN does the run
# phase proceed with neo4j OFF (the 3GB WSL memory budget cannot hold neo4j + Chromium at once).

# Cap the bounded graph read so risk-based never hangs on a down/slow graph; mirrors the exact
# graceful-degrade shape of routers/scenarios._flow_risk_index (honest-empty on failure).
_RISK_TIMEOUT_S = 3.0
# A stable synthetic run_id for the read-surface flow-mining spend (mirrors the scenarios read).
_READ_RUN_ID = "exec-risk-read"


@dataclass(frozen=True)
class RiskRankWeights:
    """Frozen weights for the risk-based tier ranking (mirrors kg/risk.RiskWeights).

    Frozen so a shared default can never be mutated under callers. Values are RESEARCH A1
    [ASSUMED] starting points — tunable with low blast radius (like kg/risk.RiskWeights).
    """

    risk_weight: float = 0.6  # [ASSUMED] graph structural risk contribution (RESEARCH A1)
    failure_weight: float = 0.4  # [ASSUMED] recent-failure-history contribution (RESEARCH A1)
    top_n: int = 10  # [ASSUMED] cap the risk-based suite size — bounds run time + memory (T-07-06)


async def failure_rate(
    db: AsyncSession, flow_ids: list[str], *, last_k: int = 10
) -> dict[str, float]:
    """Per-flow recent failure rate (product_failure count / total) over the last K runs.

    Reads the EXEC-05 ``test_results`` table (RESEARCH failure-history SQL): for each flow,
    failure_rate = product_failure verdicts / total results across the last K distinct
    test_runs. Empty history (cold start) → 0.0 for every flow (no crash, graceful).
    """
    if not flow_ids:
        return {}

    # The last K distinct run_ids by recency (most-recent test_runs).
    recent_runs = (
        await db.execute(
            select(TestRun.run_id).order_by(TestRun.created_at.desc()).limit(last_k)
        )
    ).scalars().all()
    if not recent_runs:
        return {fid: 0.0 for fid in flow_ids}

    total = func.count(TestResult.id)
    failed = func.sum(
        func.cast(TestResult.verdict == "product_failure", Integer)
    )
    rows = (
        await db.execute(
            select(TestResult.flow_id, failed, total)
            .where(
                TestResult.run_id.in_(recent_runs),
                TestResult.flow_id.in_(flow_ids),
            )
            .group_by(TestResult.flow_id)
        )
    ).all()
    rates = {fid: 0.0 for fid in flow_ids}
    for fid, fail_count, count in rows:
        rates[fid] = (float(fail_count or 0) / count) if count else 0.0
    return rates


async def _load_flow_risk() -> list[dict]:
    """Return the build_flows RECORD LIST from the live graph (honest-empty on failure).

    Reproduces routers/scenarios._flow_risk_index's EXACT graceful-degrade shape — both the
    flows_source read and the build_flows mine are bounded by asyncio.wait_for(_RISK_TIMEOUT_S)
    inside ONE try/except. Each returned record already carries the real graph ``risk_score``
    (computed INSIDE build_flows) — callers RANK these records; they never compute the score.
    On graph down/slow/not-discovered (or timeout) → ``[]`` (honest empty, never a hang).
    """
    try:
        graph = await asyncio.wait_for(kg_reader.flows_source(), timeout=_RISK_TIMEOUT_S)
        records = await asyncio.wait_for(
            kg_flows.build_flows(graph, _READ_RUN_ID), timeout=_RISK_TIMEOUT_S
        )
    except Exception:  # noqa: BLE001 -- graph down/slow/not discovered → honest-empty ranking
        return []
    return records


def _spec_path_for_flow(flow_id: str) -> str:
    """The run-relative spec path a flow's generated feature lands at (codegen feature naming)."""
    return f"features/{flow_id}.feature"


async def rank_risk_flows(
    db: AsyncSession, *, weights: RiskRankWeights = RiskRankWeights()
) -> list[dict]:
    """Rank the graph's mined flows by graph-risk + recent-failure and return the top-N.

    D-03b: this MUST run while neo4j is UP and BEFORE the run phase — it materializes the spec
    list, then the run phase proceeds with neo4j off (3GB WSL memory budget).

    Ranks ``_load_flow_risk()``'s build_flows RECORD LIST (each already carries the real graph
    ``risk_score`` — never a bare score computation) combined with ``failure_rate``:

        combined = risk_weight * record["risk_score"] + failure_weight * failure_rate * 100

    Returns the top-N records sorted by ``combined`` desc, each carrying ``id``, ``spec_path``,
    and ``combined``. Cold start (failure_rate all-zero) → pure build_flows risk order.
    neo4j down (``_load_flow_risk`` → []) → empty ranking, no hang.
    """
    records = await _load_flow_risk()
    if not records:
        return []

    flow_ids = [r["id"] for r in records]
    rates = await failure_rate(db, flow_ids)

    ranked: list[dict] = []
    for rec in records:
        fid = rec["id"]
        combined = (
            weights.risk_weight * float(rec.get("risk_score") or 0)
            + weights.failure_weight * rates.get(fid, 0.0) * 100
        )
        ranked.append(
            {
                "id": fid,
                "risk_score": rec.get("risk_score"),
                "risk_tier": rec.get("risk_tier"),
                "spec_path": _spec_path_for_flow(fid),
                "combined": combined,
            }
        )
    ranked.sort(key=lambda e: e["combined"], reverse=True)
    return ranked[: weights.top_n]


async def resolve_flows_for_tier(
    db: AsyncSession, tier: str, *, weights: RiskRankWeights = RiskRankWeights()
) -> list[dict]:
    """Resolve the per-flow job list to enqueue for a tier (B1, RESEARCH "per-flow enqueue").

    The uniform engine path is per-flow enqueue for ALL tiers (RESEARCH Open Q3) — one job per
    chosen flow, each `{flow_id}`:

      - tag tiers (smoke/sanity/regression) and `full`: one job per DISTINCT approved-scenario
        flow_id (the tag selector is carried on the run's `selector` for the in-spec `-m` filter;
        per-flow granularity gives the live view + retry/kill their natural scope). Reads
        Postgres only — NO graph, so tag tiers stay keyless.
      - `risk-based` (D-02/D-03b): one job per top-N ranked flow from rank_risk_flows (this runs
        while neo4j is UP, BEFORE the run phase — the caller sequences neo4j off afterwards).

    Returns a list of job dicts (possibly empty when nothing is approved/ranked — the run is
    still created; an empty enqueue is a valid no-flow run, not an error).
    """
    if tier == "risk-based":
        ranked = await rank_risk_flows(db, weights=weights)
        return [{"flow_id": r["id"]} for r in ranked]

    # Tag tiers + full: one job per distinct approved-scenario flow_id (Postgres-only, keyless).
    flow_ids = (
        await db.execute(
            select(Scenario.flow_id)
            .where(Scenario.status == "approved")
            .group_by(Scenario.flow_id)
            .order_by(Scenario.flow_id)
        )
    ).scalars().all()
    return [{"flow_id": fid} for fid in flow_ids]


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


async def kill_run(run_id: str) -> None:
    """Graceful cooperative kill (D-07, RESEARCH Pattern 3): set the flag + purge the queue.

    Two cooperative steps, NO forceful process termination:
      1. Set the Redis kill flag `run:{run_id}:kill` (via the SHARED get_redis() client). The
         worker checks this BETWEEN tests and DRAINS — it finishes/aborts the in-flight test and
         pulls no new work for the run; remaining flows resolve to `aborted` (not product_failure).
      2. Purge the WHOLE durable exec.jobs queue of pending jobs so no enqueued-but-unstarted
         flow is consumed after the kill.

    A6/I2 (single-worker, one-run-at-a-time assumption): queue.purge() clears the ENTIRE
    exec.jobs queue, which is safe ONLY because runs are one-at-a-time in Phase 7. Per-run queues
    (`exec.jobs.{run_id}`) are the forward design note for concurrent runs — NOT Phase-7 scope.
    """
    await get_redis().set(f"run:{run_id}:kill", "1")
    if settings.amqp_url is None:
        # The flag is set (the worker drains); without the queue profile up there is nothing to
        # purge — a no-flow run or a host without the broker. Not an error.
        log.info("kill_run", run_id=run_id, purged=False)
        return
    connection = await aio_pika.connect_robust(settings.amqp_url)
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue(QUEUE_NAME, durable=True)
        await queue.purge()
    log.info("kill_run", run_id=run_id, purged=True)
