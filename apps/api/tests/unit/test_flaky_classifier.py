"""Pure flaky-vs-product retry classifier table tests (EXEC-05 / D-05) — keyless, no I/O.

classify_retry maps a list of per-attempt exit codes (from the worker's 2x retry loop) to a
verdict. The rule (D-05, RESEARCH "The flaky classifier"):

  - passed on the first attempt (no retry needed)        -> "passed"
  - passed only after a retry (any attempt exit 0, len>1) -> "flaky" (infra flake)
  - all attempts failed                                   -> "product_failure"

The classifier is PURE (no I/O, no LLM) and mirrors kg/risk.py discipline — so it is fully
table-testable with no session/broker/keys. ("aborted" is set by the Plan-04 kill path, not
here, and is therefore not exercised by this table.)
"""

from __future__ import annotations

import pytest

from app.services.worker.classifier import classify_retry


@pytest.mark.parametrize(
    ("exit_codes", "expected_verdict"),
    [
        ([0], "passed"),  # passed first try, no retry -> passed
        ([1, 0], "flaky"),  # failed then passed on retry -> flaky (infra)
        ([1, 1, 0], "flaky"),  # failed twice then passed on the last retry -> flaky
        ([1, 1, 1], "product_failure"),  # all three attempts failed -> product
        ([1], "product_failure"),  # single failed attempt (no retry) -> product
        ([2, 0], "flaky"),  # non-1 failure code then pass -> still flaky
    ],
)
def test_classify_retry_verdict_table(exit_codes: list[int], expected_verdict: str) -> None:
    assert classify_retry(exit_codes)["verdict"] == expected_verdict


def test_classify_retry_records_attempts_and_exit_codes() -> None:
    result = classify_retry([1, 1, 0])
    assert result["attempts"] == 3
    assert result["passed"] is True
    assert result["exit_codes"] == [1, 1, 0]


def test_classify_retry_passed_field_false_on_all_fail() -> None:
    result = classify_retry([1, 1, 1])
    assert result["passed"] is False
    assert result["attempts"] == 3
    assert result["exit_codes"] == [1, 1, 1]


def test_classify_retry_single_pass_attempts_one() -> None:
    result = classify_retry([0])
    assert result == {
        "verdict": "passed",
        "attempts": 1,
        "passed": True,
        "exit_codes": [0],
    }


def test_classify_retry_is_pure_returns_fresh_list() -> None:
    """The returned exit_codes must not alias the caller's input list (defensive copy)."""
    codes = [1, 0]
    result = classify_retry(codes)
    codes.append(99)
    assert result["exit_codes"] == [1, 0]
