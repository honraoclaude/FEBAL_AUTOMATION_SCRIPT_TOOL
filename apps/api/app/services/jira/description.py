"""Jira description-PROSE enrichment via the metered gateway + no-key fallback (D-01).

`describe(...)` produces ONLY the human-readable description prose. It routes through
`llm_gateway.complete(operation_type="defect.describe", run_id)` (NEVER a direct provider
SDK call — D-07) and returns:

    (prose, enriched)

where `enriched` is True only when the LLM actually wrote the prose. When NO provider key
is configured — or the gateway refuses (budget / kill-switch / auth / transient) — it
returns a DETERMINISTIC evidence-summary fallback with `enriched=False`, so the UI can
render the honest "written without an LLM" caption (the generation.py / gateway no-key
fallback precedent). The path is keyless-safe.

D-01 boundary: this is the ONLY jira/ module that touches the gateway. The class +
confidence DECISION is deterministic and NEVER routes through the LLM — the LLM here is
prose-only. client.py / adf.py / fake.py stay LLM-free (enforced by a test).
"""

from __future__ import annotations

import structlog

from app.core.config import settings
from app.services import llm_gateway

log = structlog.get_logger()

_SYSTEM = (
    "You are a QA engineer writing the prose summary of an automated-test defect for a "
    "Jira ticket. Write 2-4 plain sentences describing what failed and the likely impact. "
    "Do not invent details beyond the evidence. Output prose only — no markdown, no lists."
)

# Conservative cap — the prose is a few sentences, not a document.
_MAX_TOKENS = 400


def _has_provider_key() -> bool:
    """True when at least one provider key is configured (the keyless short-circuit gate)."""
    return bool(settings.anthropic_api_key or settings.openai_api_key)


def _fallback_prose(evidence: dict) -> str:
    """Deterministic evidence-summary prose (no LLM) — stable for the same evidence.

    A real summary (classification + flow + failing step + expected/actual), NOT a
    placeholder. Same evidence -> identical prose (run_id-independent), so it is
    reproducible and diff-stable.
    """
    cls = evidence.get("classification", "Unclassified")
    summary = evidence.get("summary", "")
    flow = evidence.get("flow", "")
    step = evidence.get("step", "")
    expected = evidence.get("expected", "")
    actual = evidence.get("actual", "")

    parts = [
        f"Classified as {cls}.",
    ]
    if summary:
        parts.append(f"{summary}.")
    if flow or step:
        where = " at step '" + step + "'" if step else ""
        flow_txt = f"flow '{flow}'" if flow else "the flow"
        parts.append(f"The failure occurred in {flow_txt}{where}.")
    if expected or actual:
        parts.append(f"Expected {expected or 'the flow to succeed'}; observed {actual or 'a failure'}.")
    parts.append("(Description written without an LLM — no provider key configured.)")
    return " ".join(parts)


def _build_messages(evidence: dict) -> list[dict]:
    """The system+user messages for the gateway (untrusted evidence is fenced)."""
    lines = "\n".join(f"{k}: {v}" for k, v in evidence.items())
    user = (
        "<<<UNTRUSTED_EVIDENCE>>>\n"
        f"{lines}\n"
        "<<<END_UNTRUSTED_EVIDENCE>>>\n"
        "Write the defect description prose."
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]


async def describe(*, db, evidence: dict, run_id: str) -> tuple[str, bool]:
    """Return (prose, enriched) for a defect's Jira description.

    Keyless short-circuit: with no provider key, return the deterministic fallback +
    enriched=False WITHOUT calling the gateway. With a key, route ONE metered gateway
    call (operation_type "defect.describe", run_id); on refusal (budget/kill-switch) OR
    any broad provider/transient error (the empty-key auth path), degrade to the SAME
    deterministic fallback. A non-empty gateway reply yields enriched=True.
    """
    if not _has_provider_key():
        return _fallback_prose(evidence), False

    try:
        result = await llm_gateway.complete(
            db,
            _build_messages(evidence),
            operation_type="defect.describe",
            run_id=run_id,
            temperature=0,
            max_tokens=_MAX_TOKENS,
        )
    except (llm_gateway.BudgetExceeded, llm_gateway.KillSwitchActive) as exc:
        log.info("defect_describe_fallback", run_id=run_id, reason=str(exc))
        return _fallback_prose(evidence), False
    except Exception as exc:  # noqa: BLE001 -- no-key/provider/transient -> deterministic fallback
        log.info("defect_describe_fallback_error", run_id=run_id, error=str(exc))
        return _fallback_prose(evidence), False

    prose = (getattr(result, "content", None) or "").strip()
    if not prose:
        return _fallback_prose(evidence), False
    return prose, True
