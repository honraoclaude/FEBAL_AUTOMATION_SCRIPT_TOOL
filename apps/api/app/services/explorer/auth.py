"""Auth handling for the explorer (Phase 4, EXPL-02) — login detect, login, storageState, relogin.

Generalizes the Slice-1 hardcoded SauceDemo login into:
  * detect_login_form(tree)  — heuristic over a normalized node tree: a password input + a
    nearby text/email input + a submit control → a LoginForm of CSS selectors; else None.
  * perform_login(page, user, password, form) — fill the detected fields and submit.
  * capture_storage_state(context, run_id) / load_storage_state_path(run_id) — persist the
    post-login session blob under workspaces/<run_id>/storage_state.json and reuse it.
  * needs_relogin(tree) — a password input reappeared mid-run → logged out → True.
  * maybe_relogin(state, page) — the node-level guard the perceive node calls: if logged out
    mid-run, re-detect + re-login with the SAME creds (fetched ONCE via the single decrypt
    surface and cached on the per-run handle registry — never on the checkpointed state).

SECURITY (T-04-07): credentials come ONLY from target_service.get_decrypted_credentials (the
single decrypt surface). This module NEVER imports a crypto primitive, NEVER logs a
credential value, and NEVER writes a credential onto an ExplorerState field or a Neo4j node.
The decrypted (user, password) is held transiently in the per-run handle registry's auth slot
(outside the checkpointed/serialized state) so a mid-run relogin can reuse it.

storageState (T-04-08): the session blob is written under the gitignored, run_id-derived
workspaces/<run_id>/ tree — never a platform-wide session, never client-controlled path.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.core.workspaces import run_dir
from app.services import target_service

log = structlog.get_logger()

# SauceDemo (Swag Labs) fast-path ids — tried first, then the generic heuristic.
_SAUCE_USER = "#user-name"
_SAUCE_PASS = "#password"
_SAUCE_SUBMIT = "#login-button"

_TEXT_INPUT_TYPES = {"text", "email", "tel", None, ""}


@dataclass(frozen=True)
class LoginForm:
    """The detected login field locators (CSS selectors) — NO credential values here."""

    username_selector: str
    password_selector: str
    submit_selector: str


def _selector_for(node: dict, *, fallback: str) -> str:
    """Build a stable CSS selector for an input/button node: id > name > type fallback."""
    attrs = node.get("attrs") or {}
    if attrs.get("id"):
        return f"#{attrs['id']}"
    if attrs.get("data-test"):
        return f"[data-test='{attrs['data-test']}']"
    if attrs.get("name"):
        return f"[name='{attrs['name']}']"
    return fallback


def _walk_inputs(tree: dict) -> list[dict]:
    """Flatten the node tree to its input/button nodes in document order."""
    out: list[dict] = []

    def walk(n: dict) -> None:
        tag = (n.get("tag") or "").lower()
        role = (n.get("role") or "").lower()
        if tag in {"input", "button"} or role in {"button", "textbox"}:
            out.append(n)
        for c in n.get("children") or []:
            walk(c)

    walk(tree)
    return out


def _is_password(node: dict) -> bool:
    return ((node.get("attrs") or {}).get("type") or "").lower() == "password"


def _is_text_input(node: dict) -> bool:
    attrs = node.get("attrs") or {}
    tag = (node.get("tag") or "").lower()
    t = (attrs.get("type") or "").lower() or None
    return tag == "input" and t in _TEXT_INPUT_TYPES and t != "password"


def _is_submit(node: dict) -> bool:
    attrs = node.get("attrs") or {}
    tag = (node.get("tag") or "").lower()
    role = (node.get("role") or "").lower()
    t = (attrs.get("type") or "").lower()
    return tag == "button" or role == "button" or (tag == "input" and t == "submit")


def detect_login_form(tree: dict) -> LoginForm | None:
    """Heuristic login-form detection (RESEARCH:316-321) over a normalized node tree.

    A login form = a password input + the NEAREST PRECEDING text/email input (the username
    field) + a submit control. SauceDemo's known ids are tried as a fast path first, then the
    generic heuristic. Returns None when there is no password input (not a login page).
    """
    if tree is None:
        return None
    inputs = _walk_inputs(tree)
    password_node = next((n for n in inputs if _is_password(n)), None)
    if password_node is None:
        return None  # no password input → not a login page

    pwd_pos = inputs.index(password_node)
    # The username field: the nearest preceding text/email input (else the first text input).
    username_node = None
    for n in reversed(inputs[:pwd_pos]):
        if _is_text_input(n):
            username_node = n
            break
    if username_node is None:
        username_node = next((n for n in inputs if _is_text_input(n)), None)

    submit_node = next((n for n in inputs[pwd_pos:] if _is_submit(n)), None)
    if submit_node is None:
        submit_node = next((n for n in inputs if _is_submit(n)), None)

    return LoginForm(
        username_selector=_selector_for(username_node or {}, fallback=_SAUCE_USER),
        password_selector=_selector_for(password_node, fallback=_SAUCE_PASS),
        submit_selector=_selector_for(submit_node or {}, fallback=_SAUCE_SUBMIT),
    )


def needs_relogin(tree: dict) -> bool:
    """True when the session looks logged out mid-run: a password input reappeared.

    The cheap, deterministic logout signal (RESEARCH:321): if the current page exposes a
    password input again, the session expired/was logged out → the perceive guard re-logs in.
    """
    if tree is None:
        return False
    return any(_is_password(n) for n in _walk_inputs(tree))


async def perform_login(page, user: str, password: str, form: LoginForm) -> None:  # noqa: ANN001
    """Fill the detected username/password fields and submit (creds never logged).

    user/password come from the single decrypt surface (caller's responsibility); this fn
    never logs them and never persists them anywhere but the live form fields.
    """
    await page.fill(form.username_selector, user)
    await page.fill(form.password_selector, password)
    await page.click(form.submit_selector)
    await page.wait_for_load_state("domcontentloaded")
    log.info("explore_login_submitted", username_selector=form.username_selector)  # NO creds


def storage_state_path(run_id: str) -> str:
    """The run_id-derived storageState path (gitignored workspaces tree, T-04-08)."""
    return str(run_dir(run_id, create=True) / "storage_state.json")


async def capture_storage_state(context, run_id: str) -> str:  # noqa: ANN001
    """Persist the post-login session blob to workspaces/<run_id>/storage_state.json; return path."""
    path = storage_state_path(run_id)
    await context.storage_state(path=path)
    log.info("explore_storage_state_captured", run_id=run_id)  # path is run_id-derived, no secret
    return path


def load_storage_state_path(run_id: str) -> str | None:
    """Return the storageState path for reuse on a new context, or None if not captured yet."""
    from pathlib import Path

    path = run_dir(run_id) / "storage_state.json"
    return str(path) if Path(path).exists() else None


async def authenticate_if_needed(db, page, target_id: int, run_id: str) -> bool:  # noqa: ANN001
    """Detect a login form on the current page and, if present, log in via the single surface.

    Fetches creds ONCE via target_service.get_decrypted_credentials (T-04-07), performs the
    login, caches the creds on the per-run handle registry for a later relogin, and captures
    storageState. Returns True if a login was performed, False if the page was not a login form.
    Creds are NEVER logged and NEVER written to ExplorerState or a Neo4j node.
    """
    from app.services.explorer.fingerprint import page_fingerprint  # local: avoid cycle

    tree = await _page_node_tree(page)
    form = detect_login_form(tree)
    if form is None:
        return False

    user, password = await target_service.get_decrypted_credentials(db, target_id)
    await perform_login(page, user, password, form)
    _cache_creds(run_id, user, password, form)
    context = page.context
    await capture_storage_state(context, run_id)
    # Touch the fingerprint so a caller can confirm we left the login page (best-effort).
    await page_fingerprint(page)
    return True


async def maybe_relogin(state: dict, page) -> bool:  # noqa: ANN001
    """Node-level guard (called by perceive): if logged out mid-run, re-login with cached creds.

    Returns True if a relogin happened. Uses the creds cached at first login (held in the
    per-run registry, NOT on state) so no second decrypt and no creds on the serialized state.
    """
    tree = await _page_node_tree(page)
    if not needs_relogin(tree):
        return False
    cached = _get_cached_creds(state["run_id"])
    if cached is None:
        return False  # never authenticated this run → nothing to recover with
    user, password, form = cached
    log.info("explore_relogin", run_id=state["run_id"])  # NO creds
    await perform_login(page, user, password, form)
    return True


# --- credential cache (per-run, OUTSIDE the checkpointed state — H-1/T-04-07) ---
# Keyed by run_id; holds the transient (user, password, LoginForm) only for the run's life so
# a mid-run relogin needs no second decrypt. NEVER serialized, NEVER logged.
_RUN_CREDS: dict[str, tuple[str, str, LoginForm]] = {}


def _cache_creds(run_id: str, user: str, password: str, form: LoginForm) -> None:
    _RUN_CREDS[run_id] = (user, password, form)


def _get_cached_creds(run_id: str) -> tuple[str, str, LoginForm] | None:
    return _RUN_CREDS.get(run_id)


def clear_creds(run_id: str) -> None:
    """Drop the per-run credential cache (driver's finally — never outlive the run)."""
    _RUN_CREDS.pop(run_id, None)


async def _page_node_tree(page) -> dict:  # noqa: ANN001
    """Extract the {role/tag/attrs/children} node tree from the live page (same DOM walk shape).

    Reuses the fingerprint module's DOM-walk JS so detection sees the same structure the
    fingerprint does. Kept here (not in the pure fingerprint hashing path) since it touches
    the page.
    """
    from app.services.explorer.fingerprint import _DOM_TREE_JS, normalize_aria_tree

    raw = await page.evaluate(_DOM_TREE_JS, 12)
    return normalize_aria_tree(raw or {})
