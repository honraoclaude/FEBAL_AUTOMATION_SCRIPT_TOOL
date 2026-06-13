"""Wave-0 mocked unit-test scaffold (02-VALIDATION).

This suite INVERTS the Phase-1 live-only philosophy: it mocks init_chat_model
so gateway logic is exercised with NO provider and NO spend. Redis isolation
uses the already-running compose Redis under a unique test key prefix (no
fakeredis package gate).
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# tests/unit/ is two levels below tests/ -> parents[3] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPO_ROOT / ".env", override=False)


class FakeAIMessage:
    """Minimal stand-in for langchain's AIMessage: .content + .usage_metadata."""

    def __init__(self, content="ok", usage_metadata=None, response_metadata=None):
        self.content = content
        # None means "provider returned no usage" — exercises the fail-closed path.
        self.usage_metadata = usage_metadata
        self.response_metadata = response_metadata or {}


class FakeChatModel:
    """Stand-in for an init_chat_model(...) instance; .ainvoke returns a FakeAIMessage."""

    def __init__(self, response: FakeAIMessage):
        self._response = response

    async def ainvoke(self, messages):  # noqa: ARG002 -- messages unused by the fake
        return self._response


@pytest.fixture
def fake_chat_model(monkeypatch):
    """Patch the gateway's init_chat_model import site.

    Returns a small controller. Call `.set(content=..., usage_metadata=...)` to
    shape the next response; the patched init_chat_model ignores model/params and
    returns a FakeChatModel wrapping that response. Records the model_str the
    gateway passed via `.calls`.
    """

    state = {
        "response": FakeAIMessage(
            content="ok",
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )
    }

    class Controller:
        calls: list[dict] = []

        def set(self, *, content="ok", usage_metadata=None, response_metadata=None):
            state["response"] = FakeAIMessage(
                content=content,
                usage_metadata=usage_metadata,
                response_metadata=response_metadata,
            )

    controller = Controller()
    controller.calls = []

    def _fake_init_chat_model(model_str, **kwargs):
        controller.calls.append({"model_str": model_str, "kwargs": kwargs})
        return FakeChatModel(state["response"])

    import app.services.llm_gateway as gateway

    monkeypatch.setattr(gateway, "init_chat_model", _fake_init_chat_model)
    return controller


@pytest.fixture(autouse=True)
async def _isolate_gateway_redis():
    """Isolate every unit test's gateway Redis use (cross-loop safety + no real counters).

    The gateway calls get_redis() on every complete() (kill-switch check, budget
    counters). Two hazards this fixes for the whole unit suite:

    1. Cross-loop reuse: app.core.redis_client._client is a module-level singleton.
       pytest-asyncio (asyncio_mode=auto) runs each test on a FRESH event loop, so a
       client opened in one test and reused in the next raises "Event loop is closed".
       Reset the singleton before AND after each test so each test opens its own client.
    2. Real-counter pollution: tests that don't patch get_redis (e.g. Plan-01
       test_gateway_provider) would otherwise read/write the REAL "llm:" keys on the dev
       Redis, eventually tripping the real daily kill-switch. Point _KEY_PREFIX at the
       "test:llm:" namespace (the prefix the redis_test/patch_redis fixtures already flush).
    """
    import app.core.redis_client as rc
    import app.services.llm_gateway as gateway

    rc._client = None  # discard any client bound to a previous test's (closed) loop
    gateway._KEY_PREFIX = "test:llm:"
    try:
        yield
    finally:
        if rc._client is not None:
            await rc._client.aclose()  # close on the still-live test loop
            rc._client = None
        gateway._KEY_PREFIX = "llm:"


@pytest.fixture
async def redis_test():
    """A redis.asyncio client on the compose Redis, namespaced + flushed per test.

    Uses the test key prefix "test:llm:" so it never clobbers dev counters.
    Host-side: rewrite the in-cluster redis host to localhost.
    """
    import redis.asyncio as aioredis

    url = os.environ["REDIS_URL"].replace("@redis:", "@localhost:").replace(
        "//redis:", "//localhost:"
    )
    # decode_responses=True mirrors the production redis_client (app/core/redis_client.py)
    # so GET/MGET return str — the gateway parses counters/kill-reason as text, not bytes.
    client = aioredis.from_url(url, decode_responses=True)
    prefix = "test:llm:"

    async def _flush_prefix():
        async for key in client.scan_iter(match=f"{prefix}*"):
            await client.delete(key)

    await _flush_prefix()
    try:
        yield client
    finally:
        await _flush_prefix()
        await client.aclose()
