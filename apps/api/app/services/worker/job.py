"""Per-flow job runner (EXEC-03/04/05) — subprocess + 2x retry loop + per-step capture.

A job message is `{run_id, flow_id}` (+ an optional base_url override for the determinism
proof). run_flow_job runs ONE flow's spec up to MAX_ATTEMPTS=3 (original + 2 retries, D-05),
stopping early on a clean exit 0 — reusing the Phase-6 stability._run_spec_once subprocess
shape VERBATIM (argv LIST, no shell — T-03-15/T-07-01, cwd=_run_cwd(), output tail-cap,
FileNotFoundError -> honest failure), now with the pytest-playwright capture flags appended.

PER-STEP ARTIFACT CAPTURE (D-04, RESEARCH Pattern 4): every attempt runs with
`--screenshot=on` (always), `--tracing=on` (always — the trace carries console + network per
W4 (a), so there are NO separate console_log/network_log files), `--video=retain-on-failure`
(video only on failure), and `--output <out_dir>`. pytest-playwright writes its per-test
SUBDIRECTORIES under <out_dir>, which is `run_dir(run_id)/<flow_id>/` — the concrete on-disk
layout (B2). After the loop the runner walks <out_dir> for captured files and records ONE
TestArtifact per file with a RUN-RELATIVE path that PRESERVES the subdir segments (e.g.
"<flow_id>/<test-slug>/trace.zip") — never a bare basename, never an absolute path, never a
binary blob in Postgres (T-07-11/T-07-12).

FLAKY CLASSIFICATION (D-05): the per-attempt exit codes feed the PURE classifier
(classifier.classify_retry): passed-on-a-retry -> flaky(infra); all-attempts-fail -> product.
The worker records ONE TestResult with the verdict, the attempt count, and the exit_codes JSON
list in a FRESH SessionLocal (Pitfall 2, mirroring execution.run_execution's finish).

spec_path is run_id-DERIVED via workspaces.spec_path(run_id) and the output dir is
run_dir(run_id)/<flow_id> (run_id-derived, flow_id from the trusted job message) — NEVER taken
raw from the message body (T-07-01/T-07-11 carry-forward of T-03-15).

Kill flag (D-07, Plan 04): BEFORE pulling/running each attempt the worker reads
`run:{run_id}:kill` from the SHARED Redis client. If the flag is set, the flow is DRAINED — the
runner publishes an `aborted` per-test event, records an `aborted` TestResult (NOT
product_failure — the test never ran to a product verdict), and returns WITHOUT pulling new
work. The in-flight subprocess (if one already started) is allowed to finish — there is NO
forceful process termination anywhere (cooperative cancel only), so no orphaned Chromium is left.

SC3: imports ONLY the subprocess primitive, the DB session, the execution-history models,
workspaces, the pure classifier, the worker progress publish, and the shared Redis client — no
LLM/gateway/explorer.
"""

from __future__ import annotations

import time
from pathlib import Path

import structlog

from app.core.redis_client import get_redis
from app.core.workspaces import run_dir, spec_path
from app.db.session import SessionLocal
from app.models.execution_history import TestArtifact, TestResult
from app.services.healing.ingest import ingest_heal_journal
from app.services.stability import _run_spec_once
from app.services.worker import progress
from app.services.worker.classifier import classify_retry, reconcile_verdict

log = structlog.get_logger()

# Original attempt + up to 2 retries (D-05). Stop early on a clean exit 0.
MAX_ATTEMPTS = 3

# The generated Playwright project subtree name (codegen.project._TARGET) — pages/ lives under
# run_dir(run_id)/<TARGET>/pages/. Kept in sync with codegen; the heal ingest rewrites under it.
_TARGET = "target"


def _kill_flag_key(run_id: str) -> str:
    """The cooperative kill flag the worker checks between tests (D-07)."""
    return f"run:{run_id}:kill"


async def _is_killed(run_id: str) -> bool:
    """True iff the run's cooperative kill flag is set (D-07 — checked between tests).

    Reads the SHARED lifespan get_redis() client (never a second client). A set flag means the
    run is being drained: the worker pulls no new work and remaining flows resolve to `aborted`.
    """
    return bool(await get_redis().get(_kill_flag_key(run_id)))


def _capture_args(out_dir: Path) -> list[str]:
    """The pytest-playwright artifact CLI flags (D-04) appended to the subprocess argv.

    screenshot + trace ALWAYS; video ONLY on failure. The trace (--tracing=on) carries the
    console + network logs (W4 (a)) — there are NO separate console/network files. --output
    points pytest-playwright at the per-flow dir so it writes per-test subdirectories under it.
    """
    return [
        "--screenshot=on",  # on -> ALWAYS (D-04)
        "--tracing=on",  # on -> ALWAYS; trace = console + network (W4 (a))
        "--video=retain-on-failure",  # video on FAILURE only (D-04)
        "--output",
        str(out_dir),
    ]


def _kind_for(name: str) -> str | None:
    """Infer the TestArtifact kind from a captured file's name (screenshot|trace|video ONLY).

    Per W4 (a) there are NO console_log/network_log kinds (they live inside the trace). A file
    that matches none of the three known kinds returns None and is NOT recorded.
    """
    lower = name.lower()
    if lower.endswith(".png"):
        return "screenshot"
    if lower.startswith("trace") and lower.endswith(".zip"):
        return "trace"
    if lower.endswith(".webm"):
        return "video"
    return None


def _discover_artifacts(run_id: str, out_dir: Path) -> list[tuple[str, str]]:
    """Walk the per-flow output dir; return (kind, run-relative-path) for each known file.

    Each path is RELATIVE to run_dir(run_id) so it preserves the `<flow_id>/<subdir...>/<name>`
    segments (POSIX separators) — the exact string the Plan-04 artifact route resolves. A bare
    basename or an absolute path is NEVER recorded. Files of an unknown kind are skipped.
    """
    base = run_dir(run_id)
    artifacts: list[tuple[str, str]] = []
    if not out_dir.exists():
        return artifacts
    for path in sorted(out_dir.rglob("*")):
        if not path.is_file():
            continue
        kind = _kind_for(path.name)
        if kind is None:
            continue
        rel = path.relative_to(base).as_posix()
        artifacts.append((kind, rel))
    return artifacts


async def run_flow_job(job: dict) -> dict:
    """Run one flow's spec with the 2x retry loop + per-step capture; record result + artifacts.

    Resolves the spec from the message's run_id (run_id-derived, never a raw body path) and the
    per-flow output dir from run_dir(run_id)/<flow_id>. Runs up to MAX_ATTEMPTS, breaking on a
    clean exit 0, collecting per-attempt exit codes; classifies the verdict via the PURE
    classifier; records ONE TestResult + one TestArtifact per captured file (run-relative paths,
    inferred kinds) in a FRESH SessionLocal; publishes a per-test event. Returns the verdict dict.
    """
    run_id = job["run_id"]
    flow_id = job["flow_id"]
    base_url = job.get("base_url")  # optional override (the determinism proof points the spec)

    # D-07 DRAIN: if the run's kill flag is already set, this flow is aborted BEFORE any
    # subprocess starts — pull no new work, record an `aborted` verdict (never product_failure),
    # publish an `aborted` per-test event. No forceful termination (cooperative cancel only).
    if await _is_killed(run_id):
        return await _abort_flow(run_id, flow_id)

    spec = str(spec_path(run_id))
    out_dir = run_dir(run_id, create=True) / flow_id
    out_dir.mkdir(parents=True, exist_ok=True)
    capture_args = _capture_args(out_dir)

    exit_codes: list[int] = []
    last_output: str | None = None  # the last attempt's tail-capped output (Pitfall 1, 09-01)
    started = time.monotonic()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Cooperative kill check BETWEEN attempts (D-07): a kill set mid-retry stops further
        # attempts. If no attempt has run yet, drain to `aborted`; otherwise classify what ran.
        if attempt > 1 and await _is_killed(run_id):
            break
        result = await _run_spec_once(spec, base_url=base_url, extra_args=capture_args)
        exit_code = result["exit_code"] if result["exit_code"] is not None else 1
        exit_codes.append(exit_code)
        # Hold the LAST attempt's tail-capped output as the error text the Phase-9 classifier
        # reads (Pitfall 1, plan 09-01). `result` survives the loop, so the final iteration's
        # output is what persists — no new import (the no-llm-in-worker gate stays green).
        last_output = result.get("output")
        if exit_code == 0:
            break  # passed -> stop retrying
    duration_s = time.monotonic() - started
    duration_ms = int(duration_s * 1000)

    base_verdict = classify_retry(exit_codes)  # pure exit-code classifier (D-05)
    artifacts = _discover_artifacts(run_id, out_dir)

    # FRESH session (Pitfall 2): the worker owns its own session, never a request's. The heal
    # ingest's HealAudit rows + the TestResult ride the SAME session + commit (Pitfall 2).
    async with SessionLocal() as db:
        # HEAL-AS-COMMIT (D-03, HEAL-03): ingest the per-flow heal-journal post-subprocess —
        # one HealAudit row per entry + a page-object rewrite for auto_heal + a best-effort KG
        # write-back. project_root holds pages/ (run_dir/<target>); journal_dir is the per-flow
        # out_dir the in-spec layer wrote to. Both run_id-derived, never journal-supplied (T-08-12).
        # The KG write-back is best-effort INSIDE ingest (a down neo4j never crashes the worker,
        # T-08-14); the audit rows + rewrite persist regardless.
        journal_outcomes = await ingest_heal_journal(
            db,
            run_id,
            flow_id,
            project_root=run_dir(run_id) / _TARGET,
            journal_dir=out_dir,
        )
        # Reconcile the exit-code verdict with the journal: a journal'd auto_heal -> auto_healed
        # (a heal is NOT a flake, Pitfall 4); quarantine -> quarantined; fail_as_defect ->
        # product_failure. No heal events -> the exit verdict is unchanged.
        journal_events = [{"outcome": o} for o in journal_outcomes]
        verdict = dict(base_verdict)
        verdict["verdict"] = reconcile_verdict(base_verdict["verdict"], journal_events)

        db.add(
            TestResult(
                run_id=run_id,
                flow_id=flow_id,
                verdict=verdict["verdict"],
                attempts=verdict["attempts"],
                exit_codes=exit_codes,
                error_text=last_output,
                duration_ms=duration_ms,
            )
        )
        for kind, rel_path in artifacts:
            db.add(
                TestArtifact(run_id=run_id, flow_id=flow_id, kind=kind, path=rel_path)
            )
        await db.commit()
        # Publish the per-test event with the verdict + the CURRENT absolute run counters,
        # built from the test_run row + the test_results aggregate this session just wrote.
        await progress.publish_test_event(
            db,
            run_id,
            flow_id=flow_id,
            test_status=verdict["verdict"],
            attempt=verdict["attempts"],
            duration_ms=duration_ms,
            elapsed_s=duration_s,
        )
    log.info(
        "run_flow_job_finished",
        run_id=run_id,
        flow_id=flow_id,
        verdict=verdict["verdict"],
        attempts=verdict["attempts"],
        exit_codes=exit_codes,
        artifacts=len(artifacts),
    )
    return verdict


async def _abort_flow(run_id: str, flow_id: str) -> dict:
    """Drain a flow killed before it ran: record an `aborted` TestResult + publish the event.

    D-07: a flow drained by the kill switch never ran to a product verdict, so its verdict is
    `aborted` (distinct from `product_failure`). Writes ONE TestResult (attempts=0, no exit
    codes, no duration) in a FRESH session and publishes an `aborted` per-test event with the
    current absolute run counters. NO subprocess is started — there is nothing to force-terminate.
    """
    verdict = {"verdict": "aborted", "attempts": 0, "passed": False, "exit_codes": []}
    async with SessionLocal() as db:
        db.add(
            TestResult(
                run_id=run_id,
                flow_id=flow_id,
                verdict="aborted",
                attempts=0,
                exit_codes=[],
                duration_ms=None,
            )
        )
        await db.commit()
        await progress.publish_test_event(
            db,
            run_id,
            flow_id=flow_id,
            test_status="aborted",
            attempt=0,
            duration_ms=None,
        )
    log.info("run_flow_job_aborted", run_id=run_id, flow_id=flow_id)
    return verdict
