"""Cross-service queue message schemas (D-05) — Pydantic v2, schemas ONLY.

This is the inter-service event contract the in-process tracer path PRODUCES and a
Phase-7 RabbitMQ publisher will later put on the wire — versioned like an API. There
is deliberately NO broker, NO aio-pika, NO queue abstraction here (PITFALLS Pitfall 8 /
D-05): the message shapes exist now; the transport lands in Phase 7 without changing
these contracts.

  - ExploreJob   — the payload POST /explore enqueues; auto-generates a hex run_id.
  - ExecuteJob   — the payload the execute path enqueues (run_id + spec to run).
  - RunStatusEvent — a status transition event keyed by run_id (queued|running|passed|failed).
"""

import uuid

from pydantic import BaseModel, Field


class ExploreJob(BaseModel):
    """Explore work item — a deterministic crawl of `target_id`, traced by `run_id`."""

    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    target_id: int


class ExecuteJob(BaseModel):
    """Execute work item — run the spec at `spec_path` under the threaded `run_id`."""

    run_id: str
    spec_path: str


class RunStatusEvent(BaseModel):
    """A run/execution status transition keyed by run_id (the poll/stream shape)."""

    run_id: str
    kind: str  # "explore" | "execute"
    status: str  # queued | running | passed | failed
    error: str | None = None


class ExploreProgressEvent(BaseModel):
    """A per-step live-progress event the explorer publishes to Redis pub/sub (EXPL-01, D-07).

    Schemas-only (no broker): the explorer publishes `model_dump_json()` to the channel
    `explore:{run_id}`; the SSE endpoint (`GET /api/explore/{run_id}/events`) re-emits it to
    the browser, which renders the Live Exploration View (04-UI-SPEC). Counters are ABSOLUTE
    values (not deltas) so the live view takes the latest event's values directly.

    `cost_usd` is sourced from the LLM gateway's per-run counter — the explorer NEVER computes
    spend (D-06). `screenshot_path` is the run-RELATIVE filename (e.g. "state-3.png"); the
    frontend builds the URL `/api/explore/{run_id}/screenshot/{name}` (M-1). `stop_reason` is
    None while running and a STOP_REASONS value on the terminal event (L-2 maps it to a UI
    state — no terminal value falls through to "no banner").
    """

    run_id: str
    step: int
    pages_found: int
    actions_taken: int
    current_url: str
    current_title: str
    screenshot_path: str | None
    feed_line: str
    cost_usd: float
    elapsed_s: float
    stop_reason: str | None = None


class ExecutionProgressEvent(BaseModel):
    """A per-test live-progress event the worker publishes to Redis pub/sub (EXEC-06, D-06/D-07).

    The execution-plane analogue of ExploreProgressEvent: the worker publishes
    `model_dump_json()` to the channel `exec:{run_id}`; the SSE endpoint
    (`GET /api/executions/{run_id}/events`) re-emits it to the browser, which renders the
    Live Execution View (07-UI-SPEC). The zod `executionProgressEventSchema` in
    `lib/api/executions.ts` mirrors this model 1:1.

    The RUN counters (completed/total/passed/failed/flaky) are ABSOLUTE values (not deltas) so
    the live view takes the latest event's values directly — mirroring the explorer's contract.
    `status` is the RUN status (queued|running|stopping|passed|failed|killed). The per-TEST
    delta describes the single test this event is about: `flow_id` (the kg/flows id), `test_id`
    (the spec/test identifier shown mono), `test_name` (the display name), `test_status` (the
    per-test verdict: queued|running|passed|flaky|product_failure|aborted), `attempt` (the
    1-based attempt count), and `duration_ms` (the resolved test duration, or None while
    in-flight). A snapshot frame (reconnect) carries the current run counters with the per-test
    delta fields null/empty.
    """

    run_id: str
    # Absolute run counters (the live view reads the latest frame directly — never deltas).
    completed: int
    total: int
    passed: int
    failed: int
    flaky: int
    elapsed_s: float
    # The run status (queued | running | stopping | passed | failed | killed).
    status: str
    # The per-test delta this event is about (null/empty on a counters-only snapshot frame).
    flow_id: str | None = None
    test_id: str | None = None
    test_name: str | None = None
    # queued | running | passed | flaky | product_failure | aborted.
    test_status: str | None = None
    attempt: int = 0
    duration_ms: int | None = None


__all__ = [
    "ExploreJob",
    "ExecuteJob",
    "RunStatusEvent",
    "ExploreProgressEvent",
    "ExecutionProgressEvent",
]
