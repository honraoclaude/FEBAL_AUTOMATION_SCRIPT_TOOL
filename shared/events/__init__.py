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


__all__ = ["ExploreJob", "ExecuteJob", "RunStatusEvent"]
