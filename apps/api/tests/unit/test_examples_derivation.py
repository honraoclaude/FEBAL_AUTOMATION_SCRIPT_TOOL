"""Unit: KG→Examples derivation (GEN-01). Pure function, no keys, no neo4j."""

from app.services.codegen.examples import derive_examples
from tests.fixtures.kg_scenarios import INVENTORY_PAGE_DETAIL, LOGIN_PAGE_DETAIL


def test_form_fields_become_columns():
    out = derive_examples(LOGIN_PAGE_DETAIL)
    # The login form's fields → Example columns (+ expected_result).
    assert "username" in out["columns"]
    assert "password" in out["columns"]
    assert "expected_result" in out["columns"]


def test_public_user_matrix_seeds_positive_and_negative_rows():
    out = derive_examples(LOGIN_PAGE_DETAIL)
    results = [r["expected_result"] for r in out["rows"]]
    # standard_user is a positive (success) row.
    assert "success" in results
    # locked_out_user is a negative (error) row.
    assert "error" in results
    # standard_user present with the public password.
    standard = next(r for r in out["rows"] if r.get("username") == "standard_user")
    assert standard["password"] == "secret_sauce"
    assert standard["expected_result"] == "success"


def test_negative_row_then_ref_points_at_a_page_state():
    out = derive_examples(LOGIN_PAGE_DETAIL)
    neg = next(r for r in out["rows"] if r["expected_result"] == "error")
    assert neg["then_kind"] == "page"
    # The error row asserts the login page (the validation/error state is shown there).
    assert neg["then_ref"].get("page_fingerprint") or neg["then_ref"].get("page_url")


def test_positive_row_then_ref_points_at_navigated_page():
    out = derive_examples(LOGIN_PAGE_DETAIL)
    pos = next(r for r in out["rows"] if r["expected_result"] == "success")
    # success Then targets the navigates_to destination (inventory) when present.
    assert pos["then_ref"].get("page_fingerprint") == "fp-inventory"


def test_at_least_one_positive_and_one_negative_row():
    out = derive_examples(LOGIN_PAGE_DETAIL)
    results = [r["expected_result"] for r in out["rows"]]
    assert results.count("success") >= 1
    assert results.count("error") >= 1


def test_a3_fallback_when_no_negative_user_supplied():
    # Pass only a positive user → the A3 required-field-emptiness negative row is appended.
    out = derive_examples(
        LOGIN_PAGE_DETAIL,
        public_users=[{"username": "standard_user", "expected_result": "success"}],
    )
    results = [r["expected_result"] for r in out["rows"]]
    assert "error" in results


def test_columns_fall_back_to_element_labels_when_form_has_no_fields():
    # The inventory page has a form with NO fields → no form columns; rows still produced.
    out = derive_examples(INVENTORY_PAGE_DETAIL)
    assert out["rows"]  # at least the user matrix + A3 negative
    assert "expected_result" in out["columns"]
