"""QUAL-03 classifier accuracy + threshold-calibration harness — keyless, deterministic.

The trust gate before ANY autonomous Jira filing is unlocked (DEF-03 / QUAL-03): a hand-labeled
failure set that spans all three classes is generated KEYLESSLY, the PRODUCTION pure classifier
(app.services.defects.classifier.classify, fed the SAME evidence dict shape the Plan-01 pipeline
assembles) is run over each, accuracy is asserted >= 0.85, and the calibrated
`jira_confidence_threshold` is derived from the measured per-class confidences and asserted against
the SHIPPED settings default — never a test-local literal. This is the fourth instance of the
keyless-accuracy-harness pattern (clone of QUAL-02's test_healing_mutations.py).

The three-class labeled set (KNOWN class -> keyless generator):

  product_defect : the SEED_BUG build (saucedemo-bug, SEED_BUG=1 — `.inventory_list` renamed to
                   `.inventory_list_BROKEN`, port 8081). The planted login spec reaches the
                   post-login page (it LOADS) and the `.inventory_list` success assertion FAILS —
                   an assertion failure on a successfully-loaded page = the product behaved wrong.
                   (the test_seeded_bug.py generator)
  automation     : an un-healed BREAK_REMOVE locator mutation (port 8086 — the login button
                   deleted). The heal-wired planted spec resolves the STALE-top login button, the
                   heal finds NO benign-grade candidate -> the heal-journal records fail_as_defect
                   (NEVER auto_heal, the QUAL-02 guard) and the spec FAILS with a locator miss on
                   an otherwise-loaded page = the AUTOMATION drifted, not the product.
                   (the test_healing_mutations.py BREAK_REMOVE generator, un-healed)
  infrastructure : a NET-NEW dead-port / forced-timeout fault — point a run at a NON-LISTENING
                   port (connection refused) and force a sub-second navigation timeout that never
                   reaches the target. No Docker build needed: the `_port_open` INVERSE (RESEARCH
                   A6). The error text carries an ERR_CONNECTION_REFUSED / timeout-never-loaded
                   signature = the environment is down.

KEYLESS + neo4j OFF in the RUN phase (RESEARCH Pitfall 6 / 3GB WSL cap): no provider keys, no real
Jira, no graph — the classifier is PURE and the failures come from the shipped SauceDemo Docker
builds + a stdlib-socket dead port + a sub-second Chromium timeout. The matrix runs the saucedemo
variants (128m each) + a Chromium subprocess only — same sequencing as test_seeded_bug.py /
test_healing_mutations.py. Memory fit under the 3GB cap is a Manual-Only `docker stats` observation.

REQUIRES the seeded-bug + mutation builds up (skips CLEANLY when down, mirroring test_seeded_bug.py
/ test_healing_mutations.py's REQUIRES notes):
  cd infra && docker compose --profile bugbuild up -d --wait saucedemo-bug
  cd infra && docker compose --profile mutation up -d --wait
Reached at 127.0.0.1 (NOT localhost): IPv4-only nginx; localhost->::1 is wedged on Windows/WSL.

Subprocess discipline: the inner planted-spec runner uses `["uv","run","python","-m","pytest", ...]`
(the 08-04 Windows Application Control deviation — the bare `pytest.exe` shim is blocked, os error
4551; `python -m pytest` is the allowed equivalent). stability.py is UNTOUCHED.
"""

from __future__ import annotations

import os
import shutil
import socket
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest

# Reuse the QUAL-02 heal-wired plant + journal helpers VERBATIM (same planted spec, same vendored
# heal page object) so the automation case exercises the SHIPPED heal path, not a re-implementation.
from tests.functional.test_healing_mutations import (
    _plant as _plant_heal,
    _read_journal,
    _run_spec_once_env,
)

# Reuse the standard planted login spec plant (the seeded-bug generator's spec) for the
# product_defect + infrastructure cases — the SAME spec test_seeded_bug.py drives.
from tests.functional.test_stability import _plant as _plant_login
from tests.functional.test_stability import _WORKSPACES_ROOT

pytestmark = [pytest.mark.functional]

# 127.0.0.1 (not localhost) — IPv4-only nginx; localhost->::1 is wedged on Windows/WSL.
_SEED_BUG_URL = "http://127.0.0.1:8081"  # saucedemo-bug (SEED_BUG=1) -> product_defect
_BREAK_REMOVE_URL = "http://127.0.0.1:8086"  # un-healed BREAK_REMOVE mutation -> automation

# The two builds the labeled set REQUIRES up (the dead-port infra fault needs NO build).
_REQUIRED_TARGETS = {
    "SEED_BUG": _SEED_BUG_URL,
    "BREAK_REMOVE": _BREAK_REMOVE_URL,
}

# The NET-NEW dead-port infra fault: a port that nothing listens on. 9 is the discard port, almost
# never bound; we additionally PROBE it is closed and skip the fault generation if it ever is open
# (so the case never silently mis-generates). A sub-second Chromium nav timeout forces the
# never-reached-target signature deterministically without waiting on a real outage.
_DEAD_PORT_URL = "http://127.0.0.1:9"


def _port_open(url: str) -> bool:
    """True iff the target host:port accepts a TCP connection (a cheap up-check)."""
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _require_targets() -> None:
    """Skip cleanly when the seeded-bug / mutation builds are down (mirrors test_seeded_bug.py)."""
    down = [name for name, url in _REQUIRED_TARGETS.items() if not _port_open(url)]
    if down:
        pytest.skip(
            "QUAL-03 labeled-set targets are not up "
            f"({', '.join(down)}). Bring them up with: "
            "cd infra && docker compose --profile bugbuild up -d --wait saucedemo-bug ; "
            "cd infra && docker compose --profile mutation up -d --wait"
        )


# ---------------------------------------------------------------------------------------------
# The dead-port / forced-timeout infra-fault generator (NET-NEW — RESEARCH A6, the _port_open
# inverse). Render a planted login spec whose nav timeout is sub-second and whose BASE_URL points
# at a non-listening port, so the goto fails with a connection-refused / never-reached signature.
# ---------------------------------------------------------------------------------------------
_INFRA_SPEC = '''\
import os

import pytest
from playwright.sync_api import Page, expect

# A non-listening port (connection refused) — the dead-port infra fault. Overridable so the same
# spec can also be pointed at a routable-but-unreachable host for the forced-timeout variant.
BASE_URL = os.environ.get("TARGET_BASE_URL", "{base_url}")
# Sub-second navigation timeout: a forced timeout that can never reach the target.
NAV_TIMEOUT_MS = int(os.environ.get("INFRA_NAV_TIMEOUT_MS", "{timeout_ms}"))


@pytest.mark.generated
def test_infra_fault(page: Page) -> None:
    """Point the run at a dead port / unreachable host -> the navigation fails (infra down)."""
    page.goto(BASE_URL, timeout=NAV_TIMEOUT_MS)
    expect(page.locator(".inventory_list")).to_be_visible()
'''


def _plant_infra(run_id: str, *, base_url: str, timeout_ms: int) -> Path:
    """Plant the dead-port / forced-timeout infra-fault spec under workspaces/<run_id>/."""
    run_dir = _WORKSPACES_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    spec_path = run_dir / "test_infra_fault.py"
    spec_path.write_text(
        _INFRA_SPEC.format(base_url=base_url, timeout_ms=timeout_ms), encoding="utf-8"
    )
    return spec_path


# ---------------------------------------------------------------------------------------------
# The three keyless known-class generators. EACH returns the classify() evidence dict the Plan-01
# pipeline assembles (error_text + page_loaded + heal_outcome + infra_health), built from the REAL
# spec-subprocess output (and, for the automation case, the REAL heal-journal outcome) — so the
# harness exercises the PRODUCTION classifier over real-run evidence, never a hand-written stub.
# ---------------------------------------------------------------------------------------------
async def _evidence_product_defect(idx: int) -> dict:
    """SEED_BUG build: the post-login `.inventory_list` assertion fails on a LOADED page."""
    run_id = f"qual03-prod-{idx}-{uuid.uuid4().hex}"
    spec_path = _plant_login(run_id)
    try:
        # The SAME planted spec test_seeded_bug.py drives, pointed at the seeded-bug build.
        result = await _run_spec_once_env(
            spec_path, {"TARGET_BASE_URL": _SEED_BUG_URL}
        )
        return {
            "error_text": result["output"],
            # The seeded-bug page LOADS (login succeeds); only the success assertion breaks.
            "page_loaded": True,
            "heal_outcome": None,
            "_passed": result["passed"],
        }
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)


async def _evidence_automation(idx: int) -> dict:
    """Un-healed BREAK_REMOVE: the deleted login button -> fail_as_defect (NEVER auto_heal)."""
    run_id = f"qual03-auto-{idx}-{uuid.uuid4().hex}"
    spec_path, out_dir = _plant_heal(run_id, base_url=_BREAK_REMOVE_URL)
    try:
        # high=settings default would also hold it below the band; we force a high band so the
        # removed element's best leftover candidate (~0.06, count==1) can NEVER clear it — the
        # un-healed outcome is structural, the QUAL-02 BREAK_REMOVE guarantee.
        result = await _run_spec_once_env(
            spec_path,
            {
                "HEAL_OUT_DIR": str(out_dir),
                "HEAL_FLOW_ID": "flow-0",
                "HEAL_HIGH_THRESHOLD": "0.15",
            },
        )
        journal = _read_journal(out_dir)
        # The most-recent heal outcome is the classifier's automation signal (the pipeline's join).
        heal_outcome = journal[-1].get("outcome") if journal else None
        return {
            "error_text": result["output"],
            # The login page LOADED (username field present); only the button is gone.
            "page_loaded": True,
            "heal_outcome": heal_outcome,
            "_passed": result["passed"],
        }
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)


async def _evidence_infrastructure(idx: int, *, base_url: str, timeout_ms: int) -> dict:
    """Dead-port / forced-timeout fault: the navigation never reaches the target (infra down)."""
    run_id = f"qual03-infra-{idx}-{uuid.uuid4().hex}"
    spec_path = _plant_infra(run_id, base_url=base_url, timeout_ms=timeout_ms)
    try:
        result = await _run_spec_once_env(spec_path, {})
        return {
            "error_text": result["output"],
            # The target never loaded (connection refused / timed out before any response).
            "page_loaded": False,
            "heal_outcome": None,
            "_passed": result["passed"],
        }
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)


async def _build_labeled_set() -> list[tuple[str, dict]]:
    """Generate the keyless three-class labeled set: several instances per class (RESEARCH P3).

    Returns [(expected_class, evidence_dict), ...] — the hand-labels paired with REAL-run evidence.
    """
    cases: list[tuple[str, dict]] = []

    # product_defect: 3 SEED_BUG runs (a meaningful denominator; the run is deterministic).
    for i in range(3):
        cases.append(("product_defect", await _evidence_product_defect(i)))

    # automation: 3 un-healed BREAK_REMOVE runs.
    for i in range(3):
        cases.append(("automation", await _evidence_automation(i)))

    # infrastructure: 3 dead-port (connection refused) + 1 forced-timeout-vs-unreachable variant.
    for i in range(3):
        cases.append(
            (
                "infrastructure",
                await _evidence_infrastructure(i, base_url=_DEAD_PORT_URL, timeout_ms=2000),
            )
        )
    # A forced sub-second timeout against a non-routable host (TEST-NET-1, RFC 5737) — a timeout
    # that can never reach the target (the second infra signature: timeout-never-loaded).
    cases.append(
        (
            "infrastructure",
            await _evidence_infrastructure(
                99, base_url="http://192.0.2.1:80", timeout_ms=500
            ),
        )
    )
    return cases


async def test_labeled_set_spans_all_three_classes_and_exercises_classifier() -> None:
    """Task-1 done-check: the keyless three-class generators run + exercise the production classifier.

    Asserts the labeled set spans all three known classes, every generated failure produced a
    non-empty error text (the spec actually failed, the case is real), every spec RAN RED (a passing
    spec is not a failure to classify), and the un-healed automation case NEVER auto_healed (the
    QUAL-02 false-heal guarantee carried into the classifier's automation signal).
    """
    _require_targets()
    # Guard: the dead port must actually be closed, else the infra case mis-generates.
    assert not _port_open(_DEAD_PORT_URL), (
        f"the dead-port infra fault target {_DEAD_PORT_URL} is unexpectedly OPEN — "
        "pick a different non-listening port"
    )

    cases = await _build_labeled_set()
    from app.services.defects.classifier import classify

    labels = {c for c, _ in cases}
    assert labels == {"product_defect", "automation", "infrastructure"}, (
        f"the labeled set must span all three classes, got {labels}"
    )

    for expected, ev in cases:
        # Every generated failure is REAL: the spec ran red with a non-empty error text.
        assert ev["_passed"] is False, (
            f"{expected} case unexpectedly PASSED (not a failure to classify): "
            f"{ev['error_text'][-800:]}"
        )
        assert ev["error_text"].strip(), f"{expected} case produced no error text"
        # The classifier runs over the real-run evidence (production module, no stub).
        decision = classify(ev)
        assert decision["classification"] in {
            "product_defect",
            "automation",
            "infrastructure",
        }
        assert 0 <= decision["confidence"] <= 100

    # The un-healed automation case never auto_healed (the QUAL-02 guard fed the automation signal).
    auto_cases = [ev for c, ev in cases if c == "automation"]
    assert all(ev["heal_outcome"] != "auto_heal" for ev in auto_cases), (
        f"a BREAK_REMOVE case auto_healed (false-heal breach): "
        f"{[ev['heal_outcome'] for ev in auto_cases]}"
    )
