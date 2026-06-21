"""PURE flaky-vs-product retry classifier (EXEC-05 / D-05) — NO I/O, NO LLM.

The worker runs a failed flow up to 2× (original + 2 retries) and feeds the per-attempt exit
codes here. The verdict rule (D-05, RESEARCH "The flaky classifier"):

  - passed on a clean first attempt           -> "passed"
  - passed only after a retry (passed + len>1) -> "flaky" (an infra flake, not a product bug)
  - all attempts failed                        -> "product_failure"

This module mirrors kg/risk.py discipline: stdlib-only, pure, table-testable — it imports
NOTHING from the graph driver, the metered LLM path, the DB session, or aio-pika. The full
3-way classification (product / test-bug / infra) with calibrated confidence is Phase 9; this
slice is the retry-only flaky vs product split. The "aborted" verdict is set by the kill path
(Plan 04), never here.

SC3: no LLM/gateway/explorer import (the worker-plane grep gate scans this file).
"""

from __future__ import annotations


def classify_retry(attempt_exit_codes: list[int]) -> dict:
    """Map the retry loop's per-attempt exit codes to a verdict (D-05).

    `attempt_exit_codes` is the ordered list of subprocess exit codes (0 = passed) the worker
    observed across its attempts (1..3 entries). Returns a dict carrying the verdict, the
    attempt count, whether the flow passed at all, and a fresh copy of the exit codes (never an
    alias of the caller's list).

    passed = any attempt returned 0. If it passed but needed a retry to do so (len > 1) the
    verdict is "flaky" (infra flake); a clean single-attempt pass is "passed". If it never
    passed the verdict is "product_failure".
    """
    codes = list(attempt_exit_codes)  # defensive copy — never alias the caller's list
    passed = any(code == 0 for code in codes)
    retried = len(codes) > 1
    if passed:
        verdict = "flaky" if retried else "passed"
    else:
        verdict = "product_failure"
    return {
        "verdict": verdict,
        "attempts": len(codes),
        "passed": passed,
        "exit_codes": codes,
    }
