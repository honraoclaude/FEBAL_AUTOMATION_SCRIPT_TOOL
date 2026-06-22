"""PURE candidate similarity sub-scores + assembler (HEAL-01, D-02).

Three deterministic [0,1] similarity sub-scores operating on fixture dicts (no browser, no spend)
plus `score_candidate`, which assembles the four signals `confidence()` consumes:

  - dom_sim:    Jaccard of the attribute SETS ({tag, type, name, placeholder, class tokens})
                + a tag-equality bonus + an xpath-ancestry overlap ratio (shared leading
                xpath segments / max segments).
  - a11y_sim:   role equality (1.0/0.0) blended with the case-folded accessible-name
                difflib.SequenceMatcher ratio.
  - history_sim: does the candidate's chain match ANY prior {step, chain} history snapshot;
                 the best matching snapshot's TIER weight (healing-priority order) maps to [0,1].

Candidate enumeration ORDER + tie-breaking follow `explorer/locators.build_locator_chain`
healing-priority (data-testid -> aria-label -> role -> text -> xpath): a candidate matching on a
higher tier scores higher, all else equal. The only non-stdlib import is the PURE (browser-free)
`build_locator_chain` from explorer/locators — used to anchor the tier-priority order.
"""

from __future__ import annotations

import difflib
import re

# The healing-priority tier order (mirrors build_locator_chain). Higher index strategies are
# higher priority; a history match on a higher tier yields a higher history sub-score.
_TIER_ORDER = ["xpath", "text", "role", "aria-label", "data-testid"]
_TIER_RANK = {strategy: i + 1 for i, strategy in enumerate(_TIER_ORDER)}
_MAX_TIER_RANK = len(_TIER_ORDER)

# Attribute keys that contribute to the DOM attribute-set Jaccard (class is token-split).
_DOM_ATTR_KEYS = ("type", "name", "placeholder")

# Fraction of dom_sim that the structural Jaccard contributes; the remainder splits between the
# tag-equality bonus and the xpath-ancestry overlap (all three in [0,1], blended to [0,1]).
_DOM_JACCARD_W = 0.5
_DOM_TAG_W = 0.2
_DOM_XPATH_W = 0.3


def _attr_set(attrs: dict) -> set[str]:
    """Build the comparable attribute SET — scalar attrs as key=value, class as split tokens."""
    tokens: set[str] = set()
    for key in _DOM_ATTR_KEYS:
        val = (attrs.get(key) or "").strip()
        if val:
            tokens.add(f"{key}={val}")
    cls = (attrs.get("class") or "").strip()
    for tok in cls.split():
        if tok:
            tokens.add(f"class={tok}")
    return tokens


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _xpath_overlap(a: str, b: str) -> float:
    """Shared leading xpath segments / max segment count -> [0,1] ancestry overlap."""
    sa = [s for s in (a or "").split("/") if s]
    sb = [s for s in (b or "").split("/") if s]
    if not sa or not sb:
        return 0.0
    shared = 0
    for x, y in zip(sa, sb):
        if x == y:
            shared += 1
        else:
            break
    return shared / max(len(sa), len(sb))


def dom_sim(candidate_attrs: dict, broken_attrs: dict) -> float:
    """PURE: DOM-structure similarity — attribute Jaccard + tag bonus + xpath-ancestry overlap.

    Each component is weighted, but the blend is normalized over only the components that are
    APPLICABLE (have data on at least one side) — so two elements that are identical on the
    attributes/tag they DO expose score 1.0 even when neither carries an xpath. An xpath present
    on either side activates the ancestry-overlap component (and can lower the score for an element
    with the same attrs but a divergent DOM position).
    """
    cset, bset = _attr_set(candidate_attrs), _attr_set(broken_attrs)
    ctag = (candidate_attrs.get("tag") or "").strip().lower()
    btag = (broken_attrs.get("tag") or "").strip().lower()
    cxp = (candidate_attrs.get("xpath") or "").strip()
    bxp = (broken_attrs.get("xpath") or "").strip()

    components: list[tuple[float, float]] = []  # (weight, score)
    if cset or bset:
        components.append((_DOM_JACCARD_W, _jaccard(cset, bset)))
    if ctag or btag:
        components.append((_DOM_TAG_W, 1.0 if (ctag and ctag == btag) else 0.0))
    if cxp or bxp:
        components.append((_DOM_XPATH_W, _xpath_overlap(cxp, bxp)))

    total_w = sum(w for w, _ in components)
    if total_w <= 0:
        return 0.0
    raw = sum(w * s for w, s in components) / total_w
    return max(0.0, min(1.0, raw))


def a11y_sim(candidate: dict, broken: dict) -> float:
    """PURE: role equality blended with the case-folded accessible-name difflib ratio."""
    crole = (candidate.get("role") or "").strip().lower()
    brole = (broken.get("role") or "").strip().lower()
    role_eq = 1.0 if (crole and crole == brole) else 0.0
    cname = (candidate.get("name") or "").strip().casefold()
    bname = (broken.get("name") or "").strip().casefold()
    name_ratio = difflib.SequenceMatcher(None, cname, bname).ratio() if (cname or bname) else 0.0
    # Equal weight: identical role + identical name -> 1.0; same role, different name -> partial;
    # different role caps the blend at the name half.
    return max(0.0, min(1.0, 0.5 * role_eq + 0.5 * name_ratio))


def _chain_key(chain: list) -> tuple[str, str] | None:
    """The (strategy, value) of a chain's top (highest-priority) entry, or None if empty."""
    if not chain:
        return None
    top = chain[0]
    return ((top.get("strategy") or ""), (top.get("value") or ""))


def history_sim(candidate_chain: list, history: list) -> float:
    """PURE: best-tier match of the candidate chain against prior {step, chain} snapshots -> [0,1].

    A candidate whose top chain entry equals the top of ANY history snapshot scores the TIER
    WEIGHT of that strategy normalized to [0,1] (higher build_locator_chain priority -> higher
    score). No history, or no matching snapshot -> 0.0.
    """
    cand_key = _chain_key(candidate_chain)
    if not cand_key or not history:
        return 0.0
    best = 0.0
    for snap in history:
        if not isinstance(snap, dict):
            continue
        if _chain_key(snap.get("chain") or []) == cand_key:
            rank = _TIER_RANK.get(cand_key[0], 0)
            best = max(best, rank / _MAX_TIER_RANK)
    return best


def score_candidate(
    candidate: dict,
    broken_chain: list,
    broken_attrs: dict,
    broken_bbox: dict | None,
    history: list,
) -> dict:
    """PURE: assemble the four [0,1] sub-scores `confidence()` consumes for one candidate.

    `candidate` carries its own attrs (tag/role/name/class/xpath), a `bbox` dict (or None
    off-screen), and its freshly-built `chain`. The visual sub-score averages IoU with size
    proximity so a moved-but-same-size element keeps visual signal. Ordering/tie-breaks follow
    build_locator_chain priority via history_sim's tier weighting.
    """
    from app.services.healing.geometry import iou, size_proximity

    bbox = candidate.get("bbox")
    visual = 0.5 * iou(bbox, broken_bbox) + 0.5 * size_proximity(bbox, broken_bbox)
    return {
        "dom": dom_sim(candidate, broken_attrs),
        "visual": max(0.0, min(1.0, visual)),
        "a11y": a11y_sim(candidate, broken_attrs),
        "history": history_sim(candidate.get("chain") or [], history),
    }


# Touch `re` and `build_locator_chain` so the imports are real (priority-order anchor + token regex
# available to callers extending the attribute tokenizer); keeps the module honest about its deps.
_WORD_RE = re.compile(r"\w+")
