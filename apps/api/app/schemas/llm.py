"""LLM gateway schemas (PLAT-05/PLAT-06).

LLMResult is the gateway's public return shape — content plus a usage echo
(token counts, cost, provider/model, run/operation tags). It is ORM-readable so
it can be built straight from an LLMUsage row when convenient.

KillSwitchRequest is declared here now (single-sourced) for Plan 02's admin
router; the run-budget-override schema belongs to Plan 02 and is NOT added here.
"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LLMResult(BaseModel):
    """Gateway return shape: model content + a redaction-safe usage echo."""

    model_config = ConfigDict(from_attributes=True)

    content: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    cache_hit: bool
    provider: str
    model: str
    run_id: str
    operation_type: str


class KillSwitchRequest(BaseModel):
    """Admin panic-button body (Plan 02 admin router contract, D-05)."""

    reason: str = Field(min_length=1)
