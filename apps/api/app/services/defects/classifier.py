"""PURE deterministic 3-way failure classifier + 0-100 confidence (DEF-01/02) — NEVER LLM JUDGMENT.

The deterministic, keyless sibling of kg/risk.py + healing/confidence.py: a @dataclass(frozen=True)
of tunable STARTING-POINT weights + a pure classify(evidence) -> {classification, confidence,
cited}. D-01 REJECTS an LLM-judged class: a number users act on (and file Jira tickets from) must
be reproducible, auditable, free, and QUAL-03-measurable WITHOUT provider keys. The LLM is used
ONLY to enrich the Jira description PROSE in a later plan — never for this decision.

Class precedence (RESEARCH Pattern 1 taxonomy — applied gate-FIRST like healing/confidence's
uniqueness gate, infrastructure first, product_defect last/default):

  infrastructure : browser-crash / "Target closed" / net::ERR_ / ERR_CONNECTION_REFUSED / DNS /
                   timeout that never reached the target / infra_health == 'down'
                   (the environment is down — NOT the app misbehaving)
  automation     : a locator/selector miss or test-data mismatch AFTER an un-healed/quarantined
                   heal (heal_outcome in {fail_as_defect, quarantine}) with the page otherwise
                   loaded — the AUTOMATION drifted, not the product
  product_defect : an assertion failure on a SUCCESSFULLY-LOADED page / functional / validation /
                   API 4xx-5xx / the SEED_BUG signature — the app behaved wrong (the default)

Confidence is a clamped 0-100 weighted blend: a strong class signal + corroborating same-class
signals - conflicting cross-class signals, then max(0, min(100, raw)). The weights are FROZEN
starting points (RESEARCH A1 — HIGH on shape, LOW on exact values) the QUAL-03 harness calibrates
in Plan 02 (the heal-band 0.85 -> 0.15 precedent); callers never hardcode literals.

Acceptance (test_classifier.py / test_no_llm_in_classifier.py): this module imports NOTHING from
the LLM/gateway/graph/DB/browser plane — it is stdlib-only (dataclasses) plus the sibling pure
infra_health signal. The weights are swappable per call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.defects.infra_health import infra_health

INFRA = "infrastructure"
AUTOMATION = "automation"
PRODUCT = "product_defect"


@dataclass(frozen=True)
class ClassifierWeights:
    """Tunable, FROZEN confidence weights (swap per call via the `w` arg).

    Frozen so a shared DEFAULT_WEIGHTS can never be mutated under callers (the kg/risk.RiskWeights
    + healing/confidence.HealWeights + explorer/budget.ExploreBudget discipline). Exact values are
    RESEARCH A1 starting points the QUAL-03 harness tunes (Plan 02).
    """

    strong_class_signal: int = 60   # the unambiguous class signal is present (e.g. ERR_CONNECTION_REFUSED)
    corroborating_signal: int = 20  # each ADDITIONAL same-class signal (infra_health, heal history, page-loaded)
    weak_or_conflicting: int = -15  # each cross-class signal present (lowers confidence)


DEFAULT_WEIGHTS = ClassifierWeights()

# --- Error-text signature patterns (compiled once; the fingerprint/infra_health discipline) ---
_INFRA_PATTERNS = [
    re.compile(r"Target closed", re.I),
    re.compile(r"browser has been closed", re.I),
    re.compile(r"crash", re.I),
    re.compile(r"net::ERR_", re.I),
    re.compile(r"ERR_CONNECTION_REFUSED", re.I),
    re.compile(r"ECONNREFUSED", re.I),
    re.compile(r"ERR_NAME_NOT_RESOLVED", re.I),  # DNS
    re.compile(r"getaddrinfo", re.I),
    re.compile(r"connection refused", re.I),
]
_TIMEOUT_RE = re.compile(r"\btimeout\b|timed out|exceeded waiting", re.I)
_LOCATOR_RE = re.compile(
    r"locator|selector|element not found|no element|not found|resolved \d+ elements|test[- ]data",
    re.I,
)
_PRODUCT_RE = re.compile(
    r"AssertionError|assert|expect\(|to_be_visible|to_have|expected .* (?:but|received)|"
    r"\b[45]\d\d\b|internal server error|validation",
    re.I,
)

_UNHEALED_OUTCOMES = frozenset({"fail_as_defect", "quarantine"})


def _has_infra_signature(error_text: str) -> bool:
    return any(p.search(error_text) for p in _INFRA_PATTERNS)


def _classify_rules(evidence: dict, cited: list[str]) -> str:
    """PURE precedence body: infrastructure first, automation, product_defect last/default.

    Appends every signal that fired to `cited` (so the classifications.evidence snapshot records
    WHY). The precedence order IS the structural gate (the healing/confidence gate-first discipline).
    """
    error_text = str(evidence.get("error_text") or "")
    page_loaded = bool(evidence.get("page_loaded"))
    heal_outcome = evidence.get("heal_outcome")
    # Derive the infra-health signal from the error text when the caller did not pass one.
    health = evidence.get("infra_health") or infra_health(error_text, page_loaded=page_loaded)

    # 1) INFRASTRUCTURE — the environment is down / the browser crashed / never reached the target.
    if _has_infra_signature(error_text):
        cited.append("infra:error-signature")
        if health == "down":
            cited.append("infra:health-down")
        return INFRA
    if health == "down":
        cited.append("infra:health-down")
        return INFRA
    if _TIMEOUT_RE.search(error_text) and not page_loaded:
        cited.append("infra:timeout-never-loaded")
        return INFRA

    # 2) AUTOMATION — a locator/selector/test-data miss AFTER an un-healed/quarantined heal, with
    #    the page otherwise loaded (the automation drifted, not the product).
    if heal_outcome in _UNHEALED_OUTCOMES:
        cited.append(f"automation:heal-{heal_outcome}")
        if _LOCATOR_RE.search(error_text):
            cited.append("automation:locator-miss")
        if page_loaded:
            cited.append("automation:page-loaded")
        return AUTOMATION

    # 3) PRODUCT DEFECT — an assertion/functional/validation/API failure on a LOADED page (default).
    if _PRODUCT_RE.search(error_text):
        cited.append("product:assertion-or-api")
    if page_loaded:
        cited.append("product:page-loaded")
    if not cited:
        cited.append("product:default")  # the conservative default when no signal fired
    return PRODUCT


def _corroboration(cls: str, cited: list[str]) -> int:
    """Count ADDITIONAL same-class signals beyond the first (the strong signal)."""
    same = [c for c in cited if c.startswith(_PREFIX[cls])]
    return max(0, len(same) - 1)


def _conflict(cls: str, cited: list[str]) -> int:
    """Count cited signals belonging to a DIFFERENT class (cross-class noise)."""
    return len([c for c in cited if not c.startswith(_PREFIX[cls])])


_PREFIX = {INFRA: "infra:", AUTOMATION: "automation:", PRODUCT: "product:"}


def classify(evidence: dict, w: ClassifierWeights = DEFAULT_WEIGHTS) -> dict:
    """PURE: evidence dict -> {classification, confidence 0-100, cited}. No I/O, no LLM, no browser.

    `evidence` keys (any absent -> falsey): error_text(str), page_loaded(bool), heal_outcome
    (str|None in {auto_heal, quarantine, fail_as_defect, None}), infra_health(str in {up,down,
    unknown}), flow_id(str), step(str).

    1) the deterministic precedence rules pick the class + populate `cited`;
    2) confidence = strong + corroborating*extra_same_class - weak*cross_class, clamped to 0-100.
    The clamp guarantees the range regardless of the weights (pathological weights floor/cap).
    """
    cited: list[str] = []
    cls = _classify_rules(evidence, cited)
    raw = (
        w.strong_class_signal
        + w.corroborating_signal * _corroboration(cls, cited)
        + w.weak_or_conflicting * _conflict(cls, cited)
    )
    confidence = max(0, min(100, raw))
    return {"classification": cls, "confidence": confidence, "cited": cited}
