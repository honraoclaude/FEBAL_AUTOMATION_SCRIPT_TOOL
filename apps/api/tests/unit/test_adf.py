"""Pure ADF v3 description-builder contract (JIRA-01) — no I/O, no keys, no neo4j.

build_adf(...) returns a valid ADF v3 description DOC DICT (not a string — Cloud v3
rejects a string description, Pitfall 2/6 / T-09-10). These tests pin the doc shape so a
regression that emits a string or drops a section fails here, BEFORE the Manual-Only live
filing step:

  - the result is a dict with type "doc" + version 1 + a content list (NEVER a string);
  - the prose paragraph leads the body;
  - a "Steps to Reproduce" heading is followed by an orderedList with one listItem/step;
  - Expected / Actual / Severity / Priority each render as their own paragraph;
  - empty steps still produce a valid (empty) orderedList — never a crash.

Run: cd apps/api && uv run python -m pytest tests/unit/test_adf.py -q
"""

from __future__ import annotations

from app.services.jira.adf import build_adf

DOC = build_adf(
    prose="Login submit returns 500 instead of redirecting to the dashboard.",
    steps=["Open /login", "Enter valid creds", "Click Submit"],
    expected="Redirect to /dashboard",
    actual="HTTP 500 error page",
    severity="High",
    priority="High",
)


def _texts(node: dict) -> list[str]:
    """Flatten all text strings under a content node (depth-first)."""
    out: list[str] = []
    if node.get("type") == "text":
        out.append(node.get("text", ""))
    for child in node.get("content", []) or []:
        out.extend(_texts(child))
    return out


def test_result_is_an_adf_doc_dict_not_a_string() -> None:
    assert isinstance(DOC, dict)
    assert DOC["type"] == "doc"
    assert DOC["version"] == 1
    assert isinstance(DOC["content"], list)


def test_prose_paragraph_leads_the_body() -> None:
    first = DOC["content"][0]
    assert first["type"] == "paragraph"
    assert "Login submit returns 500" in " ".join(_texts(first))


def test_steps_render_as_a_heading_then_ordered_list() -> None:
    headings = [n for n in DOC["content"] if n["type"] == "heading"]
    assert any("Steps to Reproduce" in " ".join(_texts(h)) for h in headings)

    lists = [n for n in DOC["content"] if n["type"] == "orderedList"]
    assert len(lists) == 1
    items = lists[0]["content"]
    assert len(items) == 3
    assert all(i["type"] == "listItem" for i in items)
    # Each step text survives into its listItem.
    assert "Open /login" in " ".join(_texts(items[0]))
    assert "Click Submit" in " ".join(_texts(items[2]))


def test_expected_actual_severity_priority_each_render() -> None:
    body = " ".join(_texts(DOC))
    assert "Expected: Redirect to /dashboard" in body
    assert "Actual: HTTP 500 error page" in body
    assert "Severity: High" in body
    assert "Priority: High" in body


def test_empty_steps_still_valid_doc() -> None:
    doc = build_adf(
        prose="p", steps=[], expected="e", actual="a", severity="Low", priority="Low"
    )
    assert doc["type"] == "doc" and doc["version"] == 1
    lists = [n for n in doc["content"] if n["type"] == "orderedList"]
    assert len(lists) == 1
    assert lists[0]["content"] == []
