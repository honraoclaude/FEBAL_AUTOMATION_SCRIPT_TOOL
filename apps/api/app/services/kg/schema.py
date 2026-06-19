"""Canonical knowledge-graph schema: label/edge constants + uniqueness constraints (KG-01/03).

ONE source of truth for the KG label names, edge-type names, and the Neo4j uniqueness
constraints. Mirrors `explorer/risk.py` `DENY_VERBS` (a module-level constant set as a code
source of truth) — the grep gate (KG-05) exempts exactly this file + `kg/writer.py`, so all
write-Cypher tokens (incl. the `CREATE CONSTRAINT` DDL below) live here or in the writer.

Constraint setup is run ONCE at lifespan startup (mirrors `core/checkpointer.init_checkpointer`
running `setup()` once). CRITICAL difference: `core/neo4j_driver.init_neo4j()` opens the driver
LAZILY (no socket at boot) so the api boots even when neo4j is down (graph profile inactive).
`ensure_constraints` therefore CATCHES connection errors and returns — it must NEVER raise at
startup, preserving the graceful-boot-without-neo4j contract (the constraints get created on the
next boot when neo4j is reachable, or before the first real write). Neo4j schema is NOT
Alembic-managed (Alembic is Postgres-only).
"""

from __future__ import annotations

import structlog
from neo4j import AsyncDriver

log = structlog.get_logger()

# --- Canonical node labels (KG-01) -------------------------------------------------------
PAGE = "Page"
BUTTON = "Button"
FORM = "Form"
WORKFLOW = "Workflow"
ELEMENT = "Element"
BUSINESS_ENTITY = "BusinessEntity"

# --- Canonical edge types (KG-01) --------------------------------------------------------
NAVIGATES_TO = "NavigatesTo"
SUBMITS = "Submits"
CREATES = "Creates"
UPDATES = "Updates"
DELETES = "Deletes"
HAS_ELEMENT = "HAS_ELEMENT"
HAS_FORM = "HAS_FORM"
HAS_BUTTON = "HAS_BUTTON"
STEP = "STEP"

# --- Uniqueness constraints (RESEARCH Pattern 1 / Pitfall 1) -----------------------------
# Page MERGEs on the Phase-4 structural fingerprint (the dedup key); the others keep their
# unique key/name. Each constraint also creates the backing index (fast MERGE lookups).
_CONSTRAINTS: tuple[str, ...] = (
    "CREATE CONSTRAINT page_fp IF NOT EXISTS "
    "FOR (p:Page) REQUIRE p.fingerprint IS UNIQUE",
    "CREATE CONSTRAINT element_key IF NOT EXISTS "
    "FOR (e:Element) REQUIRE e.key IS UNIQUE",
    "CREATE CONSTRAINT button_key IF NOT EXISTS "
    "FOR (b:Button) REQUIRE b.key IS UNIQUE",
    "CREATE CONSTRAINT form_key IF NOT EXISTS "
    "FOR (f:Form) REQUIRE f.key IS UNIQUE",
    "CREATE CONSTRAINT business_entity_name IF NOT EXISTS "
    "FOR (be:BusinessEntity) REQUIRE be.name IS UNIQUE",
)

# --- Deterministic verb -> BusinessEntity map (RESEARCH lines 411-415) -------------------
# action-label SUBSTRING (lowercased) -> {name, kind, edge}. Drives the explorer's
# state-change edge writing for the recognizable SauceDemo verbs. Deterministic, NOT LLM.
VERB_ENTITY_MAP: dict[str, dict[str, str]] = {
    "add-to-cart": {"name": "Cart", "kind": "collection", "edge": UPDATES},
    "add to cart": {"name": "Cart", "kind": "collection", "edge": UPDATES},
    "remove": {"name": "Cart", "kind": "collection", "edge": UPDATES},
    "checkout": {"name": "Order", "kind": "transaction", "edge": CREATES},
    "finish": {"name": "Order", "kind": "transaction", "edge": CREATES},
    "inventory": {"name": "Product", "kind": "catalog_item", "edge": UPDATES},
    "product": {"name": "Product", "kind": "catalog_item", "edge": UPDATES},
}


def map_verb_to_entity(label: str) -> dict[str, str] | None:
    """PURE: resolve an action label to a {name, kind, edge} BusinessEntity, or None.

    Substring match (lowercased) against VERB_ENTITY_MAP; first match wins by insertion order.
    Deterministic + table-testable; no LLM, no I/O (RESEARCH BusinessEntity verb->entity map).
    """
    text = (label or "").lower()
    for verb, entity in VERB_ENTITY_MAP.items():
        if verb in text:
            return entity
    return None


async def ensure_constraints(driver: AsyncDriver) -> bool:
    """Create every uniqueness constraint idempotently (IF NOT EXISTS). GRACEFUL when neo4j down.

    Run ONCE at lifespan startup. Catches any connection/driver error and logs-and-returns
    False (NEVER raises) so the api still boots when neo4j is unreachable (graph profile
    inactive). Returns True when the constraints were applied. The constraints get created on
    the next reachable boot otherwise.
    """
    try:
        async with driver.session() as session:
            for ddl in _CONSTRAINTS:
                await session.run(ddl)
        log.info("kg_constraints_ensured", count=len(_CONSTRAINTS))
        return True
    except Exception as exc:  # noqa: BLE001 -- graceful boot: neo4j may be down at startup
        log.info("kg_constraints_skipped_neo4j_unreachable", error=str(exc))
        return False
