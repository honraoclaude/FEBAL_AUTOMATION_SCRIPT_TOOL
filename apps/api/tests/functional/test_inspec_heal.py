"""Keyless in-spec heal proof against a live mutated page (HEAL-01 / HEAL-02, THE CRUX).

Plants a minimal generated project — the rendered in-spec `_healing.py` + a page object whose
top-priority chain entry points at a STALE data-test the live SauceDemo page does NOT have — and
runs it via stability._run_spec_once against the live SauceDemo target. Two cases prove the crux:

  1. BENIGN RENAME (auto_heal): the broken top tier (`data-test="username-STALE"`, live count 0)
     drifted, but the live username input still matches uniquely on its lower tiers / signals
     (DOM type+placeholder, bounding-box, prior history). _resolve -> heal finds it, the HARD live
     re-validation confirms live_match_count == 1, the heal CONTINUES the test, and the journal
     records ONE auto_heal entry with live_match_count == 1 and a non-empty after_chain.
  2. REMOVED ELEMENT (fail_as_defect): the broken chain points at an element absent across ALL
     tiers — no candidate re-validates to a unique live match (live_match_count == 0). The
     uniqueness gate FORBIDS a heal regardless of score; _resolve -> heal raises HealFailed so the
     spec FAILS, and the journal records fail_as_defect with live_match_count == 0 (NEVER auto_heal).

KEYLESS + neo4j OFF (RESEARCH Pitfall 6 / A7): the chains/history are vendored into the page
object's _chains/_element_meta at plant time, NOT read from the graph during this run phase, so no
provider keys and no neo4j are touched. The full LIVE end-to-end heal during a real LLM-generated
suite (keys + the full codegen path) stays Manual-Only (08-VALIDATION Manual-Only).

The bands are config-tunable (HEAL_HIGH_THRESHOLD env, exactly like stability_runs): the benign
case sets a threshold the unique match clears so the MECHANIC (unique -> auto_heal; zero -> fail)
is what is proven, independent of the default tuning the mutation harness sets later. The
uniqueness gate (live count == 1) is the structural guarantee under any threshold.

Target reached at 127.0.0.1 (NOT localhost): on Windows/WSL `localhost` resolves to ::1 first and
the IPv6 port-forward is wedged for this nginx (IPv4-only) — the Phase-1 saucedemo decision note.
Subprocess discipline: stability._run_spec_once (argv list, no shell, isolated) — never in-process.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, select_autoescape

pytestmark = [pytest.mark.functional]

# 127.0.0.1 (not localhost) — IPv4-only nginx; localhost->::1 is wedged on Windows/WSL.
SAUCEDEMO_HOST_URL = "http://127.0.0.1:8080"

# Repo root: tests/functional/test_inspec_heal.py -> functional -> tests -> api -> apps -> root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_WORKSPACES_ROOT = _REPO_ROOT / "workspaces"
_TEMPLATES_DIR = _REPO_ROOT / "apps" / "api" / "app" / "templates"

# A HIGH band the unique benign match clears (~0.33: history 1.0 + DOM tag/attr Jaccard), well
# above the next-best candidate (~0.06) — proving the unique-match -> auto_heal mechanic with a
# wide margin. The removed-element case fails the uniqueness gate (count 0) under ANY threshold,
# so this value never lets a non-unique match heal. (Bands are config-tunable, like stability_runs;
# the default 0.85 is the harness-tuned production value — this proof asserts the MECHANIC.)
_BENIGN_HIGH = "0.30"


def _jinja() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(enabled_extensions=(), default=False),
        keep_trailing_newline=True,
    )
    # The page object renders _chains / _element_meta via the pyrepr filter (Python literal, not
    # JSON) — register the same filter codegen/project.py registers so the planted page object
    # renders identically to the real codegen path.
    env.filters["pyrepr"] = repr
    return env


def _render_healing() -> str:
    return _jinja().get_template("healing/_healing.py.j2").render()


def _render_page_object(*, locators: dict, chains: dict, meta: dict) -> str:
    return _jinja().get_template("pages/page_object.py.j2").render(
        class_name="LoginPage",
        page_url=SAUCEDEMO_HOST_URL,
        locators=locators,
        element_chains=chains,
        element_meta=meta,
    )


# The planted spec: import the page object, navigate to the live target, resolve the (stale-top)
# element through the heal-aware accessor, and click it. _resolve writes the heal-journal to
# HEAL_OUT_DIR (the spec's KNOWN per-flow dir) and either continues (auto_heal) or raises
# HealFailed (fail). The spec inserts its own dir on sys.path so `from _healing import heal`
# inside _resolve resolves to the vendored module planted alongside it.
_SPEC = '''\
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from playwright.sync_api import sync_playwright  # noqa: E402

from login_page import LoginPage  # noqa: E402

BASE_URL = os.environ.get("TARGET_BASE_URL", "{base_url}")


def test_inspec_heal():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("#user-name", timeout=15000)
            login = LoginPage(page)
            # _resolve uses the STALE top chain entry; on the miss it heals against the live DOM.
            loc = login._resolve("{element_key}")
            loc.click()
        finally:
            browser.close()
'''


def _plant(run_id: str, *, element_key: str, chain: list, meta: dict) -> tuple[Path, Path]:
    """Plant _healing.py + login_page.py + the spec under workspaces/<run_id>/. Returns
    (spec_path, out_dir)."""
    run_dir = _WORKSPACES_ROOT / run_id
    out_dir = run_dir / "flow-0"
    out_dir.mkdir(parents=True, exist_ok=True)

    # The page object: a single attr whose TOP locator is the STALE data-test (live miss).
    locators = {element_key: '[data-test="username-STALE"]'}
    chains = {element_key: chain}
    (run_dir / "_healing.py").write_text(_render_healing(), encoding="utf-8")
    (run_dir / "login_page.py").write_text(
        _render_page_object(locators=locators, chains=chains, meta=meta), encoding="utf-8"
    )
    spec_path = run_dir / "test_inspec_heal_planted.py"
    spec_path.write_text(
        _SPEC.format(base_url=SAUCEDEMO_HOST_URL, element_key=element_key),
        encoding="utf-8",
    )
    return spec_path, out_dir


def _read_journal(out_dir: Path) -> list:
    journal = out_dir / "heal-journal.json"
    if not journal.exists():
        return []
    return json.loads(journal.read_text(encoding="utf-8"))


async def test_benign_rename_auto_heals_to_unique_live_match() -> None:
    """A benign top-tier drift heals to the unique live username -> spec passes, journal auto_heal.

    The live username input still matches the broken element on DOM (type+placeholder), visual
    (bounding box), and history (a prior data-test=username snapshot) — it is the unique best
    candidate and re-validates to live_match_count == 1, so the heal continues the test.
    """
    run_id = f"heal-benign-{uuid.uuid4().hex}"
    chain = [{"strategy": "data-testid", "value": "username-STALE"}]
    meta = {
        "username_field": {
            # Broken-element signals the scorer compares live candidates against. tag drives the
            # element-specific enumeration (<input>); type+placeholder match the live username
            # strongly; history's top matches the live data-test=username.
            "attrs": {"tag": "input", "type": "text", "placeholder": "Username"},
            "bbox": None,  # heal reads the live bbox; broken bbox unknown -> visual via size only
            "history": [
                {"step": 0, "chain": [{"strategy": "data-testid", "value": "username"}]}
            ],
        }
    }
    spec_path, out_dir = _plant(run_id, element_key="username_field", chain=chain, meta=meta)
    extra_env = {"HEAL_OUT_DIR": str(out_dir), "HEAL_FLOW_ID": "flow-0",
                 "HEAL_HIGH_THRESHOLD": _BENIGN_HIGH}
    try:
        result = await _run_spec_once_env(spec_path, extra_env)
        journal = _read_journal(out_dir)
        assert result["passed"] is True, (
            f"benign-rename spec did not pass (heal did not continue): {result['output']}"
        )
        auto = [e for e in journal if e.get("outcome") == "auto_heal"]
        assert len(auto) == 1, f"expected exactly one auto_heal entry, got {journal}"
        entry = auto[0]
        assert entry["live_match_count"] == 1, f"auto_heal not on a unique match: {entry}"
        assert entry["after_chain"], f"auto_heal after_chain is empty: {entry}"
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)


async def test_removed_element_fails_as_defect_zero_match() -> None:
    """A removed element (absent across ALL tiers) never auto-heals -> spec fails, journal fail.

    No candidate re-validates to a unique live match (live_match_count == 0). The uniqueness gate
    forbids a heal regardless of score, so _resolve raises HealFailed and the spec FAILS — the
    structural false-heal guard (QUAL-02). The journal records fail_as_defect, NEVER auto_heal.
    """
    run_id = f"heal-removed-{uuid.uuid4().hex}"
    # The broken chain + tag point at an element absent across EVERY enumeration tier on the
    # SauceDemo login page: tag <dialog> (none present), role=switch (none), and an absent text.
    # Element-specific enumeration finds NO candidate -> the best selector re-validates to 0.
    chain = [
        {"strategy": "data-testid", "value": "ghost-element-STALE"},
        {"strategy": "role", "value": "switch"},
        {"strategy": "text", "value": "Totally Absent Control Xyz"},
    ]
    meta = {
        "ghost_field": {
            "attrs": {"tag": "dialog", "type": "range", "placeholder": "Absent Xyz"},
            "bbox": None,
            "history": [],
        }
    }
    spec_path, out_dir = _plant(run_id, element_key="ghost_field", chain=chain, meta=meta)
    # Even at high=0.0 a zero-match can never heal (the structural uniqueness gate, count != 1).
    extra_env = {"HEAL_OUT_DIR": str(out_dir), "HEAL_FLOW_ID": "flow-0",
                 "HEAL_HIGH_THRESHOLD": "0.0"}
    try:
        result = await _run_spec_once_env(spec_path, extra_env)
        journal = _read_journal(out_dir)
        assert result["passed"] is False, (
            f"removed-element spec wrongly passed (false heal?): {result['output']}"
        )
        assert journal, f"expected a heal-journal entry for the removed element: {out_dir}"
        assert not any(e.get("outcome") == "auto_heal" for e in journal), (
            f"a removed element must NEVER auto_heal (uniqueness gate breach): {journal}"
        )
        fail = [e for e in journal if e.get("outcome") == "fail_as_defect"]
        assert fail, f"expected a fail_as_defect entry, got {journal}"
        assert fail[0]["live_match_count"] == 0, (
            f"removed element must have live_match_count == 0: {fail[0]}"
        )
    finally:
        shutil.rmtree(_WORKSPACES_ROOT / run_id, ignore_errors=True)


async def _run_spec_once_env(spec_path: Path, extra_env: dict) -> dict:
    """Run the planted spec once with extra env vars exported into the child (HEAL_* knobs).

    Reuses stability._run_spec_once's isolated-subprocess discipline; the heal knobs are exported
    via os.environ for the child (the same mechanism the worker uses to point the spec at its
    per-flow out_dir). Restores os.environ afterward so tests don't leak knobs into each other.
    """
    import os

    from app.services.stability import _run_spec_once

    saved = {k: os.environ.get(k) for k in extra_env}
    os.environ.update(extra_env)
    try:
        return await _run_spec_once(str(spec_path))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
