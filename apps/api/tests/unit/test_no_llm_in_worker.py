"""SC3 NO-LLM import gate (grep gate, default suite — no broker/keys/neo4j needed).

The execution worker is a STATELESS subprocess runner: it consumes a RabbitMQ job and runs
`uv run pytest <spec>` in an isolated child. It MUST NEVER reach the LLM gateway, LangChain,
LangGraph, or the explorer agent — exploration/generation is a different plane (SC3). This
test walks every `.py` under `app/services/worker/` PLUS `app/worker_main.py` and fails if any
forbidden import token appears OUTSIDE a comment/docstring line.

Grep gate hygiene (mirrors test_single_write_path.py, the Phase-5 KG-05 gate): full-line
comments (first non-space char is `#`) are stripped before scanning, so a docstring/comment
mentioning "init_chat_model" does NOT trip the gate — only a real import statement does. The
forbidden tokens are import-shaped (`import ...` / `from ... import`) so prose never matches.

This gate is created in Task 2 (before the worker package exists) and re-run after Task 3
once consumer.py/job.py/progress.py/worker_main.py land — the gate going green over the REAL
worker source IS the SC3 enforcement working.
"""

from __future__ import annotations

import re
from pathlib import Path

# apps/api/app/ — the backend application package.
_APP_ROOT = Path(__file__).resolve().parents[2] / "app"
_WORKER_PKG = _APP_ROOT / "services" / "worker"
_WORKER_MAIN = _APP_ROOT / "worker_main.py"

# Forbidden import tokens — the LLM/agent plane the worker must never touch (SC3).
# Each is import-shaped so English prose in a docstring cannot match; comment lines are
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


def _worker_sources() -> list[Path]:
    """Every worker-plane .py file that currently exists (worker pkg + worker_main)."""
    sources: list[Path] = []
    if _WORKER_PKG.exists():
        sources.extend(p for p in _WORKER_PKG.rglob("*.py") if "__pycache__" not in p.parts)
    if _WORKER_MAIN.exists():
        sources.append(_WORKER_MAIN)
    return sources


def test_worker_plane_imports_no_llm_symbol() -> None:
    offenders: list[str] = []
    for py in _worker_sources():
        source = _strip_comment_lines(py.read_text(encoding="utf-8"))
        for token in _FORBIDDEN:
            for m in token.finditer(source):
                line_no = source.count("\n", 0, m.start()) + 1
                offenders.append(
                    f"{py.relative_to(_APP_ROOT.parent)}:{line_no} -> {m.group(0)!r}"
                )

    assert not offenders, (
        "Forbidden LLM/agent-plane import found in the execution worker (SC3 breach — the "
        "worker must never reach the gateway/LangChain/LangGraph/explorer):\n"
        + "\n".join(offenders)
    )
