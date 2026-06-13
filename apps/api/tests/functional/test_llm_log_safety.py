"""Functional log-safety (PLAT-07, RESEARCH Pitfall 5 + redaction-collision FIX).

A gateway call inside the LIVE api container emits a `llm_usage` structlog event.
This test captures `docker compose logs api` and asserts:
  1. the event logs REAL integer token counts under tokens_in/tokens_out
     (NOT "[REDACTED]" — proving the redaction-collision rename works), and
  2. no prompt/response text and no provider-key material appears in the event.
"""

import json
import os
import re
import subprocess
import uuid
from pathlib import Path

import asyncpg
import pytest

pytestmark = pytest.mark.functional

REPO_ROOT = Path(__file__).resolve().parents[4]

# A distinctive prompt + a sentinel "key" we assert never reach the logs.
_PROMPT_SENTINEL = "PROMPTBODY"
_KEY_SENTINEL = "sk-secretkeyvalue"

_DRIVER = r'''
import asyncio, sys
from app.core.logging import configure_logging
configure_logging()  # same JSON + redaction chain the api uses (PLAT-07)
import app.services.llm_gateway as gw
from app.core.llm_pricing import PRICING

run_id = sys.argv[1]
op = sys.argv[2]
model = "anthropic:" + PRICING[0].model

class _Msg:
    content = "PROMPTBODY-response"
    usage_metadata = {"input_tokens": 4242, "output_tokens": 2121, "total_tokens": 6363}
    response_metadata = {}

class _Chat:
    async def ainvoke(self, messages):
        return _Msg()

gw.init_chat_model = lambda *a, **k: _Chat()

async def main():
    from app.db.session import SessionLocal
    async with SessionLocal() as db:
        await gw.complete(
            db,
            [{"role": "user", "content": "PROMPTBODY secret prompt text"}],
            operation_type=op, run_id=run_id, model=model, max_tokens=256,
        )

asyncio.run(main())
'''


def _host_dsn() -> str:
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "@postgres:", "@localhost:"
    )


def _run_driver(run_id: str, op: str) -> str:
    """Run the gateway inside the live api container; return its emitted log stream.

    The usage event is rendered by the api's own structlog JSON+redaction chain
    (configure_logging is called in-driver), inside the real container runtime —
    so the captured stdout is exactly what the api would write to a log sink.
    No HTTP route exists for the gateway in this slice (Plan 02), so the
    in-container driver is the live-stack equivalent of an api-process emission.
    """
    proc = subprocess.run(
        [
            "docker", "compose",
            "-f", "infra/docker-compose.yml",
            "--env-file", ".env",
            "exec", "-T", "api",
            "uv", "run", "python", "-c", _DRIVER, run_id, op,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert proc.returncode == 0, f"driver failed: {proc.stdout}\n{proc.stderr}"
    return proc.stdout + proc.stderr


@pytest.fixture
async def clean_llm_usage():
    created: list[str] = []
    yield created
    if not created:
        return
    conn = await asyncpg.connect(_host_dsn())
    try:
        await conn.execute("DELETE FROM llm_usage WHERE run_id = ANY($1::text[])", created)
    finally:
        await conn.close()


def _find_usage_event(captured: str, run_id: str) -> dict:
    """The JSON `llm_usage` log line carrying our run_id."""
    for line in captured.splitlines():
        if "llm_usage" not in line or run_id not in line:
            continue
        # docker prefixes lines with "api-1  | "; strip to the JSON object.
        brace = line.find("{")
        if brace == -1:
            continue
        try:
            obj = json.loads(line[brace:])
        except json.JSONDecodeError:
            continue
        if obj.get("event") == "llm_usage" and obj.get("run_id") == run_id:
            return obj
    raise AssertionError(f"no llm_usage event for run_id {run_id} in captured logs")


async def test_usage_event_logs_real_tokens_and_no_leak(clean_llm_usage):
    run_id = f"logsafe-{uuid.uuid4().hex[:12]}"
    op = "test.log_safety"
    clean_llm_usage.append(run_id)

    captured = _run_driver(run_id, op)
    assert captured.strip(), "driver produced no log output"

    event = _find_usage_event(captured, run_id)

    # 1. Real integer token counts under the collision-safe keys (NOT redacted).
    # Keys avoid the substring "token" so the SENSITIVE regex never masks them.
    assert event["tok_in"] == 4242
    assert event["tok_out"] == 2121
    assert event["tok_in"] != "[REDACTED]"
    assert event["tok_out"] != "[REDACTED]"
    # And the raw line shows an integer count, not a redaction marker.
    assert re.search(r'"tok_in":\s*4242', json.dumps(event))
    assert "[REDACTED]" not in json.dumps({"tok_in": event["tok_in"], "tok_out": event["tok_out"]})

    # 2. No prompt/response body and no provider key in the usage event.
    blob = json.dumps(event)
    assert _PROMPT_SENTINEL not in blob, "prompt/response text leaked into usage event"
    assert _KEY_SENTINEL not in blob
    for forbidden in ("messages", "content", "prompt", "response"):
        assert forbidden not in event, f"forbidden key {forbidden!r} in usage event"
