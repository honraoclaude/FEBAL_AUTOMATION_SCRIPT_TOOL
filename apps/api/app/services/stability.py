"""Stability + seeded-bug acceptance harness (GEN-05 / D-07/D-08, Phase 6 plan 06-04).

The TRUST GATE before a generated spec is "accepted":
  1. N-RUN STABILITY (D-07): run the spec N consecutive times (env STABILITY_RUNS, default 3);
     accept ONLY if ALL N pass. Any non-green run — including a single flake — REJECTS it.
  2. SEEDED-BUG BREAKAGE DETECTION (D-08): re-run the SAME spec once against the seeded-bug
     SauceDemo build (one injected DOM defect — `.inventory_list` renamed; see
     infra/targets/saucedemo/Dockerfile SEED_BUG / the saucedemo-bug compose service). The run
     MUST FAIL. A spec that still passes against a known-broken target is NOT detecting breakage.
  3. ACCEPTANCE = N green vs standard AND red vs the bug build.

CRITICAL invariants (reused VERBATIM from the Phase-3 subprocess runner, execution.run_execution):
  - Pitfall 3 / T-06-19: the generated spec uses the SYNC Playwright API and MUST run only in an
    ISOLATED subprocess (`uv run pytest <spec_path>`) — NEVER an in-process pytest invocation
    (a sync Playwright call inside the running asyncio API process would deadlock/crash, and an
    in-process run is not isolated). There is NO pytest.main / shell=True anywhere here.
  - T-06-18: the subprocess argv is a LIST with no `shell=True`; `spec_path` is run_id-derived
    (`workspaces/<run_id>/...`), never raw user input — so a hostile value cannot inject a command.
  - T-06-23: captured output is tail-capped (_OUTPUT_TAIL_CHARS) per the Phase-3 runner.

OOM SEQUENCING (T-06-20 / Pitfall 4 — the 3GB WSL cap):
  Host 5.7GB / WSL cap 3GB. postgres+redis+api+neo4j+saucedemo already ≈ 2.9GB. Adding
  saucedemo-bug + a Chromium subprocess on top of neo4j risks an OOM kill. The acceptance flow
  is therefore SEQUENCED, NOT concurrent:
    (1) codegen (Slice 3) reads the Element Repository UNDER graph_mode (neo4j up, web stopped)
        and WRITES the spec to workspaces/<run_id>/.
    (2) STOP neo4j, then run run_stability vs saucedemo and run_seeded_bug vs saucedemo-bug —
        the spec is ALREADY written, so running it needs no graph. saucedemo (128m) +
        saucedemo-bug (128m) + Chromium fit comfortably without neo4j.
  The planted-spec deterministic proof needs no neo4j at all (no codegen read). This harness
  NEVER touches neo4j; the sequencing is enforced by the CALLER (and by the functional test,
  which stops neo4j before the run phase).

The full live generate->review->codegen->stabilize chain is Manual-Only (needs provider keys);
the WHOLE harness mechanic is provable deterministically with a PLANTED spec and NO keys
(tests/functional/test_stability.py + test_seeded_bug.py).
"""

import asyncio
import os
from pathlib import Path

import structlog

from app.core.config import settings
from app.services.execution import _run_cwd

log = structlog.get_logger()

# Tail-cap captured output so a noisy spec cannot bloat the trace (Phase-3 runner parity).
_OUTPUT_TAIL_CHARS = 8000

# The env var the GENERATED conftest (templates/conftest.py.j2) reads to override the target
# base URL. The seeded-bug run sets it to SEEDED_BUG_BASE_URL so the SAME spec hits the bug build.
_BASE_URL_ENV = "TARGET_BASE_URL"


async def _run_spec_once(
    spec_path: str,
    *,
    base_url: str | None = None,
    extra_args: list[str] | None = None,
) -> dict:
    """Run the spec ONCE in an isolated subprocess; return {passed, exit_code, output}.

    Reuses the Phase-3 execution.run_execution subprocess shape VERBATIM:
    `uv run pytest <spec_path> -q` as an ISOLATED child (argv LIST, no shell — T-06-18),
    combined stdout/stderr captured + tail-capped. NEVER runs the spec in-process (T-06-19).
    When `base_url` is given it is exported as TARGET_BASE_URL into the child env so the
    generated conftest points the SAME spec at an override target (the seeded-bug build).

    `extra_args` appends trusted, CONSTANT pytest flags to the argv (e.g. the worker's
    pytest-playwright capture flags `--screenshot=on --tracing=on --video=retain-on-failure
    --output <dir>` in Plan 03). They are appended to the SAME argv list (still no shell): the
    caller owns them and they are never raw client input (the worker builds them from constants
    + a run_id-derived output dir — T-07-11).
    """
    env = os.environ.copy()
    if base_url is not None:
        env[_BASE_URL_ENV] = base_url

    argv = ["uv", "run", "pytest", spec_path, "-q", *(extra_args or [])]

    exit_code: int | None = None
    output = ""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=_run_cwd(),
            env=env,
        )
        out, _ = await proc.communicate()
        exit_code = proc.returncode
        output = (out.decode(errors="replace") if out else "")[-_OUTPUT_TAIL_CHARS:]
    except FileNotFoundError as exc:
        # `uv` (the runner binary) is missing — record an honest failure, never crash.
        output = f"stability runner unavailable: {exc}"
        log.error("stability_runner_missing", spec_path=spec_path, error=str(exc))
    except Exception as exc:  # noqa: BLE001 -- any failure is a non-green run, not a crash
        output = f"stability run error: {exc}"
        log.error("stability_run_failed", spec_path=spec_path, error=str(exc))

    return {"passed": exit_code == 0, "exit_code": exit_code, "output": output}


async def run_stability(spec_path: str | Path, *, runs: int | None = None) -> dict:
    """Run the spec N consecutive times; accept iff ALL N pass (D-07).

    N = `runs` else settings.stability_runs (env STABILITY_RUNS, default 3). Each run is a
    FRESH subprocess + a fresh pytest-playwright browser context (full isolation). Accept iff
    EVERY run returns exit 0; any non-green run — including a single flake — rejects.

    Returns {accepted: bool, runs: int, passed_count: int, results: [per-run dicts]}.
    """
    n = settings.stability_runs if runs is None else runs
    spec = str(spec_path)
    results: list[dict] = []
    for i in range(n):
        result = await _run_spec_once(spec)
        results.append(result)
        log.info(
            "stability_run", spec_path=spec, run=i + 1, of=n, passed=result["passed"]
        )
        if not result["passed"]:
            # Fail-fast: a single non-green run already rejects the spec (no point running more).
            break
    passed_count = sum(1 for r in results if r["passed"])
    accepted = passed_count == n
    log.info(
        "stability_complete",
        spec_path=spec,
        runs=n,
        passed_count=passed_count,
        accepted=accepted,
    )
    return {
        "accepted": accepted,
        "runs": n,
        "passed_count": passed_count,
        "results": results,
    }


async def run_seeded_bug(spec_path: str | Path, *, base_url: str | None = None) -> dict:
    """Run the SAME spec once vs the seeded-bug build; it MUST FAIL (D-08).

    The base URL override is exported as TARGET_BASE_URL into the child env (the generated
    conftest reads it), pointing the spec at the seeded-bug build whose renamed
    `.inventory_list` breaks the post-login success assertion. `base_url` else
    settings.seeded_bug_base_url. `detected_breakage` is True iff the run FAILED (exit != 0).

    Returns {detected_breakage: bool, exit_code, output, base_url}.
    """
    bug_url = settings.seeded_bug_base_url if base_url is None else base_url
    if not bug_url:
        raise ValueError(
            "seeded-bug base URL is unset (settings.seeded_bug_base_url / SEEDED_BUG_BASE_URL)"
        )
    result = await _run_spec_once(str(spec_path), base_url=bug_url)
    detected = not result["passed"]
    log.info(
        "seeded_bug_run",
        spec_path=str(spec_path),
        base_url=bug_url,
        detected_breakage=detected,
    )
    return {
        "detected_breakage": detected,
        "exit_code": result["exit_code"],
        "output": result["output"],
        "base_url": bug_url,
    }


async def accept_spec(
    spec_path: str | Path,
    *,
    runs: int | None = None,
    seeded_bug_base_url: str | None = None,
) -> dict:
    """The breakage-detection acceptance: accept iff N-green-vs-std AND red-vs-bug (D-07+D-08).

    1. run_stability(spec) — must be all-green over N runs.
    2. run_seeded_bug(spec) — must FAIL vs the bug build (detected_breakage).
    accepted = stability.accepted AND seeded_bug.detected_breakage. Both halves are required:
    a spec that flakes is not stable, and a spec that passes vs a known-broken target is not
    detecting breakage.

    Returns {accepted, stability, seeded_bug}.
    """
    stability = await run_stability(spec_path, runs=runs)
    seeded_bug = await run_seeded_bug(spec_path, base_url=seeded_bug_base_url)
    accepted = bool(stability["accepted"] and seeded_bug["detected_breakage"])
    log.info(
        "accept_spec",
        spec_path=str(spec_path),
        accepted=accepted,
        stable=stability["accepted"],
        detected_breakage=seeded_bug["detected_breakage"],
    )
    return {"accepted": accepted, "stability": stability, "seeded_bug": seeded_bug}
