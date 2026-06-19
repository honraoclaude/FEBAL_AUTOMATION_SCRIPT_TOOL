"""Knowledge-graph service package (Phase 5) — the SINGLE Neo4j write path (KG-05).

`writer` owns ALL write-Cypher (idempotent fingerprint-MERGE + freshness + read-back guard);
`schema` owns the label/edge constants + uniqueness constraints + the deterministic
verb->BusinessEntity map. The explorer's persist node delegates here and holds zero Cypher.

Re-exports mirror `explorer/__init__.py` so callers can
`from app.services.kg import writer, schema, ensure_constraints`.
"""

from app.services.kg import schema, writer
from app.services.kg.schema import ensure_constraints

__all__ = ["writer", "schema", "ensure_constraints"]
