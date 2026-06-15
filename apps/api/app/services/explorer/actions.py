"""Constrained action-menu enumeration (D-02) + in-origin frontier candidate derivation.

The LLM never emits a selector — code enumerates the candidate interactable elements and
the LLM picks an INDEX (D-02). This bounds tokens and keeps the budget/loop logic
deterministic. aria_snapshot is the LLM VIEW; the menu + its locators come from real
element handles (Pitfall 4: aria_snapshot has roles/names but not data-testid/href).

H-2: in-origin `a[href]` targets become frontier candidates (key derived from page_key) so
the crawl advances to NEW pages instead of re-perceiving the landing page.

Full locator-chain extraction is Slice 3 (EXPL-09) — the `locator_chain` field is left as a
documented stub here.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlsplit, urlunsplit

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


async def enumerate_actions(page, base_url: str) -> tuple[list[dict], list[dict]]:  # noqa: ANN001
    """Build the constrained menu + the in-origin frontier candidates from the live page.

    Returns (menu, candidates):
      - menu: [{index, role, label, url?, locator_chain}] — the LLM picks an index (D-02).
      - candidates: [{key, url, label}] for in-origin a[href] targets (H-2 frontier feed).
    """
    handles = await page.query_selector_all(_CANDIDATE_SELECTOR)
    menu: list[dict] = []
    candidates: list[dict] = []
    for i, h in enumerate(handles):
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
            # Slice 3 (EXPL-09) replaces this stub with the full prioritized locator chain.
            "locator_chain": None,  # STUB: data-testid->aria-label->role->text->xpath (Slice 3)
        }
        if href:
            absolute = urljoin(page.url, href)
            entry["url"] = absolute
            if _same_origin(absolute, base_url):
                candidates.append(
                    {"key": page_key(absolute), "url": absolute, "label": label}
                )
        menu.append(entry)
    return menu, candidates


def render_menu(menu: list[dict]) -> str:
    """Render the menu as a compact numbered list for the decide prompt (D-02)."""
    lines = []
    for e in menu:
        suffix = f" -> {e['url']}" if e.get("url") else ""
        lines.append(f"[{e['index']}] {e['role']}: {e['label']}{suffix}")
    return "\n".join(lines) if lines else "(no actions available)"
