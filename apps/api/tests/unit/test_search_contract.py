"""Keyless search CONTRACT proof (DASH-06, Tasks 2 & 3) over the FakeAsyncElasticsearch double.

NO `elasticsearch` server, NO `search` profile, NO keys — the index/search/highlight/backfill
contract is exercised entirely against tests/fixtures/fake_es.FakeAsyncElasticsearch. Asserts:

  Task 2 (indexer):
    - index_execution / index_failure with a RECORDING fake write the right doc to the right
      index with the stable `{run_id}:{flow_id}` id and the verdict/classification fields.
    - index_execution / index_failure with a RAISING fake SWALLOW-AND-LOG — they return WITHOUT
      raising (an ES outage NEVER breaks the Postgres write path — Pitfall 3 / T-10-19).
    - ensure_indices is idempotent + GRACEFUL (a raising fake does not raise — the boot precedent).
    - backfill yields async_bulk index actions for the executions + failures indices.

  Task 3 (query):
    - search() issues a multi_match with q as the structured query VALUE (never concatenated) +
      a highlight block; returns a typed [{index, id, score, source, highlight}] list.

Run: cd apps/api && uv run python -m pytest tests/unit/test_search_contract.py -q
"""

from __future__ import annotations

import pytest

from app.services.search import query as search_query
from app.services.search.indexer import (
    EXECUTIONS_INDEX,
    FAILURES_INDEX,
    backfill,
    ensure_indices,
    index_execution,
    index_failure,
)
from tests.fixtures.fake_es import FakeAsyncElasticsearch

pytestmark = pytest.mark.asyncio


# --- Task 2: on-write index (success) ----------------------------------------------------

async def test_index_execution_writes_doc_to_executions_index() -> None:
    es = FakeAsyncElasticsearch()
    await index_execution("run-1", "flow-a", verdict="product_failure", error_text="boom", es=es)

    assert es.indexed == [
        {
            "index": EXECUTIONS_INDEX,
            "id": "run-1:flow-a",
            "document": {
                "run_id": "run-1",
                "flow_id": "flow-a",
                "verdict": "product_failure",
                "tier": None,
                "error_text": "boom",
                "created_at": None,
            },
        }
    ]
    # the stable id makes a re-index an UPSERT (idempotent), not a duplicate
    assert "run-1:flow-a" in es.store[EXECUTIONS_INDEX]


async def test_index_failure_writes_doc_to_failures_index() -> None:
    es = FakeAsyncElasticsearch()
    await index_failure(
        "run-2", "flow-b", classification="product_defect", fingerprint="abc123",
        confidence=88, error_text="assert failed", es=es,
    )

    [doc] = es.indexed
    assert doc["index"] == FAILURES_INDEX
    assert doc["id"] == "run-2:flow-b"
    assert doc["document"]["classification"] == "product_defect"
    assert doc["document"]["fingerprint"] == "abc123"
    assert doc["document"]["confidence"] == 88


# --- Task 2: on-write index SWALLOWS an ES failure (the PG-write-never-broken proof) ------

async def test_index_execution_swallows_es_failure() -> None:
    es = FakeAsyncElasticsearch(raising=True)
    # MUST NOT raise — a down ES never breaks the Postgres write path (T-10-19).
    await index_execution("run-3", "flow-c", verdict="passed", es=es)
    assert es.indexed == []  # nothing recorded, but no exception escaped


async def test_index_failure_swallows_es_failure() -> None:
    es = FakeAsyncElasticsearch(raising=True)
    await index_failure("run-4", "flow-d", classification="automation", fingerprint="z", es=es)
    assert es.indexed == []


# --- Task 2: ensure_indices idempotent + graceful ----------------------------------------

async def test_ensure_indices_creates_three_indices() -> None:
    es = FakeAsyncElasticsearch()
    ok = await ensure_indices(es)
    assert ok is True
    assert {"executions", "failures", "logs"} <= set(es.mappings)
    # idempotent — a second call does not raise / re-create errors
    assert await ensure_indices(es) is True


async def test_ensure_indices_graceful_when_es_down() -> None:
    es = FakeAsyncElasticsearch(raising=True)
    # MUST NOT raise — the api boots when the search profile is down (the ensure_constraints precedent)
    assert await ensure_indices(es) is False


# --- Task 2: backfill yields bulk actions ------------------------------------------------

class _FakeScalarResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def all(self) -> list:
        return self._rows


class _Row:
    def __init__(self, **kw) -> None:
        self.__dict__.update(kw)
        self.__dict__.setdefault("created_at", None)


class _FakeDB:
    """Returns seeded rows per model — a keyless stand-in for the AsyncSession backfill reads."""

    def __init__(self, by_model: dict) -> None:
        self._by_model = by_model

    async def scalars(self, stmt):  # noqa: ANN001
        # the first FROM entity of the select identifies the model
        model = stmt.column_descriptions[0]["entity"]
        return _FakeScalarResult(self._by_model.get(model, []))


async def test_backfill_yields_bulk_actions_for_both_indices() -> None:
    from app.models.defects import Classification, Defect
    from app.models.execution_history import TestResult

    db = _FakeDB(
        {
            TestResult: [_Row(run_id="r1", flow_id="f1", verdict="passed", error_text=None)],
            Classification: [
                _Row(run_id="r1", flow_id="f1", classification="product_defect",
                     confidence=90, evidence={"error_text": "boom"})
            ],
            Defect: [
                _Row(run_id="r1", flow_id="f1", classification="product_defect",
                     fingerprint="fp1", confidence=90, jira_key=None)
            ],
        }
    )
    es = FakeAsyncElasticsearch()

    # A recording stand-in for elasticsearch.helpers.async_bulk: it consumes the SAME async action
    # iterator backfill builds (the production async_bulk contract) without driving async_bulk's deep
    # client internals (transport/serializers) against the in-memory fake.
    recorded: list[dict] = []

    async def _fake_async_bulk(client, actions):  # noqa: ANN001
        async for a in actions:
            recorded.append(a)
        return len(recorded), []

    ok, errors = await backfill(db, es=es, bulk_runner=_fake_async_bulk)

    assert ok == 3  # one execution + one classification + one defect
    assert not errors
    indices = {a["_index"] for a in recorded}
    assert indices == {EXECUTIONS_INDEX, FAILURES_INDEX}
    # stable {run_id}:{flow_id} ids so a re-run UPSERTs rather than duplicates
    assert {a["_id"] for a in recorded} == {"r1:f1"}


# --- Task 3: search() parameterized multi_match + highlight ------------------------------

async def test_search_returns_typed_hits_with_highlight() -> None:
    es = FakeAsyncElasticsearch()
    await index_execution("run-9", "login", verdict="product_failure",
                          error_text="login button not visible", es=es)
    # the executions doc uses 'error_text'; the fake searches the same text fields query.py declares
    hits = await search_query.search("login", es=es)

    assert len(hits) == 1
    hit = hits[0]
    assert hit["index"] == EXECUTIONS_INDEX
    assert hit["id"] == "run-9:login"
    assert hit["source"]["error_text"] == "login button not visible"
    assert "error_text" in hit["highlight"]


async def test_search_passes_q_as_structured_value_not_concatenated(monkeypatch) -> None:
    """The injection-mitigation contract (T-10-17): q reaches the DSL as a VALUE, never a string."""
    captured: dict = {}

    class _Spy(FakeAsyncElasticsearch):
        async def search(self, *, query=None, **kw):  # noqa: ANN001
            captured["query"] = query
            return await super().search(query=query, **kw)

    es = _Spy()
    await search_query.search("malicious\" OR 1=1", es=es)

    # q lives at query.multi_match.query as the exact VALUE — never spliced into a DSL string
    assert captured["query"]["multi_match"]["query"] == 'malicious" OR 1=1'
