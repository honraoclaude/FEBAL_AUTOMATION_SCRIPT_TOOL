"""Pure workflow-flag + form-validation extraction tests (EXPL-04) — no browser, no spend.

parse_workflow_flag turns a decide response into {flow, order} (or None); a sequence of
stepped states assembles an ordered Workflow→STEP→Page chain; extract_validation_rules turns
a (gated) form-submit result into [{field, message}]. All pure — the live probe is gated by
the risk classifier (verified by the act-gate ordering in test_safety.py).
"""

from app.services.explorer.nodes import extract_validation_rules, parse_workflow_flag


def test_parse_workflow_flag_step_of_flow():
    """'2 step 3 of checkout' (index + note) yields {flow: checkout, order: 3}."""
    assert parse_workflow_flag("2 step 3 of checkout") == {"flow": "checkout", "order": 3}


def test_parse_workflow_flag_kv_form():
    """A key/value note 'flow=login, step=1' is parsed too."""
    assert parse_workflow_flag("0 (flow=login, step=1)") == {"flow": "login", "order": 1}


def test_parse_workflow_flag_strips_flow_suffix():
    """'step 2 of login flow' drops the trailing 'flow' word."""
    assert parse_workflow_flag("1 step 2 of login flow") == {"flow": "login", "order": 2}


def test_parse_workflow_flag_absent_returns_none():
    """A plain index response carries no workflow flag."""
    assert parse_workflow_flag("3") is None
    assert parse_workflow_flag("") is None
    assert parse_workflow_flag(None) is None


def test_ordered_workflow_chain_assembly():
    """A sequence of stepped flags assembles an ordered chain (order preserved)."""
    responses = ["0 step 1 of checkout", "2 step 2 of checkout", "1 step 3 of checkout"]
    chain = []
    for step, resp in enumerate(responses):
        flag = parse_workflow_flag(resp)
        if flag is not None:
            chain.append({"flow": flag["flow"], "order": flag["order"], "page_key": f"p{step}"})
    assert [c["order"] for c in chain] == [1, 2, 3]
    assert all(c["flow"] == "checkout" for c in chain)
    assert [c["page_key"] for c in chain] == ["p0", "p1", "p2"]


def test_extract_validation_rules_captures_field_and_message():
    """A submit result with validation errors records {field, message} per offending field."""
    submit_result = {
        "form_id": "login",
        "errors": [
            {"field": "user-name", "message": "Please fill out this field."},
            {"field": "password", "message": "Please fill out this field."},
        ],
    }
    rules = extract_validation_rules(submit_result)
    assert rules == [
        {"field": "user-name", "message": "Please fill out this field."},
        {"field": "password", "message": "Please fill out this field."},
    ]


def test_extract_validation_rules_skips_empty_message():
    """An error with no message is dropped (nothing to record)."""
    submit_result = {"errors": [{"field": "x", "message": ""}, {"field": "y", "message": "bad"}]}
    assert extract_validation_rules(submit_result) == [{"field": "y", "message": "bad"}]


def test_extract_validation_rules_empty_when_no_errors():
    """A clean submit (no errors) yields no validation rules."""
    assert extract_validation_rules({"form_id": "f", "errors": []}) == []
    assert extract_validation_rules({}) == []
