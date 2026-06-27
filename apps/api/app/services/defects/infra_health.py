"""PURE infra-health signal (DEF-02) — the error-pattern source (RESEARCH Open-Q2 option b).

D-02 wants infra health as a CITED classification signal. RESEARCH Open-Q2 recommends starting
with the pure error-PATTERN signal (connection-refused / DNS / timeout-reaching-target patterns
over the error text) rather than a live Docker-health probe, which couples the classifier to the
container plane (deferred to Phase 11). The dead-port QUAL-03 case proves this deterministically.

PURE: stdlib re only — imports NOTHING from the LLM/gateway/graph/DB/Docker plane (the
test_no_llm_in_classifier gate scans this file). Returns one of 'down' | 'up' | 'unknown'.
"""

from __future__ import annotations

import re

# Error-text patterns that signal the TARGET environment is down/unreachable (not the app failing
# a business rule). Compiled once; case-insensitive.
_DOWN_PATTERNS = [
    re.compile(r"ERR_CONNECTION_REFUSED", re.I),
    re.compile(r"ECONNREFUSED", re.I),
    re.compile(r"net::ERR_NAME_NOT_RESOLVED", re.I),  # DNS
    re.compile(r"ERR_NAME_NOT_RESOLVED", re.I),
    re.compile(r"getaddrinfo|name or service not known", re.I),  # DNS
    re.compile(r"connection refused", re.I),
    re.compile(r"connection reset", re.I),
    re.compile(r"could not (?:reach|connect)", re.I),
    re.compile(r"net::ERR_", re.I),  # any chromium network error
]

# A timeout signals 'down' ONLY when the page never loaded (a timeout on a loaded page is a slow
# app assertion, not an infra outage) — that nuance is applied by the caller via page_loaded; here
# a bare timeout pattern is a WEAK down hint folded into the classifier's corroboration counting.
_TIMEOUT_RE = re.compile(r"\btimeout\b|timed out|exceeded waiting", re.I)


def infra_health(error_text: str | None, *, page_loaded: bool | None = None) -> str:
    """PURE: derive 'down' | 'up' | 'unknown' from the error-text patterns.

    - any explicit network/DNS/connection pattern -> 'down';
    - a timeout WITH page_loaded falsey (never reached the target) -> 'down';
    - a non-empty error_text with none of the above -> 'up' (the target was reachable, the
      failure is elsewhere — an assertion/locator);
    - no error_text -> 'unknown'.
    """
    if not error_text:
        return "unknown"
    for pat in _DOWN_PATTERNS:
        if pat.search(error_text):
            return "down"
    if _TIMEOUT_RE.search(error_text) and not page_loaded:
        return "down"
    return "up"
