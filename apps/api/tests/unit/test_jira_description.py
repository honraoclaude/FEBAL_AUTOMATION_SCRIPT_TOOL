"""Jira description-prose enrichment + deterministic no-key fallback (JIRA-01 / D-01).

describe(...) builds the human-readable description PROSE via the metered gateway
(operation_type "defect.describe", run_id) and, when NO provider key is present (or the
gateway refuses — budget/kill-switch/auth), returns a DETERMINISTIC evidence-summary
fallback plus a `not-enriched` flag so the UI shows the honest "written without an LLM"
caption. The class/confidence DECISION never routes through here — the LLM is prose-only
(D-01). These tests are keyless (no DB, no neo4j, no real provider):

  - with no provider key, describe() returns deterministic prose + enriched=False
    WITHOUT calling the gateway (the keyless short-circuit);
  - the deterministic prose is stable (same evidence -> same prose) and mentions the
    classification + the failing step (a real summary, not a placeholder);
  - when the gateway is monkeypatched to raise (budget/kill-switch/auth), describe()
    falls back to the SAME deterministic prose + enriched=False (never propagates);
  - when the gateway returns content (keyed path, monkeypatched), describe() returns
    that prose + enriched=True.

Run: cd apps/api && uv run python -m pytest tests/unit/test_jira_description.py -q
"""

from __future__ import annotations

from app.services.jira import description as desc

EVIDENCE = {
    "classification": "Product Defect",
    "summary": "Login submit returns 500",
    "flow": "auth-login",
    "step": "Click Submit",
    "expected": "Redirect to /dashboard",
    "actual": "HTTP 500 error page",
}


async def test_no_key_returns_deterministic_fallback_not_enriched(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", None, raising=False)
    monkeypatch.setattr(settings, "openai_api_key", None, raising=False)

    # The gateway must NOT be reached on the keyless path — make it explode if called.
    async def _boom(*a, **k):  # pragma: no cover - asserted not-called
        raise AssertionError("gateway must not be called when no provider key is set")

    monkeypatch.setattr(desc.llm_gateway, "complete", _boom)

    prose, enriched = await desc.describe(db=None, evidence=EVIDENCE, run_id="r1")
    assert enriched is False
    assert isinstance(prose, str) and prose.strip()


async def test_fallback_prose_is_deterministic_and_substantive(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", None, raising=False)
    monkeypatch.setattr(settings, "openai_api_key", None, raising=False)

    p1, e1 = await desc.describe(db=None, evidence=EVIDENCE, run_id="r1")
    p2, e2 = await desc.describe(db=None, evidence=EVIDENCE, run_id="r2")

    assert p1 == p2  # deterministic: same evidence -> same prose (run_id-independent)
    assert e1 is False and e2 is False
    # A real summary, not a placeholder: mentions the class + the failing step.
    assert "Product Defect" in p1
    assert "Click Submit" in p1


async def test_gateway_failure_degrades_to_fallback(monkeypatch) -> None:
    from app.core.config import settings

    # A key is present, so describe() WOULD route to the gateway — but it refuses.
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test", raising=False)

    async def _refuse(*a, **k):
        raise desc.llm_gateway.KillSwitchActive("halt")

    monkeypatch.setattr(desc.llm_gateway, "complete", _refuse)

    prose, enriched = await desc.describe(db=object(), evidence=EVIDENCE, run_id="r1")
    assert enriched is False
    assert "Product Defect" in prose  # the deterministic fallback


async def test_keyed_path_returns_enriched_prose(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test", raising=False)

    class _Result:
        content = "A crisp, LLM-written defect description."

    async def _ok(db, messages, *, operation_type, run_id, **k):
        assert operation_type == "defect.describe"
        assert run_id == "r1"
        return _Result()

    monkeypatch.setattr(desc.llm_gateway, "complete", _ok)

    prose, enriched = await desc.describe(db=object(), evidence=EVIDENCE, run_id="r1")
    assert enriched is True
    assert prose == "A crisp, LLM-written defect description."


def test_description_module_is_the_only_jira_gateway_consumer() -> None:
    # D-01 boundary: description.py is the ONLY jira/ module that touches the gateway;
    # client.py / adf.py / fake.py stay LLM-free.
    from pathlib import Path

    pkg = Path(desc.__file__).resolve().parent
    for name in ("client.py", "adf.py", "fake.py"):
        src = (pkg / name).read_text(encoding="utf-8")
        assert "llm_gateway" not in src, f"{name} must not touch the LLM gateway (D-01)"
