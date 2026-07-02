"""Constrained action-menu enumeration (D-02) + in-origin frontier candidate derivation.

The LLM never emits a selector — code enumerates the candidate interactable elements and
the LLM picks an INDEX (D-02). This bounds tokens and keeps the budget/loop logic
deterministic. aria_snapshot is the LLM VIEW; the menu + its locators come from real
element handles (Pitfall 4: aria_snapshot has roles/names but not data-testid/href).

H-2: in-origin `a[href]` targets become frontier candidates (key derived from page_key) so
the crawl advances to NEW pages instead of re-perceiving the landing page.

Each menu entry's `locator_chain` is the full prioritized chain (data-testid→aria-label→role
→text→xpath) extracted per element (EXPL-09, locators.extract_locator_chain).
"""

from __future__ import annotations

import asyncio
from urllib.parse import urljoin, urlsplit, urlunsplit

import structlog

from app.services.explorer.locators import extract_locator_chain

_CANDIDATE_SELECTOR = (
    "a[href], button, input, select, textarea, "
    "[role=button], [role=link], [role=menuitem]"
)


def page_key(url: str) -> str:
    """Stable URL identity: scheme+host+path (drop query/fragment).

    Slice 2 (EXPL-06): this is NO LONGER the state dedup/fingerprint key — the structural
    `fingerprint.fingerprint(...)` computed in the perceive node replaced it as the
    converge/persist dedup key. page_key now serves only the FRONTIER (in-origin a[href]
    candidate identity), where URL identity is the correct notion (the frontier dedups URLs
    to visit, not page structures). Same shape as the Phase-3 tracer _page_key.
    """
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") or "/", "", ""))


def _same_origin(url: str, base_url: str) -> bool:
    """True when url shares scheme+host with base_url (in-origin) — H-2 frontier gate."""
    u, b = urlsplit(url), urlsplit(base_url)
    return (u.scheme, u.netloc) == (b.scheme, b.netloc)


# Per-element enumeration is bounded: element_handle.evaluate() has NO default Playwright
# timeout, so a single element whose DOM state stalls the JS can hang the whole exploration
# forever (observed live on a real target). Each element is capped and skipped on timeout/error
# so enumeration always completes — a menu missing one weird element is fine; a hung run is not.
log = structlog.get_logger()
_ELEMENT_ENUM_TIMEOUT_S = 5.0


async def _describe_element(h, i: int, page, base_url: str) -> tuple[dict, dict | None]:  # noqa: ANN001
    """Build one menu entry (+ optional in-origin candidate) for a single element handle."""
    role = await h.get_attribute("role")
    if not role:
        role = (await h.evaluate("e => e.tagName.toLowerCase()")) or "element"
    label_raw = (await h.inner_text()) or (await h.get_attribute("aria-label")) or ""
    label = label_raw.strip()[:80]
    href = await h.get_attribute("href")
    entry: dict = {
        "index": i,
        "role": role,
        "label": label,
        # EXPL-09: full prioritized locator chain (data-testid→aria-label→role→text→xpath).
        "locator_chain": await extract_locator_chain(h),
    }
    candidate: dict | None = None
    if href:
        absolute = urljoin(page.url, href)
        entry["url"] = absolute
        if _same_origin(absolute, base_url):
            candidate = {"key": page_key(absolute), "url": absolute, "label": label}
    return entry, candidate


async def enumerate_actions(page, base_url: str) -> tuple[list[dict], list[dict]]:  # noqa: ANN001
    """Build the constrained menu + the in-origin frontier candidates from the live page.

    Returns (menu, candidates):
      - menu: [{index, role, label, url?, locator_chain}] — the LLM picks an index (D-02).
      - candidates: [{key, url, label}] for in-origin a[href] targets (H-2 frontier feed).

    Each element's read is bounded by `_ELEMENT_ENUM_TIMEOUT_S`; an element that times out or
    errors is SKIPPED (never blocks the run) — see the module note above.
    """
    handles = await page.query_selector_all(_CANDIDATE_SELECTOR)
    menu: list[dict] = []
    candidates: list[dict] = []
    for i, h in enumerate(handles):
        try:
            entry, candidate = await asyncio.wait_for(
                _describe_element(h, i, page, base_url), timeout=_ELEMENT_ENUM_TIMEOUT_S
            )
        except (TimeoutError, Exception) as exc:  # noqa: BLE001 -- skip un-enumerable elements
            log.info("enumerate_element_skipped", index=i, error=str(exc)[:200])
            continue
        menu.append(entry)
        if candidate is not None:
            candidates.append(candidate)
    return menu, candidates


def render_menu(menu: list[dict]) -> str:
    """Render the menu as a compact numbered list for the decide prompt (D-02)."""
    lines = []
    for e in menu:
        suffix = f" -> {e['url']}" if e.get("url") else ""
        lines.append(f"[{e['index']}] {e['role']}: {e['label']}{suffix}")
    return "\n".join(lines) if lines else "(no actions available)"
