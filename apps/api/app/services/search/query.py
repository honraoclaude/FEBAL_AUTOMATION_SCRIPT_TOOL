"""search() — parameterized multi_match + highlight over the three indices (DASH-06, Task 3).

INJECTION MITIGATION (T-10-17, the reader.py parameterized-query discipline): the user's query
string `q` is passed as a STRUCTURED VALUE inside `query["multi_match"]["query"]` — NEVER
string-concatenated / f-stringed / %-formatted into the DSL. The ES query DSL is built as a Python
dict; `q` is one leaf VALUE the transport serializes. There is no code path that interpolates `q`
into a DSL string.

GRACEFUL-DEGRADE (T-10-20): a connection error is NOT swallowed here — it bubbles up as
`elasticsearch.exceptions.ConnectionError`, which the main.py `@app.exception_handler` turns into an
honest 503 "Search is unavailable…". This is deliberate: returning an empty hit list on an ES
outage would LIE (zero results vs unavailable). The on-write index path swallows (best-effort write);
the read path surfaces the outage honestly.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.core.es_client import get_es
from app.services.search.indexer import (
    EXECUTIONS_INDEX,
    FAILURES_INDEX,
    LOGS_INDEX,
)

log = structlog.get_logger()

# The default fan-out: search all three surfaces at once (the comma-joined ES multi-index target).
_ALL_INDICES = f"{EXECUTIONS_INDEX},{FAILURES_INDEX},{LOGS_INDEX}"

# The full-text fields the multi_match scores across (the `text`-typed mapping fields). keyword
# id/verdict fields are intentionally excluded — they are filters, not free-text search targets.
_SEARCH_FIELDS = ["error_text", "evidence_text", "message"]

# The fields ES returns highlighted fragments for (wrapped in <em> by default).
_HIGHLIGHT_FIELDS = {"error_text": {}, "evidence_text": {}, "message": {}}


async def search(q: str, *, index: str | None = None, es: Any = None, size: int = 50) -> list[dict]:
    """Run a parameterized multi_match search and return a typed hit list.

    Args:
        q: the untrusted user query — passed as a STRUCTURED VALUE (never concatenated into the DSL).
        index: an optional scoped index (one of executions/failures/logs); defaults to all three.
        es: an optional injected client (the FakeAsyncElasticsearch contract double); defaults to
            the lifespan client.
        size: max hits (default 50).

    Returns a list of `{index, id, score, source, highlight}` dicts. A connection error is NOT
    caught — it bubbles to the main.py ESConnectionError→503 handler (graceful-degrade, never a
    fake empty list).
    """
    client = es if es is not None else get_es()
    target = index if index else _ALL_INDICES

    resp = await client.search(
        index=target,
        query={"multi_match": {"query": q, "fields": _SEARCH_FIELDS}},
        highlight={"fields": _HIGHLIGHT_FIELDS},
        size=size,
    )

    return [
        {
            "index": h["_index"],
            "id": h["_id"],
            "score": h.get("_score"),
            "source": h.get("_source", {}),
            "highlight": h.get("highlight", {}),
        }
        for h in resp["hits"]["hits"]
    ]
