"""Read-only Cypher: pages, page detail, the Element Repository, graph summary, flows source.

The READ counterpart of `kg/writer.py`. Every query uses `session.execute_read(_read)` (managed
read txns, the read twin of the writer's execute_write) and carries a `LIMIT` as a DoS guard
(V5 / T-05-07 — an unbounded read on a large graph is a denial-of-service). All Cypher is
parameterized; labels/edge-types come from `kg.schema` code constants — page-derived text is
NEVER interpolated (T-05-08). This module holds NO write-Cypher (the single-write-path grep gate
stays green; all writes go through kg/writer.py).

`chain_json` / `history_json` (the Phase-4 locator seam written on :Element) are deserialized
into structured lists here so the router/UI receive the prioritized locator chain + its history
directly per element (KG-05 element-repository half).

`driver` is an optional kwarg defaulting to the lifespan singleton so graph tests inject a
short-lived host driver while production reuses the one pool.
"""

from __future__ import annotations

import json

from neo4j import AsyncDriver

from app.core.neo4j_driver import get_neo4j

# A generous DoS ceiling on every read (V5). SauceDemo is tiny; a real graph stays bounded.
_LIMIT = 1000


async def _read(cypher: str, params: dict, *, driver: AsyncDriver | None) -> list[dict]:
    """Managed execute_read returning a list of plain dict records."""
    drv = driver or get_neo4j()

    async def _tx(tx) -> list[dict]:
        result = await tx.run(cypher, **params)
        return [dict(rec) async for rec in result]

    async with drv.session() as session:
        return await session.execute_read(_tx)


def _loads(raw: str | None) -> list:
    """Tolerant JSON->list deserialize for chain_json/history_json (empty/garbage -> [])."""
    if not raw:
        return []
    try:
        val = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return val if isinstance(val, list) else []


# --- Pages -------------------------------------------------------------------------------

_LIST_PAGES = (
    "MATCH (p:Page) "
    "OPTIONAL MATCH (p)-[:HAS_ELEMENT]->(e:Element) "
    "WITH p, count(e) AS element_count "
    "RETURN p.fingerprint AS fingerprint, p.url AS url, p.title AS title, "
    "       p.first_seen AS first_seen, p.last_verified AS last_verified, element_count "
    "ORDER BY p.url "
    "LIMIT $limit"
)


async def list_pages(*, driver: AsyncDriver | None = None) -> list[dict]:
    """All Page nodes with their element count (the /pages index)."""
    return await _read(_LIST_PAGES, {"limit": _LIMIT}, driver=driver)


_PAGE_DETAIL = (
    "MATCH (p:Page {fingerprint:$fingerprint}) "
    "OPTIONAL MATCH (p)-[:HAS_ELEMENT]->(e:Element) "
    "OPTIONAL MATCH (p)-[:HAS_FORM]->(f:Form) "
    "OPTIONAL MATCH (p)-[r:NavigatesTo]->(t:Page) "
    "RETURN p.fingerprint AS fingerprint, p.url AS url, p.title AS title, "
    "       p.first_seen AS first_seen, p.last_verified AS last_verified, "
    "       collect(DISTINCT {key:e.key, role:e.role, label:e.label}) AS elements, "
    "       collect(DISTINCT {key:f.key}) AS forms, "
    "       collect(DISTINCT {to:t.fingerprint, url:t.url, via:r.via}) AS navigates_to "
    "LIMIT $limit"
)


async def page_detail(fingerprint: str, *, driver: AsyncDriver | None = None) -> dict | None:
    """A single page + its elements, forms, and outbound NavigatesTo edges (with `via`)."""
    rows = await _read(
        _PAGE_DETAIL, {"fingerprint": fingerprint, "limit": _LIMIT}, driver=driver
    )
    if not rows:
        return None
    row = rows[0]
    # collect() emits one {key:null} when there are no matches — drop those empties.
    row["elements"] = [e for e in row.get("elements", []) if e.get("key")]
    row["forms"] = [f for f in row.get("forms", []) if f.get("key")]
    row["navigates_to"] = [n for n in row.get("navigates_to", []) if n.get("to")]
    return row


# --- Element Repository (KG-05 half) -----------------------------------------------------

# RESEARCH ELEMENT_REPO (lines 417-430), verbatim shape + the DoS LIMIT.
_ELEMENT_REPO = (
    "MATCH (p:Page)-[:HAS_ELEMENT]->(e:Element) "
    "RETURN e.key AS key, e.role AS role, e.label AS label, "
    "       e.chain_json AS chain_json, e.history_json AS history_json, "
    "       p.fingerprint AS page_fp, p.url AS page_url, "
    "       e.first_seen AS first_seen, e.last_verified AS last_verified "
    "ORDER BY p.url, e.label "
    "LIMIT $limit"
)


async def element_repository(*, driver: AsyncDriver | None = None) -> list[dict]:
    """Every element + its DESERIALIZED locator chain + history, keyed per element (KG-05).

    The Phase-4 chain_json/history_json strings are parsed into structured lists so the
    router/UI receive the prioritized locator chain + its history directly.
    """
    rows = await _read(_ELEMENT_REPO, {"limit": _LIMIT}, driver=driver)
    for row in rows:
        row["chain"] = _loads(row.pop("chain_json", None))
        row["history"] = _loads(row.pop("history_json", None))
    return rows


_ELEMENT_DETAIL = (
    "MATCH (p:Page)-[:HAS_ELEMENT]->(e:Element {key:$key}) "
    "RETURN e.key AS key, e.role AS role, e.label AS label, "
    "       e.chain_json AS chain_json, e.history_json AS history_json, "
    "       p.fingerprint AS page_fp, p.url AS page_url, "
    "       e.first_seen AS first_seen, e.last_verified AS last_verified "
    "LIMIT $limit"
)


async def element_detail(key: str, *, driver: AsyncDriver | None = None) -> dict | None:
    """A single element's locator chain + history (deserialized)."""
    rows = await _read(_ELEMENT_DETAIL, {"key": key, "limit": _LIMIT}, driver=driver)
    if not rows:
        return None
    row = rows[0]
    row["chain"] = _loads(row.pop("chain_json", None))
    row["history"] = _loads(row.pop("history_json", None))
    return row


# --- Graph summary -----------------------------------------------------------------------

_GRAPH_SUMMARY = (
    "MATCH (n) "
    "WITH labels(n) AS lbls "
    "UNWIND lbls AS label "
    "RETURN label, count(*) AS count "
    "ORDER BY label "
    "LIMIT $limit"
)


async def graph_summary(*, driver: AsyncDriver | None = None) -> dict:
    """Counts by node label for the /graph index — {label: count}."""
    rows = await _read(_GRAPH_SUMMARY, {"limit": _LIMIT}, driver=driver)
    return {r["label"]: int(r["count"]) for r in rows}


# --- Flows source (feeds the pure miner in kg/flows.py) ----------------------------------

_FLOWS_NODES = (
    "MATCH (p:Page) "
    "OPTIONAL MATCH (p)-[:HAS_FORM]->(f:Form) "
    "WITH p, count(f) AS form_count "
    "OPTIONAL MATCH (p)<-[nav:NavigatesTo]-() "
    "WITH p, form_count, count(nav) AS inbound "
    "RETURN p.fingerprint AS fp, p.title AS label, p.url AS url, "
    "       form_count > 0 AS has_form, inbound AS inbound_nav "
    "LIMIT $limit"
)

_FLOWS_EDGES = (
    "MATCH (a:Page)-[r:NavigatesTo|Submits]->(b) "
    "RETURN a.fingerprint AS from_fp, "
    "       coalesce(b.fingerprint, b.key) AS to_fp, "
    "       type(r) AS type, r.via AS via "
    "LIMIT $limit"
)


async def flows_source(*, driver: AsyncDriver | None = None) -> dict:
    """Read the page/edge structure into the in-memory graph the pure miner consumes.

    Returns {"nodes": {fp: {label, url, auth_gated, form}}, "edges": [{from, to, type, via}]}.
    auth_gated is approximated as "the page is not an entry" (it has an inbound NavigatesTo) —
    a deterministic, graph-derived proxy for "behind login" without any LLM judgment. The pure
    `kg.flows.mine_flows` then bounds the traversal (no variable-length Cypher, so A4's
    parameterized-path-range caveat never applies — the bound is enforced in Python).
    """
    node_rows = await _read(_FLOWS_NODES, {"limit": _LIMIT}, driver=driver)
    edge_rows = await _read(_FLOWS_EDGES, {"limit": _LIMIT}, driver=driver)

    nodes = {
        r["fp"]: {
            "label": r.get("label") or "",
            "url": r.get("url") or "",
            "auth_gated": int(r.get("inbound_nav") or 0) > 0,
            "form": bool(r.get("has_form")),
        }
        for r in node_rows
    }
    edges = [
        {"from": r["from_fp"], "to": r["to_fp"], "type": r["type"], "via": r.get("via") or ""}
        for r in edge_rows
        if r.get("from_fp") and r.get("to_fp")
    ]
    return {"nodes": nodes, "edges": edges}
