"""THE single Neo4j write path (KG-05) — idempotent fingerprint-MERGE + freshness (KG-03).

Lifted from `explorer/nodes.py` (`_build_persist_cypher`/`_write_workflow_step`/
`_write_form_validation` + their `execute_write` bodies). The only semantic edits from the
Phase-4 originals: (a) Page MERGEs on `$fingerprint` (was `key`); (b) the freshness split —
`ON CREATE SET first_seen=$now` / `ON MATCH SET last_verified=$now` + a `coalesce` so a
freshly-created node also carries `last_verified` in the same statement; first_seen is NEVER
touched on `ON MATCH` (Pitfall 2). Element/Button/Form/BusinessEntity keep their unique
key/name MERGE.

Every function preserves the Phase-3/4 invariant (SC1) lifted verbatim:
  - managed `execute_write` against the lifespan `get_neo4j()` singleton (NEVER a second driver)
  - parameterized Cypher ONLY — labels/edge-types are `kg/schema.py` code constants, never
    interpolated from page-derived text (Cypher-injection mitigation, T-04-14 / T-05-01)
  - a `RETURN count(*) AS n` read-back guard: a 0-count write RAISES (no silent no-op)

`driver` is an optional kwarg defaulting to the lifespan singleton so tests can inject a
short-lived host driver; production callers omit it and reuse the one pool.
"""

from __future__ import annotations

from neo4j import AsyncDriver

from app.core.neo4j_driver import get_neo4j
from app.services.kg import schema


async def _write(cypher: str, params: dict, *, driver: AsyncDriver | None, what: str) -> dict:
    """Managed execute_write + read-back guard (the SC1 invariant, lifted verbatim).

    Returns the single record (callers may read first_seen/last_verified off it). Raises when
    the write persisted nothing (record absent or count < 1).
    """
    drv = driver or get_neo4j()

    async def _tx(tx) -> dict | None:
        result = await tx.run(cypher, **params)
        record = await result.single()
        return dict(record) if record else None

    async with drv.session() as session:
        rec = await session.execute_write(_tx)
    if not rec or int(rec.get("n", 0)) < 1:
        raise RuntimeError(f"kg_writer.{what} persisted nothing to Neo4j")
    return rec


# --- Node upserts (idempotent MERGE + freshness) -----------------------------------------

# Page MERGEs on the structural fingerprint (constraint-backed). first_seen ONLY on create;
# last_verified bumped on match; the coalesce line guarantees a created node is fresh too.
_UPSERT_PAGE = (
    "MERGE (p:Page {fingerprint:$fingerprint}) "
    "ON CREATE SET p.first_seen=$now "
    "ON MATCH SET p.last_verified=$now "
    "SET p.last_verified=coalesce(p.last_verified,$now), "
    "    p.run_id=$run_id, p.url=$url, p.title=$title, p.screenshot_path=$shot "
    "RETURN p.first_seen AS first_seen, p.last_verified AS last_verified, count(*) AS n"
)


async def upsert_page(
    *, fingerprint: str, url: str, title: str, run_id: str,
    screenshot_path: str | None, now: str, driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _UPSERT_PAGE,
        {"fingerprint": fingerprint, "url": url, "title": title, "run_id": run_id,
         "shot": screenshot_path, "now": now},
        driver=driver, what="upsert_page",
    )


_UPSERT_ELEMENT = (
    "MERGE (e:Element {key:$key}) "
    "ON CREATE SET e.first_seen=$now, e.role=$role, e.label=$label "
    "ON MATCH SET e.last_verified=$now "
    "SET e.last_verified=coalesce(e.last_verified,$now), "
    "    e.run_id=$run_id, e.chain_json=$chain_json, e.history_json=$history_json "
    "RETURN count(*) AS n"
)


async def upsert_element(
    *, key: str, role: str, label: str, chain_json: str, history_json: str,
    run_id: str, now: str, driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _UPSERT_ELEMENT,
        {"key": key, "role": role, "label": label, "chain_json": chain_json,
         "history_json": history_json, "run_id": run_id, "now": now},
        driver=driver, what="upsert_element",
    )


_UPSERT_BUTTON = (
    "MERGE (b:Button {key:$key}) "
    "ON CREATE SET b.first_seen=$now "
    "ON MATCH SET b.last_verified=$now "
    "SET b.last_verified=coalesce(b.last_verified,$now), "
    "    b.label=$label, b.role=$role, b.page_fingerprint=$page_fingerprint, b.run_id=$run_id "
    "RETURN count(*) AS n"
)


async def upsert_button(
    *, key: str, label: str, role: str, page_fingerprint: str, run_id: str,
    now: str, driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _UPSERT_BUTTON,
        {"key": key, "label": label, "role": role, "page_fingerprint": page_fingerprint,
         "run_id": run_id, "now": now},
        driver=driver, what="upsert_button",
    )


_UPSERT_FORM = (
    "MERGE (f:Form {key:$key}) "
    "ON CREATE SET f.first_seen=$now "
    "ON MATCH SET f.last_verified=$now "
    "SET f.last_verified=coalesce(f.last_verified,$now), "
    "    f.validation_rules=$validation_rules, f.run_id=$run_id "
    "RETURN count(*) AS n"
)


async def upsert_form(
    *, key: str, validation_rules: str, run_id: str, now: str,
    driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _UPSERT_FORM,
        {"key": key, "validation_rules": validation_rules, "run_id": run_id, "now": now},
        driver=driver, what="upsert_form",
    )


_UPSERT_WORKFLOW = (
    "MERGE (w:Workflow {name:$name, run_id:$run_id}) "
    "ON CREATE SET w.first_seen=$now "
    "ON MATCH SET w.last_verified=$now "
    "SET w.last_verified=coalesce(w.last_verified,$now) "
    "RETURN count(*) AS n"
)


async def upsert_workflow(
    *, name: str, run_id: str, now: str, driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _UPSERT_WORKFLOW,
        {"name": name, "run_id": run_id, "now": now},
        driver=driver, what="upsert_workflow",
    )


_UPSERT_BUSINESS_ENTITY = (
    "MERGE (be:BusinessEntity {name:$name}) "
    "ON CREATE SET be.first_seen=$now, be.kind=$kind "
    "ON MATCH SET be.last_verified=$now "
    "SET be.last_verified=coalesce(be.last_verified,$now), be.kind=$kind "
    "RETURN count(*) AS n"
)


async def upsert_business_entity(
    *, name: str, kind: str, now: str, driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _UPSERT_BUSINESS_ENTITY,
        {"name": name, "kind": kind, "now": now},
        driver=driver, what="upsert_business_entity",
    )


# --- Edge links (each read-back guarded) -------------------------------------------------

_LINK_NAVIGATES_TO = (
    "MATCH (a:Page {fingerprint:$from_fp}) "
    "MATCH (b:Page {fingerprint:$to_fp}) "
    "MERGE (a)-[r:NavigatesTo]->(b) "
    "SET r.via=$via, r.run_id=$run_id "
    "RETURN count(r) AS n"
)


async def link_navigates_to(
    *, from_fingerprint: str, to_fingerprint: str, via: str, run_id: str,
    driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _LINK_NAVIGATES_TO,
        {"from_fp": from_fingerprint, "to_fp": to_fingerprint, "via": via, "run_id": run_id},
        driver=driver, what="link_navigates_to",
    )


_LINK_HAS_ELEMENT = (
    "MATCH (p:Page {fingerprint:$page_fp}) "
    "MATCH (e:Element {key:$element_key}) "
    "MERGE (p)-[r:HAS_ELEMENT]->(e) "
    "SET r.run_id=$run_id "
    "RETURN count(r) AS n"
)


async def link_has_element(
    *, page_fingerprint: str, element_key: str, run_id: str,
    driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _LINK_HAS_ELEMENT,
        {"page_fp": page_fingerprint, "element_key": element_key, "run_id": run_id},
        driver=driver, what="link_has_element",
    )


_LINK_HAS_BUTTON = (
    "MATCH (p:Page {fingerprint:$page_fp}) "
    "MATCH (b:Button {key:$button_key}) "
    "MERGE (p)-[r:HAS_BUTTON]->(b) "
    "SET r.run_id=$run_id "
    "RETURN count(r) AS n"
)


async def link_has_button(
    *, page_fingerprint: str, button_key: str, run_id: str,
    driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _LINK_HAS_BUTTON,
        {"page_fp": page_fingerprint, "button_key": button_key, "run_id": run_id},
        driver=driver, what="link_has_button",
    )


_LINK_HAS_FORM = (
    "MATCH (p:Page {fingerprint:$page_fp}) "
    "MATCH (f:Form {key:$form_key}) "
    "MERGE (p)-[r:HAS_FORM]->(f) "
    "SET r.run_id=$run_id "
    "RETURN count(r) AS n"
)


async def link_has_form(
    *, page_fingerprint: str, form_key: str, run_id: str,
    driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _LINK_HAS_FORM,
        {"page_fp": page_fingerprint, "form_key": form_key, "run_id": run_id},
        driver=driver, what="link_has_form",
    )


_LINK_SUBMITS = (
    "MATCH (p:Page {fingerprint:$page_fp}) "
    "MATCH (f:Form {key:$form_key}) "
    "MERGE (p)-[r:Submits]->(f) "
    "SET r.run_id=$run_id "
    "RETURN count(r) AS n"
)


async def link_submits(
    *, page_fingerprint: str, form_key: str, run_id: str,
    driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _LINK_SUBMITS,
        {"page_fp": page_fingerprint, "form_key": form_key, "run_id": run_id},
        driver=driver, what="link_submits",
    )


def _state_change_cypher(edge_type: str) -> str:
    """Form-[edge]->BusinessEntity. edge_type is a kg.schema CODE CONSTANT, never page text."""
    return (
        "MATCH (f:Form {key:$form_key}) "
        "MATCH (be:BusinessEntity {name:$entity_name}) "
        f"MERGE (f)-[r:{edge_type}]->(be) "
        "SET r.run_id=$run_id "
        "RETURN count(r) AS n"
    )


_LINK_CREATES = _state_change_cypher(schema.CREATES)
_LINK_UPDATES = _state_change_cypher(schema.UPDATES)
_LINK_DELETES = _state_change_cypher(schema.DELETES)


async def link_creates(
    *, form_key: str, entity_name: str, run_id: str, driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _LINK_CREATES,
        {"form_key": form_key, "entity_name": entity_name, "run_id": run_id},
        driver=driver, what="link_creates",
    )


async def link_updates(
    *, form_key: str, entity_name: str, run_id: str, driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _LINK_UPDATES,
        {"form_key": form_key, "entity_name": entity_name, "run_id": run_id},
        driver=driver, what="link_updates",
    )


async def link_deletes(
    *, form_key: str, entity_name: str, run_id: str, driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _LINK_DELETES,
        {"form_key": form_key, "entity_name": entity_name, "run_id": run_id},
        driver=driver, what="link_deletes",
    )


_LINK_STEP = (
    "MERGE (w:Workflow {name:$flow, run_id:$run_id}) "
    "MATCH (p:Page {fingerprint:$page_fp}) "
    "MERGE (w)-[s:STEP {order:$order}]->(p) "
    "SET s.run_id=$run_id "
    "RETURN count(*) AS n"
)


async def link_step(
    *, flow: str, order: int, page_fingerprint: str, run_id: str,
    driver: AsyncDriver | None = None,
) -> dict:
    return await _write(
        _LINK_STEP,
        {"flow": flow, "order": order, "page_fp": page_fingerprint, "run_id": run_id},
        driver=driver, what="link_step",
    )
