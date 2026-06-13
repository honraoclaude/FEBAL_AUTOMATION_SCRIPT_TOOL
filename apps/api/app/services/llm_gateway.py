"""LLM gateway — the single money-control surface every agent call routes through
(PLAT-05/PLAT-06).

This slice implements the call + cost-accounting path: a provider-agnostic
complete() that routes through init_chat_model, reads usage uniformly across
providers, computes USD cost from the effective-dated pricing table, writes one
durable llm_usage ledger row, and emits a redaction-safe structlog usage event.

Budget pre-check (Plan 02) and the Redis response cache (Plan 03) layer on top
later — their seams are named here (no_cache, cache_hit) but NOT yet enforced.

REDACTION COLLISION (PATTERNS flag #2): core/logging.py's SENSITIVE regex matches
the substring "token", so log keys input_tokens/output_tokens would render
[REDACTED]. The usage event therefore logs counts under tokens_in/tokens_out
(regex-safe). The DB columns stay input_tokens/output_tokens — columns are not
log keys. The SENSITIVE regex is left UNCHANGED so real credentials still redact.

PLAT-07: prompts/responses and provider keys NEVER enter the ledger or a log event.
"""

import os
import uuid

import structlog
from langchain.chat_models import init_chat_model
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.llm_pricing import compute_cost, lookup_price
from app.models.llm_usage import LLMUsage
from app.schemas.llm import LLMResult

log = structlog.get_logger()


class TransientProviderError(Exception):
    """A retryable provider failure (429/529/transient network) — drives tenacity."""


class MissingUsageMetadataError(Exception):
    """Provider returned no usage_metadata — fail closed (Pitfall 3), never cost $0."""


# Env-gated LangSmith passthrough (D-discretion). No code cost when off.
if settings.langsmith_tracing:
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    if settings.langsmith_api_key:
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)


def _provider_of(model_str: str) -> str:
    """Provider name from a provider-prefixed model string ("anthropic:..." -> "anthropic")."""
    provider, sep, _ = model_str.partition(":")
    return provider if sep else ""


@retry(
    retry=retry_if_exception_type(TransientProviderError),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def _invoke(model_str: str, messages, *, temperature: float, max_tokens: int):
    """Single provider round-trip, retried on TransientProviderError only."""
    chat = init_chat_model(model_str, temperature=temperature, max_tokens=max_tokens)
    return await chat.ainvoke(messages)


async def complete(
    db: AsyncSession,
    messages,
    *,
    operation_type: str,
    run_id: str | None = None,
    model: str | None = None,
    temperature: float = 0,
    max_tokens: int,
    no_cache: bool = False,
) -> LLMResult:
    """Route one metered LLM call: provider-agnostic invoke -> cost -> ledger -> usage event.

    `model` may be a provider-prefixed string (the form init_chat_model consumes);
    when omitted, settings.llm_default_model is used (D-13). A run_id is generated
    when the caller supplies none (D-10). Fails closed when usage_metadata is
    absent or the model is unpriced — never records $0.

    `no_cache` is accepted now as a forward seam (Plan 03 cache); this slice does
    not yet consult a cache, so every call is a live, non-cached call.
    """
    run_id = run_id or uuid.uuid4().hex
    model_str = model or settings.llm_default_model
    provider = _provider_of(model_str)

    resp = await _invoke(
        model_str, messages, temperature=temperature, max_tokens=max_tokens
    )

    um = getattr(resp, "usage_metadata", None)
    if not um or um.get("input_tokens") is None or um.get("output_tokens") is None:
        # Cannot cost ⇒ refuse; never silently log $0 (Pitfall 3).
        raise MissingUsageMetadataError(operation_type)
    input_tokens = int(um["input_tokens"])
    output_tokens = int(um["output_tokens"])

    # Pass the FULL provider-prefixed model_str; lookup_price normalizes via
    # _bare_model. UnknownModelPriceError propagates (fail-closed) BEFORE any row.
    price = lookup_price(model_str)
    cost_usd = compute_cost(price, input_tokens, output_tokens)

    row = LLMUsage(
        run_id=run_id,
        operation_type=operation_type,
        provider=provider,
        model=model_str,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        cache_hit=False,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # Redaction-safe usage event. The SENSITIVE regex matches the SUBSTRING
    # "token", so any key containing it — input_tokens, output_tokens, AND even
    # tokens_in/tokens_out — would render [REDACTED]. We therefore log the counts
    # under tok_in/tok_out, which contain no forbidden substring, so real integers
    # survive. The SENSITIVE regex stays UNCHANGED (real credentials still redact);
    # the DB columns keep their input_tokens/output_tokens names (columns != log keys).
    # NO messages/prompt/response or provider key ever enters the event.
    log.info(
        "llm_usage",
        operation_type=operation_type,
        run_id=run_id,
        provider=provider,
        model=model_str,
        tok_in=input_tokens,
        tok_out=output_tokens,
        cost_usd=str(cost_usd),
        cache_hit=False,
    )

    content = getattr(resp, "content", None)
    return LLMResult(
        content=content if isinstance(content, str) else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        cache_hit=False,
        provider=provider,
        model=model_str,
        run_id=run_id,
        operation_type=operation_type,
    )
