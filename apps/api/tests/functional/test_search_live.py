"""DASH-06 live ES round-trip (search-profile-gated, NO live_llm).

Indexes a doc into a REAL Elasticsearch under the `search` compose profile, refreshes, then
searches it back through the REAL query.search() — proving the mappings + multi_match + highlight
contract end-to-end against the actual 9.x server (the FakeAsyncElasticsearch contract tests cover
the keyless path; this is the one live proof).

Marked `search` (+ `functional`): the deterministic gate excludes it; run it explicitly under the
search profile. The fixture SKIPS when ES is unreachable so the suite never hard-fails on a
profile that is off.

3GB-CAP SEQUENCING: ES (mem_limit 1536m) and neo4j (graph_mode) must NOT both be up with the full
app under the 3GB WSL cap — run this with neo4j OFF (search_mode), exactly as the graph-marked
tests run with web stopped. Start it with:

    docker compose --profile search up -d --wait elasticsearch
    cd apps/api && uv run python -m pytest -m search tests/functional/test_search_live.py -q

Run: cd apps/api && uv run python -m pytest -m search tests/functional/test_search_live.py -q
"""

from __future__ import annotations

import os
import uuid

import pytest
from elasticsearch import AsyncElasticsearch

from app.services.search import indexer
from app.services.search import query as search_query

pytestmark = [pytest.mark.functional, pytest.mark.search]


def _host_es_url() -> str:
    url = os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200")
    return url.replace("://elasticsearch:", "://localhost:")


@pytest.fixture
async def es_client():
    """A real AsyncElasticsearch on the search-profile ES; SKIP when it is unreachable."""
    try:
        client = AsyncElasticsearch(_host_es_url())
    except Exception:  # noqa: BLE001 — transport/construct issue: skip, never hard-fail
        pytest.skip("Elasticsearch client could not be constructed — search profile not set up.")
    try:
        if not await client.ping():
            await client.close()
            pytest.skip("Elasticsearch unreachable — start the search profile to run this test.")
    except Exception:  # noqa: BLE001 — profile off / not started: skip, never hard-fail
        await client.close()
        pytest.skip("Elasticsearch unreachable — start the search profile to run this test.")
    try:
        yield client
    finally:
        await client.close()


async def test_index_then_search_roundtrips(es_client) -> None:
    """An indexed execution doc is found + highlighted by a real multi_match search."""
    run_id = f"live-{uuid.uuid4().hex}"
    flow_id = "checkout"
    unique = f"zzq{uuid.uuid4().hex[:8]}"  # a token unique to this run so the search is exact

    await indexer.ensure_indices(es_client)
    await indexer.index_execution(
        run_id,
        flow_id,
        verdict="product_failure",
        error_text=f"checkout {unique} button not visible",
        es=es_client,
    )
    # make the just-indexed doc searchable immediately
    await es_client.indices.refresh(index=indexer.EXECUTIONS_INDEX)

    try:
        hits = await search_query.search(unique, es=es_client)
        assert any(h["id"] == f"{run_id}:{flow_id}" for h in hits)
        hit = next(h for h in hits if h["id"] == f"{run_id}:{flow_id}")
        assert unique in str(hit["highlight"].get("error_text", "")).lower() or \
            unique in str(hit["source"].get("error_text", "")).lower()
    finally:
        await es_client.delete(
            index=indexer.EXECUTIONS_INDEX, id=f"{run_id}:{flow_id}", ignore=[404]
        )
