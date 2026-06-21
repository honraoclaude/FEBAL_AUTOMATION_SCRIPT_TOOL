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

Kill flag: the live `run:{run_id}:kill` drain + the "aborted" verdict land in Plan 04 (the real
drain). This slice keeps the no-op hook shape only — NO placeholder kill behavior is added.

SC3: imports ONLY the subprocess primitive, the DB session, the execution-history models,
workspaces, the pure classifier, and the worker progress publish — no LLM/gateway/explorer.
"""

from __future__ import annotations

import time
from pathlib import Path

import structlog

from app.core.workspaces import run_dir, spec_path
from app.db.session import SessionLocal
from app.models.execution_history import TestArtifact, TestResult
from app.services.stability import _run_spec_once
from app.services.worker import progress
from app.services.worker.classifier import classify_retry

log = structlog.get_logger()

# Original attempt + up to 2 retries (D-05). Stop early on a clean exit 0.
MAX_ATTEMPTS = 3


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

    spec = str(spec_path(run_id))
    out_dir = run_dir(run_id, create=True) / flow_id
    out_dir.mkdir(parents=True, exist_ok=True)
    capture_args = _capture_args(out_dir)

    exit_codes: list[int] = []
    started = time.monotonic()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        # Kill-flag hook (no-op in this slice; the live drain + 'aborted' land in Plan 04).
        result = await _run_spec_once(spec, base_url=base_url, extra_args=capture_args)
        exit_code = result["exit_code"] if result["exit_code"] is not None else 1
        exit_codes.append(exit_code)
        if exit_code == 0:
            break  # passed -> stop retrying
    duration_s = time.monotonic() - started

    verdict = classify_retry(exit_codes)  # pure classifier (D-05)
    status = "passed" if verdict["passed"] else "failed"
    artifacts = _discover_artifacts(run_id, out_dir)

    # FRESH session (Pitfall 2): the worker owns its own session, never a request's.
    async with SessionLocal() as db:
        db.add(
            TestResult(
                run_id=run_id,
                flow_id=flow_id,
                verdict=verdict["verdict"],
                attempts=verdict["attempts"],
                exit_codes=exit_codes,
                duration_ms=int(duration_s * 1000),
            )
        )
        for kind, rel_path in artifacts:
            db.add(
                TestArtifact(run_id=run_id, flow_id=flow_id, kind=kind, path=rel_path)
            )
        await db.commit()

    await progress.publish_test_event(
        run_id, flow_id, status=status, attempt=verdict["attempts"], duration_s=duration_s
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
