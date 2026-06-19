"""KG-05 single-write-path enforcement (grep gate, default suite — no neo4j needed).

The knowledge graph has exactly ONE Neo4j write path: app/services/kg/writer.py
(and the constraint DDL in app/services/kg/schema.py). This test walks every .py file
under apps/api/app/ and fails if any write-Cypher token (MERGE, CREATE (, SET , DETACH
DELETE, REMOVE ) appears OUTSIDE those two exempt files.

Grep gate hygiene: comment lines (a line whose first non-space char is `#`) are stripped
before scanning so a docstring/comment mentioning "MERGE" does not trip the gate. The token
set mirrors RESEARCH Anti-pattern / Pitfall 6 and the plan's KG-05 enforcement.

This test goes RED until the explorer's inline persist Cypher is lifted into kg/writer.py
(Task 2) — that RED state IS the enforcement working.
"""

from __future__ import annotations

import re
from pathlib import Path

# apps/api/app/ — the backend application package whose ONLY write path is kg/writer.py.
_APP_ROOT = Path(__file__).resolve().parents[2] / "app"

# Exactly the two files allowed to hold write-Cypher (KG-05).
_EXEMPT = {
    _APP_ROOT / "services" / "kg" / "writer.py",
    _APP_ROOT / "services" / "kg" / "schema.py",
}

# Write-Cypher tokens, scoped to CYPHER SYNTAX so English prose ("Neo4j MERGE key",
# "SET the kill-switch flag") in docstrings/comments does NOT trip the gate. The point of
# the gate is real write statements — those always carry Cypher punctuation:
#   - MERGE always opens a pattern: `MERGE (`
#   - CREATE node/edge always opens a pattern: `CREATE (`  (CREATE CONSTRAINT lives in the
#     exempt schema.py, and would not match `CREATE (` anyway)
#   - SET in Cypher always assigns a property: `SET x.prop` or `SET x=` (prose "SET the" fails)
#   - DETACH DELETE / REMOVE x. are unambiguous Cypher
_WRITE_TOKENS = [
    re.compile(r"\bMERGE\s*\("),
    re.compile(r"\bCREATE\s*\("),
    re.compile(r"\bSET\s+\w+\s*[.=]"),
    re.compile(r"\bDETACH\s+DELETE\b"),
    re.compile(r"\bREMOVE\s+\w+\."),
]


def _strip_comment_lines(text: str) -> str:
    """Drop full-line comments (first non-space char is `#`) before token scanning."""
    kept = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        kept.append(line)
    return "\n".join(kept)


def test_no_write_cypher_outside_kg_writer_and_schema() -> None:
    offenders: list[str] = []
    for py in _APP_ROOT.rglob("*.py"):
        if py in _EXEMPT:
            continue
        source = _strip_comment_lines(py.read_text(encoding="utf-8"))
        for token in _WRITE_TOKENS:
            for m in token.finditer(source):
                # Report file + the matched token snippet for a debuggable failure.
                line_no = source.count("\n", 0, m.start()) + 1
                offenders.append(f"{py.relative_to(_APP_ROOT.parent)}:{line_no} -> {m.group(0)!r}")

    assert not offenders, (
        "Write-Cypher found outside kg/writer.py + kg/schema.py (KG-05 single write path "
        "violated):\n" + "\n".join(offenders)
    )


def test_exempt_files_exist() -> None:
    """The two exempt files must exist — otherwise the gate is exempting nothing."""
    for path in _EXEMPT:
        assert path.exists(), f"expected single-write-path file missing: {path}"
