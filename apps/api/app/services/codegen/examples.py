"""Deterministic KG→Examples derivation for scenario outlines (GEN-01 / D GEN-01).

Scenario Outlines need an `Examples:` table; the data is DERIVED deterministically from the KG,
NOT invented by the LLM (RESEARCH Novel Mechanism 2):

  - Form fields → Example COLUMNS. `page_detail["forms"]` carries form-field metadata; each
    field becomes a column (e.g. <username>, <password>). If a form lists no fields, fall back
    to the element labels of textbox/input-role elements on the page.
  - BusinessEntity instances + the SauceDemo public user matrix → POSITIVE rows.
    The well-known public Swag Labs demo accounts (standard_user/locked_out_user/problem_user/
    performance_glitch_user) seed rows; standard_user is the canonical positive (expected_result
    = success). PLAT-07: ONLY public demo creds — never target ciphertext.
  - Validation rules → NEGATIVE rows (A3 fallback). If the KG carries validation rules they
    drive a negative row whose Then asserts an ERROR page-state; if absent, derive a negative
    row from required-field EMPTINESS (an empty required field → an error page-state). Either
    way the negative row's `expected_result` is "error" and `then_kind`/`then_ref` point at a
    page-state (so the no-vacuous gate has a graph-backed Then).

PURE function over the KG read structures — unit-testable on a fixture graph, no keys, no neo4j.
An `expected_result` column (success|error) + a `then_ref` column ride along so the caller can
build the per-row Then annotation; the visible Gherkin Examples columns are the form fields +
expected_result.
"""

from __future__ import annotations

# The well-known PUBLIC Swag Labs demo accounts (PLAT-07 — public demo creds only).
# locked_out_user is the canonical NEGATIVE login account (its Then asserts an error state).
_SAUCEDEMO_PUBLIC_USERS = (
    {"username": "standard_user", "expected_result": "success"},
    {"username": "locked_out_user", "expected_result": "error"},
    {"username": "problem_user", "expected_result": "success"},
    {"username": "performance_glitch_user", "expected_result": "success"},
)
_SAUCEDEMO_PASSWORD = "secret_sauce"


def _form_columns(page_detail: dict) -> list[str]:
    """Form-field names → Example columns; fall back to textbox element labels."""
    columns: list[str] = []
    for form in page_detail.get("forms", []) or []:
        for field in form.get("fields", []) or []:
            name = field.get("name") or field.get("label")
            if name and name not in columns:
                columns.append(name)
    if columns:
        return columns
    # Fallback: input/textbox element labels become columns (deterministic).
    for el in page_detail.get("elements", []) or []:
        if el.get("role") in ("textbox", "input") and el.get("label"):
            label = el["label"]
            if label not in columns:
                columns.append(label)
    return columns


def _error_page_ref(page_detail: dict) -> dict:
    """A page-state ref a negative-row Then asserts (the SAME page = the validation/error state).

    The negative row stays on the login/form page (the error is shown there), so the Then's
    page ref resolves against an EXISTING page — keeping the no-vacuous gate satisfied.
    """
    fp = page_detail.get("fingerprint")
    if fp:
        return {"page_fingerprint": fp}
    return {"page_url": page_detail.get("url")}


def _success_page_ref(page_detail: dict) -> dict:
    """A page-state ref a positive-row Then asserts: the page navigated to on success.

    Uses the first navigates_to target when present (the post-submit landing page); else the
    page itself (still graph-backed).
    """
    nav = page_detail.get("navigates_to", []) or []
    if nav and nav[0].get("to"):
        return {"page_fingerprint": nav[0]["to"]}
    return _error_page_ref(page_detail)


def derive_examples(
    page_detail: dict,
    *,
    public_users: list | None = None,
    entity_map: dict | None = None,
    validation_rules: list | None = None,
) -> dict:
    """PURE: build {"columns": [...], "rows": [...]} from a page_detail KG structure.

    Each row is a dict keyed by the columns PLUS `expected_result` (success|error), `then_kind`
    ("page"), and `then_ref` (a graph-backed page ref). At least one positive row (standard_user)
    and at least one negative/error row are always produced for a SauceDemo login-style form.
    """
    users = public_users if public_users is not None else list(_SAUCEDEMO_PUBLIC_USERS)
    columns = _form_columns(page_detail)
    has_password_col = any(c.lower() == "password" for c in columns)

    rows: list[dict] = []
    for user in users:
        result = user.get("expected_result", "success")
        row: dict = {}
        # Fill known columns deterministically: username + password where present.
        for col in columns:
            low = col.lower()
            if low == "username":
                row[col] = user.get("username", "")
            elif low == "password":
                row[col] = _SAUCEDEMO_PASSWORD
            else:
                row[col] = ""
        if not columns:
            # No form columns discovered — still emit a username column so the outline is usable.
            row["username"] = user.get("username", "")
            if has_password_col:
                row["password"] = _SAUCEDEMO_PASSWORD
        row["expected_result"] = result
        row["then_kind"] = "page"
        row["then_ref"] = (
            _success_page_ref(page_detail)
            if result == "success"
            else _error_page_ref(page_detail)
        )
        rows.append(row)

    # A3 fallback: if NO user supplied a negative row, derive one from required-field emptiness.
    if not any(r["expected_result"] == "error" for r in rows):
        neg: dict = {col: "" for col in columns} or {"username": ""}
        neg["expected_result"] = "error"
        neg["then_kind"] = "page"
        neg["then_ref"] = _error_page_ref(page_detail)
        rows.append(neg)

    # Validation rules (A3): each rule adds a negative row asserting the error page-state.
    for rule in validation_rules or []:
        neg = {col: "" for col in columns} or {"username": ""}
        field = rule.get("field")
        if field and field in neg:
            neg[field] = rule.get("invalid_value", "")
        neg["expected_result"] = "error"
        neg["then_kind"] = "page"
        neg["then_ref"] = _error_page_ref(page_detail)
        rows.append(neg)

    # The VISIBLE Gherkin Examples columns: the form fields + expected_result.
    visible_columns = columns + ["expected_result"] if columns else ["username", "expected_result"]
    return {"columns": visible_columns, "rows": rows}
