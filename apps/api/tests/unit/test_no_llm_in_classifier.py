"""NO-LLM import gate over the defects package (D-01, grep gate — no keys/neo4j/broker needed).

The class/confidence DECISION is DETERMINISTIC and keyless (D-01): the LLM (gateway) is used ONLY
to enrich the Jira description prose in a LATER plan — NEVER for the class/confidence decision.
This gate (a clone of test_no_llm_in_worker.py) walks every `.py` under `app/services/defects/`
and fails if any forbidden LLM/agent-plane import token appears OUTSIDE a comment line — the
classifier/fingerprint/infra_health/evidence modules must reach NOTHING on the LLM/gateway/
LangChain/LangGraph/explorer plane.

Grep gate hygiene (mirrors test_no_llm_in_worker.py): full-line comments (first non-space char is
`#`) are stripped before scanning, so a docstring/comment mentioning a forbidden symbol does NOT
trip the gate — only a real import statement does. The tokens are import-shaped so prose never
matches.

Run: cd apps/api && uv run python -m pytest tests/unit/test_no_llm_in_classifier.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

# apps/api/app/ — the backend application package.
_APP_ROOT = Path(__file__).resolve().parents[2] / "app"
_DEFECTS_PKG = _APP_ROOT / "services" / "defects"

# Forbidden import tokens — the LLM/agent plane the deterministic classifier must never touch
# (D-01). Each is import-shaped so English prose in a docstring cannot match; comment lines are
# stripped first as a second line of defence.
_FORBIDDEN = [
    re.compile(r"\binit_chat_model\b"),
    re.compile(r"\bllm_gateway\b"),
    re.compile(r"\bimport\s+langchain\b"),
    re.compile(r"\bfrom\s+langchain\b"),
    re.compile(r"\bimport\s+langgraph\b"),
    re.compile(r"\bfrom\s+langgraph\b"),
    re.compile(r"\bfrom\s+app\.services\.explorer\b"),
    re.compile(r"\bimport\s+app\.services\.explorer\b"),
]


def _strip_comment_lines(text: str) -> str:
    """Drop full-line comments (first non-space char is `#`) before token scanning."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def _defects_sources() -> list[Path]:
    """Every defects-package .py file that currently exists."""
    if not _DEFECTS_PKG.exists():
        return []
    return [p for p in _DEFECTS_PKG.rglob("*.py") if "__pycache__" not in p.parts]


def test_defects_package_imports_no_llm_symbol() -> None:
    sources = _defects_sources()
    assert sources, "no defects-package sources found to scan (the gate must scan real files)"

    offenders: list[str] = []
    for py in sources:
        source = _strip_comment_lines(py.read_text(encoding="utf-8"))
        for token in _FORBIDDEN:
            for m in token.finditer(source):
                line_no = source.count("\n", 0, m.start()) + 1
                offenders.append(
                    f"{py.relative_to(_APP_ROOT.parent)}:{line_no} -> {m.group(0)!r}"
                )

    assert not offenders, (
        "Forbidden LLM/agent-plane import found in the defects package (D-01 breach — the "
        "class/confidence decision is deterministic; the LLM is description-prose only):\n"
        + "\n".join(offenders)
    )
