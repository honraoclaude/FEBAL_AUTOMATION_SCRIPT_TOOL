"""In-memory AsyncElasticsearch double for the keyless search contract (10-04, Open Q3).

The index/search/highlight CONTRACT is exercised against this fake — no `elasticsearch`
server, no `search` profile, no keys (the live round-trip is the `search`-marked functional
test). It implements the SUBSET of the AsyncElasticsearch async surface the search seam touches:

  - ``index(index, id, document)``       — store one doc (the on-write dual-index hook)
  - ``search(index, query, highlight, size)`` — naive substring multi_match + a highlight block,
        returning an ES-shaped ``{"hits": {"hits": [...], "total": {...}}}`` envelope
  - ``indices.create / indices.exists``  — the ensure-mappings idempotent create
  - ``bulk``                             — the actions sink ``elasticsearch.helpers.async_bulk`` drives
  - ``close``                            — lifespan parity (no-op)

A ``raising=True`` variant raises on EVERY operation — the swallow-and-log proof (an ES outage
must NEVER break the Postgres write) and the search-degrade proof (a ConnectionError → honest 503)
both inject it. The raised type is the real ``elasticsearch.exceptions.ConnectionError`` WHEN the
package is installed (so the main.py 503 handler matches), falling back to a local stand-in class
of the same name when it is not yet installed (pre-gate import safety).

This double lives under tests/fixtures (NOT app/) — it is test scaffolding, never shipped code.
"""

from __future__ import annotations

from typing import Any

try:  # the real transport error so the main.py @exception_handler(ESConnectionError) matches
    from elasticsearch.exceptions import ConnectionError as ESConnectionError  # type: ignore
except Exception:  # noqa: BLE001 — pre-gate import safety: the package may not be installed yet

    class ESConnectionError(Exception):  # type: ignore[no-redef]
        """Stand-in for elasticsearch.exceptions.ConnectionError before the gated install."""


class _FakeIndices:
    """The ``es.indices`` namespace — only the idempotent ensure-mappings calls are used."""

    def __init__(self, parent: "FakeAsyncElasticsearch") -> None:
        self._parent = parent

    async def exists(self, *, index: str) -> bool:
        self._parent._raise_if_configured()
        return index in self._parent.mappings

    async def create(self, *, index: str, mappings: dict | None = None, **_: Any) -> dict:
        self._parent._raise_if_configured()
        # idempotent at the seam: ensure_indices checks exists() first, but be tolerant here too.
        self._parent.mappings.setdefault(index, mappings or {})
        self._parent.store.setdefault(index, {})
        return {"acknowledged": True, "index": index}


class FakeAsyncElasticsearch:
    """A minimal in-memory stand-in for ``AsyncElasticsearch`` (keyless contract double).

    Args:
        raising: when True EVERY operation raises ``ESConnectionError`` — the ES-down proof
            (swallow-and-log on write; honest 503 on search). Default False (a recording double).
    """

    def __init__(self, *, raising: bool = False) -> None:
        self.raising = raising
        # index name -> {doc_id -> source dict}
        self.store: dict[str, dict[str, dict]] = {}
        # index name -> mappings (set by indices.create)
        self.mappings: dict[str, dict] = {}
        # every (index, id, document) the seam wrote — assertion surface for the on-write tests
        self.indexed: list[dict] = []
        # every bulk action batch async_bulk pushed — assertion surface for the backfill test
        self.bulk_actions: list[dict] = []
        self.indices = _FakeIndices(self)

    def _raise_if_configured(self) -> None:
        if self.raising:
            raise ESConnectionError("fake elasticsearch is down")

    def options(self, **_: Any) -> "FakeAsyncElasticsearch":
        """`elasticsearch.helpers.async_bulk` calls `client.options()` before `client.bulk(...)`.

        The real client returns a per-request-options-bound client; the fake is stateless, so it
        returns itself (the bulk sink is the same in-memory store)."""
        return self

    async def index(self, *, index: str, id: str | None = None, document: dict, **_: Any) -> dict:  # noqa: A002
        self._raise_if_configured()
        self.store.setdefault(index, {})
        doc_id = id if id is not None else f"auto-{len(self.store[index])}"
        self.store[index][doc_id] = dict(document)
        self.indexed.append({"index": index, "id": doc_id, "document": dict(document)})
        return {"_index": index, "_id": doc_id, "result": "created"}

    async def bulk(self, *, operations: list | None = None, **_: Any) -> dict:
        """The low-level bulk endpoint async_bulk batches into. operations is a flat
        [action_meta, source, action_meta, source, ...] list (the ES bulk wire format)."""
        self._raise_if_configured()
        ops = operations or []
        items = []
        # pairs of (meta, source) for index actions
        i = 0
        while i < len(ops):
            meta = ops[i]
            action = next(iter(meta))  # "index" / "create" / ...
            target = meta[action]
            source = ops[i + 1] if i + 1 < len(ops) else {}
            idx = target.get("_index", "")
            doc_id = target.get("_id", f"auto-{i}")
            self.store.setdefault(idx, {})
            self.store[idx][doc_id] = dict(source)
            self.bulk_actions.append({"index": idx, "id": doc_id, "source": dict(source)})
            items.append({action: {"_index": idx, "_id": doc_id, "status": 201}})
            i += 2
        return {"errors": False, "items": items}

    async def search(
        self,
        *,
        index: str | None = None,
        query: dict | None = None,
        highlight: dict | None = None,
        size: int = 10,
        **_: Any,
    ) -> dict:
        """Naive multi_match: substring-match the query VALUE across the requested fields.

        Reads the query strictly from ``query["multi_match"]["query"]`` (a structured VALUE,
        never a concatenated DSL string) — the injection-mitigation contract. Builds a highlight
        block by wrapping the first matched fragment in <em> tags for each highlighted field.
        """
        self._raise_if_configured()
        mm = (query or {}).get("multi_match", {})
        q = str(mm.get("query", "") or "").lower()
        fields = mm.get("fields", []) or []
        hl_fields = list((highlight or {}).get("fields", {}).keys())

        targets = [t.strip() for t in (index or "").split(",") if t.strip()] or list(self.store)
        hits: list[dict] = []
        for idx in targets:
            for doc_id, source in self.store.get(idx, {}).items():
                matched_field = None
                for f in fields:
                    val = source.get(f)
                    if isinstance(val, str) and q and q in val.lower():
                        matched_field = f
                        break
                if matched_field is None:
                    continue
                hit = {"_index": idx, "_id": doc_id, "_score": 1.0, "_source": dict(source)}
                if hl_fields:
                    hl: dict[str, list[str]] = {}
                    for f in hl_fields:
                        val = source.get(f)
                        if isinstance(val, str) and q and q in val.lower():
                            hl[f] = [val.replace(val, f"<em>{val}</em>")]
                    if hl:
                        hit["highlight"] = hl
                hits.append(hit)
                if len(hits) >= size:
                    break

        return {
            "took": 1,
            "timed_out": False,
            "hits": {"total": {"value": len(hits), "relation": "eq"}, "hits": hits},
        }

    async def close(self) -> None:  # lifespan parity — nothing to release in-memory
        return None
