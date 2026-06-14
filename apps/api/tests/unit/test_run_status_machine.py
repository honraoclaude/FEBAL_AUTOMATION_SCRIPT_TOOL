"""Unit tests for the run-status machine + shared/events schemas (03-02 Task 1).

Pure logic — NO DB, NO provider. Two surfaces are covered here:

  1. run_service's VALID status set + the guard run_service raises against an
     out-of-set status (the only status-integrity mechanism — T-03-09). The guard
     is exposed as a tiny pure helper so it can be asserted without a session.
  2. shared/events Pydantic v2 message schemas (D-05 — schemas only, no broker):
     ExploreJob auto-generates a hex run_id; ExecuteJob/RunStatusEvent carry the
     run_id threaded through the slice.

The DB-touching service methods (create_run/set_status row writes,
get_status_by_run_id resolution) are exercised by the graph-marked functional
test in Task 3 against the live stack.
"""

import pytest

from app.services import run_service
from shared.events import ExecuteJob, ExploreJob, RunStatusEvent


def test_valid_status_set_is_exactly_the_four_states():
    assert run_service.VALID == {"queued", "running", "passed", "failed"}


@pytest.mark.parametrize("status", ["queued", "running", "passed", "failed"])
def test_validate_status_accepts_every_valid_state(status):
    # _validate_status returns the status unchanged for a valid value (no raise).
    assert run_service._validate_status(status) == status


@pytest.mark.parametrize("bad", ["", "done", "RUNNING", "pass", "error", "complete"])
def test_validate_status_rejects_out_of_set_value(bad):
    with pytest.raises(ValueError):
        run_service._validate_status(bad)


def test_run_not_found_error_is_a_typed_exception():
    assert issubclass(run_service.RunNotFoundError, Exception)


def test_explore_job_autogenerates_nonempty_hex_run_id():
    job = ExploreJob(target_id=1)
    assert isinstance(job.run_id, str) and job.run_id
    # uuid4().hex is 32 lowercase hex chars
    int(job.run_id, 16)  # raises ValueError if not hex
    assert job.target_id == 1


def test_two_explore_jobs_get_distinct_run_ids():
    assert ExploreJob(target_id=1).run_id != ExploreJob(target_id=1).run_id


def test_execute_job_carries_run_id_and_spec_path():
    job = ExecuteJob(run_id="abc123", spec_path="workspaces/abc123/test_x.py")
    assert job.run_id == "abc123"
    assert job.spec_path == "workspaces/abc123/test_x.py"


def test_run_status_event_carries_kind_status_and_optional_error():
    ev = RunStatusEvent(run_id="r1", kind="explore", status="failed", error="boom")
    assert ev.run_id == "r1"
    assert ev.kind == "explore"
    assert ev.status == "failed"
    assert ev.error == "boom"
    # error defaults to None
    assert RunStatusEvent(run_id="r2", kind="execute", status="queued").error is None


def test_shared_events_has_no_broker_import():
    # D-05: schemas ONLY — the module must not IMPORT aio-pika or any broker client.
    # Inspect actual import lines (prose mentions of the package name are fine).
    import shared.events as events

    src = events.__file__
    with open(src, encoding="utf-8") as fh:
        import_lines = [
            ln.strip()
            for ln in fh
            if ln.lstrip().startswith(("import ", "from "))
        ]
    joined = "\n".join(import_lines)
    for broker in ("aio_pika", "pika", "aiormq", "kombu", "celery"):
        assert broker not in joined, f"unexpected broker import {broker!r}: {import_lines}"
