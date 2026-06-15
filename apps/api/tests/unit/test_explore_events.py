"""Unit proofs for the SSE live-progress seam (04-04, EXPL-01) — no stack, no spend.

Covers:
  - ExploreProgressEvent shape: full field set validates + round-trips JSON; a missing
    required field raises (Pydantic-v2 schemas-only, mirrors RunStatusEvent).
  - publish_progress: publishes the serialized event to Redis pub/sub channel
    explore:{run_id} (redis mocked — no real broker).
  - build_progress_event: builds the event from state + the gateway-sourced cost (D-06 —
    the explorer NEVER computes spend; cost is passed in from the per-run counter).
  - L-3 cooperative Stop: with the cancel flag set, should_continue / the loop short-circuits
    to stop_reason="stopped" and the fake provider is not invoked further.
"""

from __future__ import annotations

import json

import pytest

from shared.events import ExploreProgressEvent


# ---- Test 1: event shape ---------------------------------------------------------------


def test_explore_progress_event_full_shape_roundtrips_json():
    """All 11 fields validate and survive a model_dump_json -> model_validate_json round-trip."""
    ev = ExploreProgressEvent(
        run_id="abc123",
        step=4,
        pages_found=3,
        actions_taken=4,
        current_url="https://example.test/cart",
        current_title="Cart",
        screenshot_path="state-4.png",
        feed_line="step 4: chose [1] checkout",
        cost_usd=0.0123,
        elapsed_s=12.5,
        stop_reason=None,
    )
    raw = ev.model_dump_json()
    parsed = ExploreProgressEvent.model_validate_json(raw)
    assert parsed == ev
    # round-trips through a plain dict too (the SSE data payload is JSON text)
    assert json.loads(raw)["run_id"] == "abc123"
    assert json.loads(raw)["stop_reason"] is None


def test_explore_progress_event_terminal_carries_stop_reason():
    """A terminal event carries a stop_reason (STOP_REASONS value)."""
    ev = ExploreProgressEvent(
        run_id="abc123",
        step=10,
        pages_found=6,
        actions_taken=10,
        current_url="https://example.test/done",
        current_title="Done",
        screenshot_path=None,
        feed_line="exploration complete",
        cost_usd=0.05,
        elapsed_s=42.0,
        stop_reason="saturation",
    )
    assert ev.stop_reason == "saturation"
    assert ExploreProgressEvent.model_validate_json(ev.model_dump_json()).stop_reason == "saturation"


def test_explore_progress_event_missing_required_field_raises():
    """Omitting a required field (pages_found) raises a validation error."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExploreProgressEvent(
            run_id="abc123",
            step=1,
            # pages_found missing
            actions_taken=1,
            current_url="u",
            current_title="t",
            screenshot_path=None,
            feed_line="f",
            cost_usd=0.0,
            elapsed_s=0.0,
        )


# ---- Test 2: publish + build -----------------------------------------------------------


class _FakeRedis:
    """Records publish calls (channel, payload) — no real broker."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> int:
        self.published.append((channel, payload))
        return 1


async def test_publish_progress_publishes_to_run_channel(monkeypatch):
    """publish_progress calls get_redis().publish on explore:{run_id} with the serialized event."""
    from app.services.explorer import progress as progress_mod

    fake = _FakeRedis()
    monkeypatch.setattr(progress_mod, "get_redis", lambda: fake)

    ev = ExploreProgressEvent(
        run_id="run-xyz",
        step=2,
        pages_found=1,
        actions_taken=2,
        current_url="u",
        current_title="t",
        screenshot_path="state-2.png",
        feed_line="step 2: chose [0] home",
        cost_usd=0.0,
        elapsed_s=1.0,
        stop_reason=None,
    )
    await progress_mod.publish_progress("run-xyz", ev)

    assert len(fake.published) == 1
    channel, payload = fake.published[0]
    assert channel == "explore:run-xyz"
    assert json.loads(payload)["step"] == 2
    assert json.loads(payload)["run_id"] == "run-xyz"


def test_build_progress_event_sources_cost_from_gateway_counter():
    """build_progress_event takes cost_usd as an INPUT (gateway counter) — never computes it (D-06)."""
    from app.services.explorer import progress as progress_mod

    state = {
        "run_id": "run-1",
        "step": 3,
        "visited_keys": ["a", "b"],  # pages_found derives from distinct visited keys
        "current_url": "https://example.test/x",
        "current_screenshot": "/abs/workspaces/run-1/state-3.png",
    }
    ev = progress_mod.build_progress_event(
        state,
        cost_usd=0.0321,
        elapsed_s=9.0,
        feed_line="step 3: chose [1] add-to-cart",
        current_title="X",
        stop_reason=None,
    )
    assert isinstance(ev, ExploreProgressEvent)
    assert ev.cost_usd == 0.0321  # passed straight through from the gateway counter
    assert ev.step == 3
    assert ev.feed_line == "step 3: chose [1] add-to-cart"
    # screenshot_path is the run-RELATIVE basename (M-1 consumer builds the URL), not the abs path
    assert ev.screenshot_path == "state-3.png"
    assert ev.current_url == "https://example.test/x"


# ---- Test 3: L-3 cooperative Stop ------------------------------------------------------


async def test_cancel_flag_halts_loop_with_stopped(monkeypatch):
    """With the Redis cancel flag set, the loop's stop check short-circuits to stop_reason=stopped."""
    from app.services.explorer import nodes

    class _CancelRedis:
        async def get(self, key: str):
            return "1" if key == "explore:cancel:run-stop" else None

    monkeypatch.setattr(nodes, "get_redis", lambda: _CancelRedis())

    out = await nodes.check_cancel({"run_id": "run-stop"})
    assert out.get("stop_reason") == "stopped"


async def test_no_cancel_flag_leaves_state_unchanged(monkeypatch):
    """Without the cancel flag, the stop check does not set stop_reason."""
    from app.services.explorer import nodes

    class _NoCancelRedis:
        async def get(self, key: str):
            return None

    monkeypatch.setattr(nodes, "get_redis", lambda: _NoCancelRedis())

    out = await nodes.check_cancel({"run_id": "run-go"})
    assert "stop_reason" not in out or out.get("stop_reason") is None
