"""Pure deterministic 3-way classifier (DEF-01) — taxonomy rules + 0-100 confidence, keyless.

The classifier mirrors kg/risk.py / healing/confidence.py: a @dataclass(frozen=True) of starting-
point weights + a pure classify(evidence) -> {classification, confidence, cited}. NO LLM, NO I/O,
NO DB — the decision is reproducible, auditable, and free (D-01). The class precedence is
infrastructure-first, product_defect-last/default (RESEARCH Pattern 1 taxonomy):

  infrastructure : browser-crash / Target closed / net::ERR_ / ERR_CONNECTION_REFUSED / DNS /
                   timeout-never-loaded / infra_health == 'down'
  automation     : locator-not-found / selector / test-data AFTER an un-healed/quarantined heal
                   (heal_outcome in {fail_as_defect, quarantine}) with the page otherwise loaded
  product_defect : assertion failure on a LOADED page / functional / validation / API 4xx-5xx /
                   the SEED_BUG signature

These table-driven cases run on FIXTURE evidence dicts (keyless) and assert the expected class +
a confidence band + that the cited signals are non-empty.

Run: cd apps/api && uv run python -m pytest tests/unit/test_classifier.py -q
"""

from __future__ import annotations

import pytest

from app.services.defects.classifier import (
    AUTOMATION,
    DEFAULT_WEIGHTS,
    INFRA,
    PRODUCT,
    ClassifierWeights,
    classify,
)

# (label, evidence, expected_class, min_confidence) — fixture rows spanning the taxonomy.
_CASES = [
    (
        "connection-refused -> infra",
        {"error_text": "page.goto: net::ERR_CONNECTION_REFUSED at http://target:80", "page_loaded": False},
        INFRA,
        60,
    ),
    (
        "browser-crash -> infra",
        {"error_text": "Target closed: the browser has been closed", "page_loaded": False},
        INFRA,
        60,
    ),
    (
        "dns -> infra",
        {"error_text": "net::ERR_NAME_NOT_RESOLVED resolving target", "page_loaded": False},
        INFRA,
        60,
    ),
    (
        "timeout never loaded -> infra",
        {"error_text": "Timeout 30000ms exceeded waiting for navigation", "page_loaded": False},
        INFRA,
        60,
    ),
    (
        "infra_health down -> infra",
        {"error_text": "could not reach service", "page_loaded": False, "infra_health": "down"},
        INFRA,
        60,
    ),
    (
        "un-healed locator drift -> automation",
        {
            "error_text": "locator.click: element not found: add-to-cart-backpack",
            "page_loaded": True,
            "heal_outcome": "fail_as_defect",
        },
        AUTOMATION,
        60,
    ),
    (
        "quarantined selector -> automation",
        {
            "error_text": "selector resolved 0 elements: .nav-menu",
            "page_loaded": True,
            "heal_outcome": "quarantine",
        },
        AUTOMATION,
        60,
    ),
    (
        "loaded-page assertion -> product_defect",
        {
            "error_text": "AssertionError: expect(locator).to_be_visible() failed for .inventory_list",
            "page_loaded": True,
        },
        PRODUCT,
        60,
    ),
    (
        "API 5xx on loaded page -> product_defect",
        {"error_text": "Expected 200 but received 500 Internal Server Error", "page_loaded": True},
        PRODUCT,
        60,
    ),
]


@pytest.mark.parametrize("label,evidence,expected,min_conf", _CASES, ids=[c[0] for c in _CASES])
def test_classify_taxonomy(label, evidence, expected, min_conf) -> None:
    out = classify(evidence)
    assert out["classification"] == expected, f"{label}: got {out['classification']} :: {out}"
    assert 0 <= out["confidence"] <= 100
    assert out["confidence"] >= min_conf, f"{label}: confidence {out['confidence']} < {min_conf}"
    assert out["cited"], f"{label}: expected non-empty cited signals"


def test_classify_returns_clamped_0_100_for_empty_evidence() -> None:
    out = classify({})
    assert out["classification"] in (INFRA, AUTOMATION, PRODUCT)
    assert 0 <= out["confidence"] <= 100


def test_default_weights_is_frozen_dataclass() -> None:
    assert isinstance(DEFAULT_WEIGHTS, ClassifierWeights)
    with pytest.raises(Exception):
        DEFAULT_WEIGHTS.strong_class_signal = 99  # frozen -> cannot mutate under callers


def test_weights_are_swappable_per_call() -> None:
    ev = {"error_text": "net::ERR_CONNECTION_REFUSED", "page_loaded": False}
    weak = ClassifierWeights(strong_class_signal=10, corroborating_signal=0, weak_or_conflicting=0)
    out = classify(ev, weak)
    assert out["classification"] == INFRA  # class rule is independent of the weights
    assert out["confidence"] == 10  # confidence honors the swapped weight
