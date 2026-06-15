"""Prioritized locator-chain extraction + history (EXPL-09, RESEARCH:297-314).

Every discovered interactable element carries the FULL ordered locator chain (not just the
winner) in healing-priority order:
    data-testid (BOTH data-testid AND data-test — SauceDemo uses data-test) →
    aria-label → role+accessible-name → visible text → generated xpath (always appended).
plus a locator_history list so Phase 8 healing can fall back when the UI shifts.

The PURE logic (priority ordering + history merge) is split from the async handle reads so it
is unit-testable on plain fixture dicts — no browser, no spend. extract_locator_chain does the
live attribute reads then delegates to build_locator_chain for the ordering.

Persistence is a minimal-but-real Neo4j seam ((:Page)-[:HAS_ELEMENT]->(:Element)) — Phase 5
owns the canonical Element Repository (normalization, dedup, freshness).
"""

from __future__ import annotations

# JS that returns a stable absolute xpath for an element (the always-present fallback tier).
_XPATH_JS = """
el => {
  function segment(node) {
    if (node.id) return `//*[@id=\"${node.id}\"]`;
    let ix = 1, sib = node.previousElementSibling;
    while (sib) { if (sib.tagName === node.tagName) ix++; sib = sib.previousElementSibling; }
    return node.tagName.toLowerCase() + '[' + ix + ']';
  }
  const parts = [];
  let node = el;
  while (node && node.nodeType === 1 && node.tagName.toLowerCase() !== 'html') {
    const seg = segment(node);
    if (seg.startsWith('//*[@id')) { parts.unshift(seg); return parts.join('/'); }
    parts.unshift(seg);
    node = node.parentElement;
  }
  return '/' + parts.join('/');
}
"""


def build_locator_chain(attrs: dict) -> list[dict]:
    """PURE: build the ordered locator chain from a plain attribute dict (unit-testable).

    `attrs` keys (any may be absent/empty): data-testid, data-test, aria-label, role, text,
    xpath. Tiers are emitted in healing-priority order; only present tiers appear, EXCEPT
    xpath which is always appended last as the guaranteed fallback (when an xpath is known).

      1. data-testid — checks BOTH `data-testid` and `data-test` (SauceDemo, RESEARCH:314).
      2. aria-label
      3. role (+ accessible name when present)
      4. visible text
      5. xpath (always last)
    """
    chain: list[dict] = []

    tid = (attrs.get("data-testid") or attrs.get("data-test") or "").strip()
    if tid:
        chain.append({"strategy": "data-testid", "value": tid})

    al = (attrs.get("aria-label") or "").strip()
    if al:
        chain.append({"strategy": "aria-label", "value": al})

    role = (attrs.get("role") or "").strip()
    name = (attrs.get("text") or "").strip()[:80]
    if role:
        entry: dict = {"strategy": "role", "value": role}
        if name:
            entry["name"] = name
        chain.append(entry)

    if name:
        chain.append({"strategy": "text", "value": name})

    xpath = (attrs.get("xpath") or "").strip()
    if xpath:
        chain.append({"strategy": "xpath", "value": xpath})

    return chain


def merge_locator_history(existing: list, new_chain: list, *, step: int) -> list:
    """PURE: append a step-stamped snapshot of the current chain to history (never drop prior).

    History is an append-only list of {step, chain} snapshots so Phase 8 healing can fall back
    to a locator that worked on an earlier observation when the live UI shifts. A re-observed
    element APPENDS rather than overwriting.
    """
    history = list(existing or [])
    history.append({"step": step, "chain": list(new_chain)})
    return history


async def extract_locator_chain(handle) -> list[dict]:  # noqa: ANN001 -- playwright ElementHandle
    """Read the element's attributes from the live handle, then build the ordered chain.

    The async reads are kept thin; the ordering lives in the pure build_locator_chain so the
    priority contract is table-tested without a browser.
    """
    attrs = {
        "data-testid": await handle.get_attribute("data-testid"),
        "data-test": await handle.get_attribute("data-test"),
        "aria-label": await handle.get_attribute("aria-label"),
        "role": await handle.get_attribute("role"),
        "text": (await handle.inner_text()) or "",
    }
    try:
        attrs["xpath"] = await handle.evaluate(_XPATH_JS)
    except Exception:  # noqa: BLE001 -- a stale handle must not crash enumeration
        attrs["xpath"] = ""
    return build_locator_chain(attrs)
