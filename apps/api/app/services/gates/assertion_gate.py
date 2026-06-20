"""Structured Then→KG no-vacuous-assertion gate (GEN-03 / D-03) — THE novel trust mechanism.

Generation emits each Then step annotated with the KG node/edge it asserts (a page state /
element / Creates-Updates-Deletes outcome). This gate DETERMINISTICALLY verifies EVERY Then
resolves to an existing assertion in the graph via read-only existence Cypher. Any Then with no
graph-backed outcome is rejected as vacuous. NOT LLM judgment, NOT heuristic text-match.

What counts as VACUOUS:
  - a Then with no kg_ref at all,
  - a Then whose kg_ref does not resolve to an existing node/edge in Neo4j,
  - a Then with an unknown `kind` OR an edge_type outside {Creates,Updates,Deletes},
  - a scenario with zero Then steps (nothing asserted).
PASS iff: every Then has a ref AND every ref resolves.

INJECTION SAFETY (Pitfall 2 / T-06-01): a Cypher relationship type cannot be parameterized, so
the LLM-supplied `edge_type` is VALIDATED against the kg/schema allow-list {CREATES,UPDATES,
DELETES} BEFORE any query is built; the constant (never the LLM string) is injected. An
unknown kind or a disallowed edge_type is treated as vacuous and runs NO Cypher.

READ-ONLY (T-06-06): every query uses the execute_read shape (managed read txn, parameterized,
LIMIT) mirroring kg/reader._read — this module holds ZERO write-Cypher so the single-write-path
grep gate stays green.
"""

from __future__ import annotations

from neo4j import AsyncDriver

from app.core.neo4j_driver import get_neo4j
from app.services.gates.gherkin_lint import GenerationError
from app.services.kg import schema

# A generous DoS ceiling on every existence read (V5 / T-06-02) — mirrors kg/reader._LIMIT.
_LIMIT = 1

# The edge-type allow-list (kg/schema CONSTANTS) — the ONLY edge types a `kind=edge` ref may
# assert. The constant is injected into Cypher; the LLM-supplied string is NEVER interpolated.
_ALLOWED_EDGE_TYPES = frozenset({schema.CREATES, schema.UPDATES, schema.DELETES})


async def _read_exists(cypher: str, params: dict, *, driver: AsyncDriver | None) -> bool:
    """Managed execute_read returning the boolean `exists` of a count-existence query."""
    drv = driver or get_neo4j()

    async def _tx(tx) -> bool:
        result = await tx.run(cypher, **params)
        rows = [dict(rec) async for rec in result]
        return bool(rows and rows[0].get("exists"))

    async with drv.session() as session:
        return await session.execute_read(_tx)


async def _edge_exists(
    edge_type: str, entity: str, *, driver: AsyncDriver | None
) -> bool:
    """Does a Creates/Updates/Deletes outcome edge exist on the named BusinessEntity?

    edge_type MUST already be validated against the allow-list by the caller; the CONSTANT is
    formatted into the relationship type (it cannot be a Cypher parameter), the entity name is
    a bound parameter. Labels/edge come from kg/schema constants — no page/LLM text interpolated.
    """
    cypher = (
        f"MATCH (:{schema.PAGE}|{schema.FORM}|{schema.WORKFLOW})"
        f"-[r:{edge_type}]->"
        f"(be:{schema.BUSINESS_ENTITY} {{name:$entity}}) "
        "RETURN count(r) > 0 AS exists "
        "LIMIT $limit"
    )
    return await _read_exists(cypher, {"entity": entity, "limit": _LIMIT}, driver=driver)


async def _element_exists(element_key: str, *, driver: AsyncDriver | None) -> bool:
    """Is the element in the Element Repository (a :Page -HAS_ELEMENT-> :Element {key})?"""
    cypher = (
        f"MATCH (:{schema.PAGE})-[:{schema.HAS_ELEMENT}]->"
        f"(e:{schema.ELEMENT} {{key:$element_key}}) "
        "RETURN count(e) > 0 AS exists "
        "LIMIT $limit"
    )
    return await _read_exists(
        cypher, {"element_key": element_key, "limit": _LIMIT}, driver=driver
    )


async def _page_exists(
    fingerprint: str | None, url: str | None, *, driver: AsyncDriver | None
) -> bool:
    """Does a page state exist by fingerprint OR url?"""
    cypher = (
        f"MATCH (p:{schema.PAGE}) WHERE p.fingerprint = $fp OR p.url = $url "
        "RETURN count(p) > 0 AS exists "
        "LIMIT $limit"
    )
    return await _read_exists(
        cypher, {"fp": fingerprint, "url": url, "limit": _LIMIT}, driver=driver
    )


async def resolve_then_refs(
    then_refs: list, *, driver: AsyncDriver | None = None
) -> list[str]:
    """Return the list of VACUOUS Then texts (empty == every Then is graph-backed).

    Pure read-only resolution. For each entry {then_text, kind, ref}:
      - kind=edge: validate ref.edge_type ∈ allow-list BEFORE building Cypher; on a mismatch
        treat as vacuous and run NO query (injection safety). Else resolve the edge existence.
      - kind=element: resolve the element_key existence.
      - kind=page: resolve the page fingerprint/url existence.
      - unknown kind / missing ref values: vacuous, NO query run.
    """
    unresolved: list[str] = []
    for entry in then_refs or []:
        then_text = (entry or {}).get("then_text", "")
        kind = (entry or {}).get("kind")
        ref = (entry or {}).get("ref") or {}

        if kind == "edge":
            edge_type = ref.get("edge_type")
            entity = ref.get("entity")
            # Injection safety: disallowed/unknown edge_type → vacuous, NO Cypher built.
            if edge_type not in _ALLOWED_EDGE_TYPES or not entity:
                unresolved.append(then_text)
                continue
            ok = await _edge_exists(edge_type, entity, driver=driver)
        elif kind == "element":
            element_key = ref.get("element_key")
            if not element_key:
                unresolved.append(then_text)
                continue
            ok = await _element_exists(element_key, driver=driver)
        elif kind == "page":
            fingerprint = ref.get("page_fingerprint")
            url = ref.get("page_url")
            if not fingerprint and not url:
                unresolved.append(then_text)
                continue
            ok = await _page_exists(fingerprint, url, driver=driver)
        else:
            # Unknown kind → vacuous; run NO query (no fabricated resolution).
            unresolved.append(then_text)
            continue

        if not ok:
            unresolved.append(then_text)
    return unresolved


async def assert_non_vacuous(
    then_refs: list, *, driver: AsyncDriver | None = None
) -> None:
    """Raise GenerationError unless every Then has a ref AND every ref resolves.

    A scenario PASSES iff resolve_then_refs(...) == [] AND it has at least one Then with a ref
    (a scenario with zero Thens, or only ref-less Thens, is vacuous by definition). Shared by
    generation and the edit/approve router so both enforce the gate identically (D-04).
    """
    if not then_refs:
        raise GenerationError("no-vacuous gate: scenario has zero Then assertions")
    unresolved = await resolve_then_refs(then_refs, driver=driver)
    if unresolved:
        raise GenerationError(
            "no-vacuous gate: Then steps with no graph-backed outcome: "
            + "; ".join(t for t in unresolved if t) or "no-vacuous gate: vacuous Then(s)"
        )
