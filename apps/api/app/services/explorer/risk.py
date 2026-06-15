"""Deterministic, code-enforced action-risk + origin-scope gates (EXPL-07 / EXPL-08, D-03/D-04).

THE SAFETY LAYER IS PURE CODE — NEVER LLM JUDGMENT (anti-pattern RESEARCH:251).
The explorer's decide node lets the LLM pick an action INDEX from a code-enumerated menu;
this module is the deterministic gate the act node runs AFTER that decision and BEFORE the
click/goto (defense in depth, Pitfall 5 RESEARCH:410-412): even a fully prompt-injected LLM
that picks a destructive or off-origin action is REFUSED here by a static deny-list, so the
action never executes.

Two pure guards (no browser, no LLM, no db — table-unit-testable like
run_service._validate_status):
  - is_destructive(action, *, sandbox): deny-list match on the action's label + confirm_text.
    The Target.sandbox flag LIFTS the deny (restorable targets, D-03).
  - is_off_origin(url, allowlist): the navigation target's scheme://host[:port] origin must be
    a member of the allowlist (D-04); off-origin gotos are refused in code before navigation.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# RESEARCH "Action Risk Classifier" (lines 323-338) — the canonical deny-list. Multi-word
# phrases ("submit order") are matched as substrings of the lowercased label+confirm_text.
DENY_VERBS: frozenset[str] = frozenset(
    {
        "delete",
        "remove",
        "destroy",
        "send",
        "pay",
        "purchase",
        "checkout",
        "submit order",
        "place order",
        "logout",
        "sign out",
        "cancel subscription",
        "deactivate",
        "wipe",
        "reset",
    }
)


def is_destructive(action: dict, *, sandbox: bool) -> bool:
    """True when the action matches the deny-list — UNLESS the target is a sandbox (D-03).

    Pure: signals come ONLY from the action's own label + confirm_text (code-enumerated by
    the menu), never from LLM judgment. The sandbox flag (Target.sandbox) lifts the deny for
    restorable targets so the explorer can exercise destructive flows where it is safe.

    A safe verb (navigate/read/form-fill of a non-submit field) matches no deny verb and is
    allowed by default (default-allow, deny-list-only).
    """
    if sandbox:  # restorable target — the deny is lifted (D-03)
        return False
    label = action.get("label", "") or ""
    confirm_text = action.get("confirm_text", "") or ""
    text = f"{label} {confirm_text}".lower()
    return any(verb in text for verb in DENY_VERBS)


def _origin(url: str) -> str | None:
    """Return the scheme://host[:port] origin of a URL, or None if it has no scheme+host.

    Normalizes case (scheme/host are case-insensitive) so allowlist membership is robust.
    """
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def is_off_origin(url: str, allowlist: list[str]) -> bool:
    """True when url's origin is NOT in the allowlist — refuse the goto in code (D-04).

    The allowlist holds origins (scheme://host[:port], server-defaulted to the target's
    base_url origin in Phase 1). Both the candidate URL and the allowlist entries are reduced
    to their canonical origin before comparison so a path/query on either side is ignored.
    A URL with no resolvable origin (relative/garbage) is treated as off-origin (refused).
    """
    target_origin = _origin(url)
    if target_origin is None:
        return True
    allowed = {o for o in (_origin(a) for a in (allowlist or [])) if o is not None}
    return target_origin not in allowed
