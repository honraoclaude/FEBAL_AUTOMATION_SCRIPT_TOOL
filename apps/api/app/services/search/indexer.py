"""On-write dual-index hooks + idempotent ensure-mappings + backfill (DASH-06, Task 2).

The search index is a DERIVED, rebuildable view of the Postgres source of truth — NEVER the
source of truth itself. Three rules this module enforces:

  1. ON-WRITE SWALLOW-AND-LOG (Pitfall 3, T-10-19): every `es.index(...)` is wrapped in a broad
     try/except that logs `es_index_skipped` and returns. An ES outage (search profile off,
     transient transport error, ...) must NEVER propagate into — and break — the Postgres commit
     that already happened. The execution/defect write is durable BEFORE the index hook runs; the
     index is best-effort. The mirror of kg/flows.py's broad-except degrade discipline.

  2. INDEX AFTER THE COMMIT (the hook call sites in worker/job.py + defects/pipeline.py call these
     helpers AFTER `await db.commit()` — never before): the row is durable first, then we attempt
     to index it. A failed index leaves a queryable Postgres row that the backfill can later index.

  3. NO SECRETS IN A DOC (T-10-21): the structlog redaction processor already masks
     password/secret/token/credential before render; the docs built here carry only the
     run/flow/verdict/classification/error-text fields — never a raw token.

Indices are TYPELESS (ES 7+ dropped `doc_type`): mappings only, no `_doc` nesting. ensure_indices
is GRACEFUL (the ensure_constraints precedent) — it swallows an unreachable ES at startup so the
api still boots when the search profile is down; the mappings get created on the next reachable
boot (or lazily — ES auto-creates an index on first write if mappings were never ensured).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import structlog
from sqlalchemy import select

from app.core.es_client import get_es
from app.models.defects import Classification, Defect
from app.models.execution_history import TestResult

log = structlog.get_logger()

# --- Index names (the three searchable surfaces; DASH-06) --------------------------------
EXECUTIONS_INDEX = "executions"
FAILURES_INDEX = "failures"
LOGS_INDEX = "logs"

# --- Typeless mappings (ES 7+: mappings only, no doc_type) -------------------------------
# `keyword` for exact-match/filter ids + status vocab; `text` for the full-text searched body
# (error_text/evidence/message); `date` for the created_at timeline; `integer` for confidence.
_EXECUTIONS_MAPPINGS: dict[str, Any] = {
    "properties": {
        "run_id": {"type": "keyword"},
        "flow_id": {"type": "keyword"},
        "verdict": {"type": "keyword"},
        "tier": {"type": "keyword"},
        "error_text": {"type": "text"},
        "created_at": {"type": "date"},
    }
}
_FAILURES_MAPPINGS: dict[str, Any] = {
    "properties": {
        "run_id": {"type": "keyword"},
        "flow_id": {"type": "keyword"},
        "classification": {"type": "keyword"},
        "fingerprint": {"type": "keyword"},
        "confidence": {"type": "integer"},
        "error_text": {"type": "text"},
        "evidence_text": {"type": "text"},
        "jira_key": {"type": "keyword"},
        "created_at": {"type": "date"},
    }
}
# A thin OPTIONAL path (A6): index the structured structlog event MESSAGE text so operators can
# full-text the rendered log line. Redaction runs before render, so no secret reaches this doc.
_LOGS_MAPPINGS: dict[str, Any] = {
    "properties": {
        "run_id": {"type": "keyword"},
        "flow_id": {"type": "keyword"},
        "event": {"type": "keyword"},
        "message": {"type": "text"},
        "created_at": {"type": "date"},
    }
}

_INDEX_MAPPINGS: dict[str, dict[str, Any]] = {
    EXECUTIONS_INDEX: _EXECUTIONS_MAPPINGS,
    FAILURES_INDEX: _FAILURES_MAPPINGS,
    LOGS_INDEX: _LOGS_MAPPINGS,
}


async def ensure_indices(es: Any = None) -> bool:
    """Create the three search indices with their mappings idempotently. GRACEFUL when ES down.

    Run ONCE at lifespan startup (the ensure_constraints precedent). Checks `indices.exists`
    then `indices.create` per index. Catches ANY connection/transport error and logs-and-returns
    False (NEVER raises) so the api still boots when ES is unreachable (search profile inactive);
    the mappings get created on the next reachable boot (or ES auto-creates on first write).
    Returns True when every index was ensured.
    """
    client = es if es is not None else get_es()
    try:
        for index, mappings in _INDEX_MAPPINGS.items():
            if not await client.indices.exists(index=index):
                await client.indices.create(index=index, mappings=mappings)
        log.info("es_indices_ensured", count=len(_INDEX_MAPPINGS))
        return True
    except Exception as exc:  # noqa: BLE001 -- graceful boot: ES may be down at startup
        log.info("es_indices_skipped_es_unreachable", error=str(exc))
        return False


async def index_execution(
    run_id: str,
    flow_id: str,
    *,
    verdict: str,
    error_text: str | None = None,
    tier: str | None = None,
    created_at: str | None = None,
    es: Any = None,
) -> None:
    """On-write index of one execution result into the `executions` index. SWALLOW-AND-LOG.

    Called AFTER the TestResult/TestArtifact Postgres commit (worker/job.py). Doc id is the
    stable `{run_id}:{flow_id}` so a re-index UPSERTs the same doc (idempotent). ANY ES failure
    is logged as `es_index_skipped` and swallowed — the Postgres write is never broken (T-10-19).
    """
    try:
        # get_es() is INSIDE the try: constructing AsyncElasticsearch can itself raise (missing
        # transport extra, an unreachable/misconfigured host) before any request — that must be
        # swallowed too, NEVER escape into the Postgres write path (T-10-19).
        client = es if es is not None else get_es()
        await client.index(
            index=EXECUTIONS_INDEX,
            id=f"{run_id}:{flow_id}",
            document={
                "run_id": run_id,
                "flow_id": flow_id,
                "verdict": verdict,
                "tier": tier,
                "error_text": error_text,
                "created_at": created_at,
            },
        )
    except Exception as exc:  # noqa: BLE001 -- search is best-effort; NEVER break the PG write
        log.info("es_index_skipped", index=EXECUTIONS_INDEX, run_id=run_id, error=str(exc))


async def index_failure(
    run_id: str,
    flow_id: str,
    *,
    classification: str,
    fingerprint: str,
    confidence: int | None = None,
    error_text: str | None = None,
    evidence_text: str | None = None,
    jira_key: str | None = None,
    created_at: str | None = None,
    es: Any = None,
) -> None:
    """On-write index of one classified failure into the `failures` index. SWALLOW-AND-LOG.

    Called AFTER the draft Defect Postgres commit (defects/pipeline.py). Doc id is the stable
    `{run_id}:{flow_id}`. ANY ES failure is logged as `es_index_skipped` and swallowed — the
    Postgres write is never broken (T-10-19).
    """
    try:
        # get_es() is INSIDE the try (see index_execution): client construction can itself raise,
        # and that must be swallowed too — NEVER escape into the Postgres write path (T-10-19).
        client = es if es is not None else get_es()
        await client.index(
            index=FAILURES_INDEX,
            id=f"{run_id}:{flow_id}",
            document={
                "run_id": run_id,
                "flow_id": flow_id,
                "classification": classification,
                "fingerprint": fingerprint,
                "confidence": confidence,
                "error_text": error_text,
                "evidence_text": evidence_text,
                "jira_key": jira_key,
                "created_at": created_at,
            },
        )
    except Exception as exc:  # noqa: BLE001 -- search is best-effort; NEVER break the PG write
        log.info("es_index_skipped", index=FAILURES_INDEX, run_id=run_id, error=str(exc))


def _evidence_text(evidence: dict | None) -> str | None:
    """Flatten a Classification.evidence JSON snapshot to a single searchable text blob.

    The redaction processor runs before render in the log path; the evidence snapshot persisted
    by the deterministic classifier carries no secret fields, but we still only pull the textual
    error/notes here — never echo a token (T-10-21).
    """
    if not evidence:
        return None
    parts: list[str] = []
    for key in ("error_text", "error", "notes", "summary"):
        val = evidence.get(key)
        if isinstance(val, str) and val:
            parts.append(val)
    return " ".join(parts) or None


async def backfill(db: Any, es: Any = None, *, bulk_runner: Any = None) -> tuple[int, list]:
    """Reindex existing Postgres rows into ES via `elasticsearch.helpers.async_bulk`.

    Streams every TestResult → the `executions` index and every Classification/Defect →
    the `failures` index as bulk index actions (stable `{run_id}:{flow_id}` ids, so a re-run
    UPSERTs rather than duplicates). The operator invokes it via
    `uv run python -c "import asyncio; from app.db.session import SessionLocal; ...; asyncio.run(backfill(db))"`
    — no new CLI framework needed. Returns async_bulk's (ok, errors).

    `bulk_runner` defaults to `elasticsearch.helpers.async_bulk` (the production path); the keyless
    contract test injects a recording runner so it can assert the produced action stream WITHOUT
    driving async_bulk's deep client internals (transport/serializers) against the in-memory fake.
    """
    client = es if es is not None else get_es()

    if bulk_runner is None:
        from elasticsearch.helpers import async_bulk as bulk_runner

    async def _actions() -> AsyncIterator[dict]:
        for r in (await db.scalars(select(TestResult))).all():
            yield {
                "_index": EXECUTIONS_INDEX,
                "_id": f"{r.run_id}:{r.flow_id}",
                "_source": {
                    "run_id": r.run_id,
                    "flow_id": r.flow_id,
                    "verdict": r.verdict,
                    "error_text": r.error_text,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                },
            }
        for c in (await db.scalars(select(Classification))).all():
            yield {
                "_index": FAILURES_INDEX,
                "_id": f"{c.run_id}:{c.flow_id}",
                "_source": {
                    "run_id": c.run_id,
                    "flow_id": c.flow_id,
                    "classification": c.classification,
                    "confidence": c.confidence,
                    "error_text": _evidence_text(c.evidence),
                    "evidence_text": _evidence_text(c.evidence),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                },
            }
        for d in (await db.scalars(select(Defect))).all():
            yield {
                "_index": FAILURES_INDEX,
                "_id": f"{d.run_id}:{d.flow_id}",
                "_source": {
                    "run_id": d.run_id,
                    "flow_id": d.flow_id,
                    "classification": d.classification,
                    "fingerprint": d.fingerprint,
                    "confidence": d.confidence,
                    "jira_key": d.jira_key,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                },
            }

    ok, errors = await bulk_runner(client, _actions())
    log.info("es_backfill_done", ok=ok, errors=len(errors) if errors else 0)
    return ok, errors
