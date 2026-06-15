"""Snapshot-first perception (D-01) — aria_snapshot YAML + a per-state screenshot.

The LLM's ONLY view of a page is the compact aria_snapshot YAML (roles/names of the
accessibility tree) — never raw HTML, never pixels (D-01). A screenshot is captured per
discovered state as EVIDENCE under workspaces/<run_id>/ but is NOT sent to the LLM (no
vision model this phase).

Token-budgeting: aria_snapshot is already compact YAML; long text nodes are truncated so a
content-heavy page cannot blow the decide-call token budget (the gateway also enforces a
hard per-run cap, D-06).
"""

from __future__ import annotations

from app.core.workspaces import run_dir

# Cap a single page's snapshot so a content-heavy page can't dominate the decide prompt.
_MAX_SNAPSHOT_CHARS = 6000


def _truncate(yaml_text: str, limit: int = _MAX_SNAPSHOT_CHARS) -> str:
    """Truncate the snapshot to a token budget, marking the cut (D-01 token-budgeting)."""
    if len(yaml_text) <= limit:
        return yaml_text
    return yaml_text[:limit] + "\n# ...[snapshot truncated for token budget]..."


async def perceive(page) -> str:  # noqa: ANN001 -- playwright Page
    """Return the compact aria_snapshot YAML for the page body (the LLM's ONLY view, D-01)."""
    snapshot = await page.locator("body").aria_snapshot()
    return _truncate(snapshot)


async def capture_screenshot(page, run_id: str, step: int) -> str:  # noqa: ANN001
    """Save a per-state screenshot under workspaces/<run_id>/ and return its path (evidence).

    NOT sent to the LLM (D-01) — recorded on the Neo4j Page node as a screenshot_path for
    the dashboard/evidence trail. Uses the same workspaces root generate-scripts/execute use.
    """
    d = run_dir(run_id, create=True)
    path = d / f"state-{step}.png"
    await page.screenshot(path=str(path))
    return str(path)
