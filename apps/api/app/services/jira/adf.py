"""Pure ADF v3 description builder (JIRA-01) — no I/O, no keys, unit-testable.

`build_adf(...)` returns a valid Atlassian Document Format (ADF) v3 description DOC DICT
(`{"type":"doc","version":1,"content":[...]}`). On `Jira(cloud=True, api_version="3")`
the description MUST be this doc dict, NOT a string — a string is rejected by Cloud v3
(Pitfall 2/6 / T-09-10). Keeping the builder PURE (the fingerprint.py discipline: no
gateway, no DB, no network) is what makes the ADF shape unit-assertable BEFORE the
Manual-Only live filing step.

Body layout: a prose paragraph, then a "Steps to Reproduce" heading + an orderedList of
the steps, then Expected / Actual / Severity / Priority paragraphs.
"""

from __future__ import annotations


def _para(text: str) -> dict:
    """An ADF paragraph node wrapping a single text run."""
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _heading(text: str, level: int = 3) -> dict:
    """An ADF heading node at `level`."""
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def _ordered_list(steps: list[str]) -> dict:
    """An ADF orderedList with one listItem (a paragraph) per step (empty -> empty list)."""
    return {
        "type": "orderedList",
        "content": [
            {"type": "listItem", "content": [_para(s)]} for s in steps
        ],
    }


def build_adf(
    *,
    prose: str,
    steps: list[str],
    expected: str,
    actual: str,
    severity: str,
    priority: str,
) -> dict:
    """Build the ADF v3 description doc dict for a defect (JIRA-01).

    Returns a DICT (never a string — Cloud v3 requirement). The prose paragraph leads;
    then a "Steps to Reproduce" heading + orderedList; then Expected/Actual/Severity/
    Priority paragraphs. Pure: no I/O, deterministic for the same inputs.
    """
    content = [
        _para(prose),
        _heading("Steps to Reproduce"),
        _ordered_list(steps),
        _para(f"Expected: {expected}"),
        _para(f"Actual: {actual}"),
        _para(f"Severity: {severity}"),
        _para(f"Priority: {priority}"),
    ]
    return {"type": "doc", "version": 1, "content": content}
