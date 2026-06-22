"""HEAL-01 candidate sub-score proof — DOM / a11y / history + score_candidate (NO browser).

The three PURE similarity sub-scores plus the assembler `score_candidate`, all operating on
fixture dicts (no browser, no spend) — the deterministic core consumed by `confidence()`:

  - dom_sim:    Jaccard of attribute SETS + tag-equality bonus + xpath-ancestry overlap ratio.
  - a11y_sim:   role equality blended with difflib accessible-name ratio (case-folded).
  - history_sim: does the candidate's chain match ANY prior {step, chain} history snapshot;
                 the best snapshot's TIER weight (build_locator_chain priority) maps to [0,1].
  - score_candidate: assembles {dom, visual, a11y, history} (visual via iou) for confidence().

Candidate ORDER + tie-breaking follow `explorer/locators.build_locator_chain` healing-priority
(data-testid -> aria-label -> role -> text -> xpath): a higher-tier match outscores an equal
lower-tier match. candidates.py imports only stdlib (difflib/re) + the pure build_locator_chain.
"""

from __future__ import annotations

import pytest

from app.services.healing.candidates import (
    a11y_sim,
    dom_sim,
    history_sim,
    score_candidate,
)


# --- dom_sim -------------------------------------------------------------------------------

def test_dom_sim_identical_attrs_is_high() -> None:
    attrs = {"tag": "button", "type": "submit", "name": "go", "class": "btn primary"}
    assert dom_sim(attrs, attrs) == pytest.approx(1.0)


def test_dom_sim_disjoint_attrs_is_low() -> None:
    a = {"tag": "button", "name": "go", "class": "btn"}
    b = {"tag": "input", "placeholder": "search", "class": "field"}
    score = dom_sim(a, b)
    assert score < 0.5


def test_dom_sim_same_tag_scores_above_disjoint() -> None:
    same_tag = dom_sim({"tag": "button"}, {"tag": "button"})
    diff_tag = dom_sim({"tag": "button"}, {"tag": "a"})
    assert same_tag > diff_tag


def test_dom_sim_xpath_ancestry_overlap_raises_score() -> None:
    base = {"tag": "button", "xpath": "/html/body/div[1]/form/button[1]"}
    shared = {"tag": "button", "xpath": "/html/body/div[1]/form/button[2]"}
    unrelated = {"tag": "button", "xpath": "/html/body/nav/a[3]"}
    assert dom_sim(base, shared) > dom_sim(base, unrelated)


# --- a11y_sim ------------------------------------------------------------------------------

def test_a11y_sim_same_role_same_name_is_one() -> None:
    cand = {"role": "button", "name": "Add to cart"}
    assert a11y_sim(cand, cand) == pytest.approx(1.0)


def test_a11y_sim_same_role_different_name_is_partial() -> None:
    a = {"role": "button", "name": "Add to cart"}
    b = {"role": "button", "name": "Add item"}
    score = a11y_sim(a, b)
    assert 0.0 < score < 1.0


def test_a11y_sim_different_role_is_low() -> None:
    a = {"role": "button", "name": "Add to cart"}
    b = {"role": "link", "name": "Add to cart"}
    # Different role drags the blend below an identical-role match.
    assert a11y_sim(a, b) < a11y_sim(a, a)


def test_a11y_sim_name_match_is_case_folded() -> None:
    a = {"role": "button", "name": "Add To Cart"}
    b = {"role": "button", "name": "add to cart"}
    assert a11y_sim(a, b) == pytest.approx(1.0)


# --- history_sim ---------------------------------------------------------------------------

def _chain(strategy: str, value: str) -> list[dict]:
    return [{"strategy": strategy, "value": value}]


def test_history_sim_no_history_is_zero() -> None:
    assert history_sim(_chain("data-testid", "add-to-cart"), []) == 0.0
    assert history_sim(_chain("data-testid", "add-to-cart"), None) == 0.0


def test_history_sim_matching_snapshot_is_positive() -> None:
    history = [{"step": 1, "chain": _chain("data-testid", "add-to-cart")}]
    assert history_sim(_chain("data-testid", "add-to-cart"), history) > 0.0


def test_history_sim_higher_tier_match_scores_higher() -> None:
    # A candidate matching on a higher-priority tier (data-testid) scores above a lower tier (text).
    hi_history = [{"step": 1, "chain": _chain("data-testid", "add-to-cart")}]
    lo_history = [{"step": 1, "chain": _chain("text", "Add to cart")}]
    hi = history_sim(_chain("data-testid", "add-to-cart"), hi_history)
    lo = history_sim(_chain("text", "Add to cart"), lo_history)
    assert hi > lo


def test_history_sim_non_matching_chain_is_zero() -> None:
    history = [{"step": 1, "chain": _chain("data-testid", "add-to-cart")}]
    assert history_sim(_chain("data-testid", "checkout"), history) == 0.0


# --- score_candidate -----------------------------------------------------------------------

def test_score_candidate_returns_four_subscores_in_unit_interval() -> None:
    candidate = {
        "tag": "button",
        "role": "button",
        "name": "Add to cart",
        "class": "btn",
        "xpath": "/html/body/div[1]/button[1]",
        "bbox": {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0},
        "chain": _chain("data-testid", "add-to-cart"),
    }
    broken_chain = _chain("data-testid", "add-to-cart")
    broken_attrs = {"tag": "button", "role": "button", "name": "Add to cart", "class": "btn",
                    "xpath": "/html/body/div[1]/button[1]"}
    broken_bbox = {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0}
    history = [{"step": 1, "chain": _chain("data-testid", "add-to-cart")}]

    signals = score_candidate(candidate, broken_chain, broken_attrs, broken_bbox, history)

    assert set(signals.keys()) == {"dom", "visual", "a11y", "history"}
    for key, val in signals.items():
        assert 0.0 <= val <= 1.0, f"{key}={val} out of [0,1]"


def test_score_candidate_perfect_match_blends_to_high_confidence() -> None:
    from app.services.healing.confidence import confidence

    attrs = {"tag": "button", "role": "button", "name": "Add to cart", "class": "btn",
             "xpath": "/html/body/div[1]/button[1]"}
    bbox = {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0}
    chain = _chain("data-testid", "add-to-cart")
    candidate = {**attrs, "bbox": bbox, "chain": chain}
    history = [{"step": 1, "chain": chain}]

    signals = score_candidate(candidate, chain, attrs, bbox, history)
    assert confidence(signals) > 0.85


def test_score_candidate_offscreen_visual_is_zero() -> None:
    candidate = {"tag": "button", "role": "button", "name": "x", "bbox": None, "chain": []}
    signals = score_candidate(candidate, [], {"tag": "button"}, None, [])
    assert signals["visual"] == 0.0


def test_higher_tier_candidate_outscores_equal_lower_tier() -> None:
    # Two candidates equal on everything except the history tier they match: the data-testid
    # match must outscore the text match (build_locator_chain priority).
    from app.services.healing.confidence import confidence

    attrs = {"tag": "button", "role": "button", "name": "Add to cart"}
    bbox = {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0}

    hi_chain = _chain("data-testid", "add-to-cart")
    lo_chain = _chain("text", "Add to cart")
    history = [
        {"step": 1, "chain": hi_chain},
        {"step": 1, "chain": lo_chain},
    ]
    hi_cand = {**attrs, "bbox": bbox, "chain": hi_chain}
    lo_cand = {**attrs, "bbox": bbox, "chain": lo_chain}

    hi = confidence(score_candidate(hi_cand, hi_chain, attrs, bbox, history))
    lo = confidence(score_candidate(lo_cand, lo_chain, attrs, bbox, history))
    assert hi > lo


def test_candidates_module_imports_no_stack() -> None:
    import inspect

    import app.services.healing.candidates as cand_mod

    src = inspect.getsource(cand_mod)
    for forbidden in ("neo4j", "llm_gateway", "SessionLocal", "playwright", "init_chat_model"):
        assert forbidden not in src, f"candidates.py must not reference {forbidden!r} (pure)"
