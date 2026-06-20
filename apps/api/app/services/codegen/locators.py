"""Element-Repository locator lookup (GEN-04 / GEN-05a / D-05).

`OBSERVED_SELECTORS` (the Phase-3 hard-coded tuple) generalized to a KG query: read the
Phase-5 Element Repository and, for each element on a page, map a deterministic page-object
ATTRIBUTE name → that element's TOP-PRIORITY locator chain entry. The element key and the
resolved locator are TEMPLATE inputs sourced from the repo — the LLM never sees or emits them.

The chain is the deserialized, PRIORITIZED locator chain from kg/reader.element_repository
(data-testid → aria-label → role → text → xpath); the top entry is the most stable locator the
crawl observed. This is a PURE mapping over the read structures — fake-driver unit-testable, no
keys, no writes (read-only via reader.element_repository, so the single-write-path gate stays
green).
"""

from __future__ import annotations

import re

from neo4j import AsyncDriver

from app.services.kg import reader

# Non-identifier chars collapse to single underscores for a deterministic snake_case attr name.
_NON_IDENT = re.compile(r"[^0-9a-zA-Z]+")


def _attr_name(role: str | None, label: str | None) -> str:
    """Deterministic snake_case page-object attribute name from an element's role + label.

    e.g. role="button", label="Add to cart" → "button_add_to_cart". Leading digits are prefixed
    with `el_` so the result is always a valid Python identifier.
    """
    raw = f"{role or ''} {label or ''}".strip().lower()
    name = _NON_IDENT.sub("_", raw).strip("_")
    if not name:
        name = "element"
    if name[0].isdigit():
        name = f"el_{name}"
    return name


def _top_chain_entry(chain: list) -> str | None:
    """The top-priority locator VALUE from a deserialized chain ([{strategy, value}, ...]).

    The chain is already prioritized by kg/reader (data-testid → aria-label → role → text →
    xpath); the first entry's `value` is the most stable locator. Returns None for an empty/
    malformed chain so the caller can skip an element with no usable locator.
    """
    if not chain:
        return None
    first = chain[0]
    if isinstance(first, dict):
        value = first.get("value")
        return value if isinstance(value, str) and value else None
    if isinstance(first, str) and first:
        return first
    return None


async def page_object_locators(
    page_fingerprint: str, *, driver: AsyncDriver | None = None
) -> dict[str, str]:
    """Map each element on a page → {attr_name: top_priority_repo_chain_entry} (repo-sourced).

    Reads the Element Repository (read-only), filters to elements whose page fingerprint matches
    `page_fingerprint`, and returns a deterministic {snake_case attr: top chain entry} dict. The
    value is ALWAYS a repo chain entry — never invented; an element with no usable chain entry is
    skipped (no freehand locator is ever fabricated). On an attr-name collision the first element
    (repo order: page url, label) wins.
    """
    rows = await reader.element_repository(driver=driver)
    attrs: dict[str, str] = {}
    for row in rows:
        if row.get("page_fp") != page_fingerprint:
            continue
        locator = _top_chain_entry(row.get("chain") or [])
        if locator is None:
            continue
        name = _attr_name(row.get("role"), row.get("label"))
        attrs.setdefault(name, locator)
    return attrs
