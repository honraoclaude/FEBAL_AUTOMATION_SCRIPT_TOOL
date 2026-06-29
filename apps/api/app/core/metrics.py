"""App-level Prometheus domain metrics (INFRA-04) — the sync-over-async bridge.

Exposes the four ALREADY-COMPUTED domain metrics as Prometheus gauges over `/metrics`:
  - qa_platform_heal_success_rate     — self-healing success rate (0..1)
  - qa_platform_classification_precision — defect-review precision applied/(applied+rejected) (0..1)
  - qa_platform_coverage_percent      — lifecycle coverage percent (0..100)
  - qa_platform_llm_cost_usd_total    — total LLM spend in USD

THE CRUX (11-RESEARCH Pattern 1): `Collector.collect()` is SYNC — the prometheus-client REGISTRY
iterates it synchronously — but the four sources are async over Postgres/Neo4j. Calling
`asyncio.run()` inside collect() from the running FastAPI loop raises
`RuntimeError: asyncio.run() cannot be called from a running event loop`. We therefore DECOUPLE
computation from exposition with a BACKGROUND-REFRESHED CACHED SNAPSHOT:

  1. The FastAPI lifespan (the init_redis/init_es precedent) starts an asyncio refresh task.
  2. _refresh_loop() every _REFRESH_SECONDS computes the four metrics over a fresh SessionLocal()
     + get_neo4j(), each source INDEPENDENTLY try/excepted, writing plain floats into _snapshot.
     A failing source sets its key to None (NOT zero) and logs — never propagates.
  3. DomainMetricsCollector.collect() reads _snapshot synchronously and O(1): a None key OMITS its
     gauge (Prometheus reads absent as "no data" — the honest signal, never a fake 0).

Why: scrapes are cheap and CANNOT fail (no DB I/O on the scrape path — T-11-02); a down source
just blanks its gauge while /metrics stays 200 (T-11-03); shipped service logic is reused, never
duplicated; and the running event loop is never touched from a sync context (RESEARCH Pitfall 1).

/metrics auth (T-11-01, accept): unauthenticated-but-safe, the root-mounted /health precedent. It
emits ONLY aggregate numeric gauges + HTTP histograms — no secrets, no PII, no prompts (the
llm_usage ledger has no prompt/response columns, PLAT-07). A scrape-token gate is deferred for the
single-operator local posture (documented). collect() NEVER touches the DB — only cached floats.
"""

from __future__ import annotations

import asyncio

import structlog
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import REGISTRY, Collector
from sqlalchemy import Numeric, cast, func, select

from app.core.neo4j_driver import get_neo4j
from app.db.session import SessionLocal
from app.models.defects import Defect
from app.models.llm_usage import LLMUsage
from app.services import coverage_dash
from app.services.healing.stats import per_element_heal_stats

log = structlog.get_logger()

# The refresh cadence — well under any scrape interval so the cached snapshot is always fresh.
_REFRESH_SECONDS = 30

# (gauge_name, snapshot_key, help) — the SINGLE source of truth for the 4 gauges. Iterated by
# both the snapshot init and collect() so the names can never drift apart.
_GAUGE_DEFS: tuple[tuple[str, str, str], ...] = (
    ("qa_platform_heal_success_rate", "heal_success_rate", "Self-healing success rate (0..1)"),
    (
        "qa_platform_classification_precision",
        "classification_precision",
        "Defect classification precision applied/(applied+rejected) (0..1)",
    ),
    ("qa_platform_coverage_percent", "coverage_percent", "Lifecycle coverage percent (0..100)"),
    ("qa_platform_llm_cost_usd_total", "llm_cost_usd_total", "Total LLM spend in USD"),
)

# All keys start None (honest absence until the first refresh lands).
_snapshot: dict[str, float | None] = {key: None for _, key, _ in _GAUGE_DEFS}

_refresh_task: asyncio.Task | None = None
_collector: "DomainMetricsCollector | None" = None


async def _refresh_once() -> None:
    """Recompute the 4 metrics over ONE fresh session — each source independently guarded.

    A source raising sets its key None and logs (the main.py:117 log.warning shape); it NEVER
    propagates to /metrics. Reuses the shipped service functions — no metric is recomputed here
    except the two NET-NEW small defect/llm aggregates (the dashboards.py count idiom).
    """
    async with SessionLocal() as db:
        # 1) heal success rate — aggregate the per-element rates into a platform rate.
        try:
            rows = await per_element_heal_stats(db)
            attempts = sum(r["attempts"] for r in rows)
            healed = sum(r["heal_success_rate"] * r["attempts"] for r in rows)
            _snapshot["heal_success_rate"] = (healed / attempts) if attempts else None
        except Exception as exc:  # noqa: BLE001 — never propagate to /metrics
            log.warning("metric_refresh_failed", metric="heal_success_rate", error=str(exc))
            _snapshot["heal_success_rate"] = None

        # 2) lifecycle coverage — graph-derived; a down Neo4j raises → coverage gauge absent.
        try:
            cov = await coverage_dash.coverage(db, driver=get_neo4j())
            _snapshot["coverage_percent"] = float(cov["coverage_percent"])
        except Exception as exc:  # noqa: BLE001
            log.warning("metric_refresh_failed", metric="coverage_percent", error=str(exc))
            _snapshot["coverage_percent"] = None

        # 3) classification precision = applied/(applied+rejected) over REVIEWED defects (D-05).
        #    A NET-NEW small query copying the dashboards.py func.count(...).where(status...) idiom.
        #    Zero reviewed → None (honest absence — never a fabricated rate).
        try:
            applied = int(
                await db.scalar(
                    select(func.count(Defect.id)).where(Defect.status == "applied")
                )
                or 0
            )
            reviewed = int(
                await db.scalar(
                    select(func.count(Defect.id)).where(
                        Defect.status.in_(("applied", "rejected"))
                    )
                )
                or 0
            )
            _snapshot["classification_precision"] = (applied / reviewed) if reviewed else None
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "metric_refresh_failed", metric="classification_precision", error=str(exc)
            )
            _snapshot["classification_precision"] = None

        # 4) total LLM spend — sum(cost_usd), Numeric→float. No rows → a REAL $0.0 (NOT None).
        try:
            total = await db.scalar(select(cast(func.sum(LLMUsage.cost_usd), Numeric(12, 6))))
            _snapshot["llm_cost_usd_total"] = float(total) if total is not None else 0.0
        except Exception as exc:  # noqa: BLE001
            log.warning("metric_refresh_failed", metric="llm_cost_usd_total", error=str(exc))
            _snapshot["llm_cost_usd_total"] = None


async def _refresh_loop() -> None:
    """Recompute the snapshot every _REFRESH_SECONDS — the only DB load the metrics path incurs."""
    while True:
        await _refresh_once()
        await asyncio.sleep(_REFRESH_SECONDS)


class DomainMetricsCollector(Collector):
    """SYNC custom collector — reads the cached _snapshot O(1), NEVER touches the DB.

    A None snapshot key OMITS its gauge (Prometheus reads absent as no-data — honest, never a
    fake 0). A real 0.0 (e.g. $0 LLM spend, 0% coverage) IS a value and is emitted.
    """

    def collect(self):  # noqa: ANN201 — prometheus-client's Collector.collect signature
        for gauge_name, snapshot_key, help_text in _GAUGE_DEFS:
            value = _snapshot[snapshot_key]
            if value is None:  # honest absence — never a fake 0
                continue
            yield GaugeMetricFamily(gauge_name, help_text, value=value)


def start_metrics(app) -> None:  # noqa: ANN001 — FastAPI app, untyped to avoid a circular import
    """Register the collector + start the background refresher. Idempotent (safe across reloads).

    Called from main.py's lifespan startup (the init_redis/init_es precedent). Registering twice on
    the default REGISTRY would raise a duplicate-timeseries error, so registration is guarded.
    """
    global _refresh_task, _collector
    if _collector is None:
        _collector = DomainMetricsCollector()
        REGISTRY.register(_collector)
    if _refresh_task is None or _refresh_task.done():
        _refresh_task = asyncio.create_task(_refresh_loop())


async def stop_metrics() -> None:
    """Cancel the refresher on lifespan shutdown (idempotent). Leaves the collector registered."""
    global _refresh_task
    if _refresh_task is not None:
        _refresh_task.cancel()
        _refresh_task = None
