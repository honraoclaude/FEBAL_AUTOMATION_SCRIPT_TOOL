"""Two-provider LIVE parity test (PLAT-05, Success Criterion 1, RESEARCH Pitfall 6).

Proves the gateway's SAME complete() call runs against BOTH Anthropic and OpenAI with
only the model-config string changed — the core provider-agnosticism promise of
init_chat_model (CLAUDE.md "Agent / LLM Layer"). usage_metadata is read uniformly across
providers (Pattern 1), so both yield positive input/output token counts and a non-zero
computed cost.

GATING (Pitfall 6, T-02-16): marked `live_llm` (off the default `-m "not live_llm"`
gate) and `skipif` on missing ANTHROPIC_API_KEY/OPENAI_API_KEY — it makes REAL (small)
provider calls with REAL spend, so it never runs in CI by default and SKIPS cleanly when
keys are absent. Run on demand: `cd apps/api && uv run pytest -m live_llm -q`.

BUDGET MECHANISM (plan FIX 4): the Plan-02 pre-check would refuse these calls if a low
demo USD/token cap were configured. The `raised_budgets` fixture monkeypatches generous
caps ($5/call, far above two sub-cent completions) and the test uses a UNIQUE run_id so
the per-run counter starts clean. The test also asserts the configured daily USD cap
exceeds the summed cost of the two parity calls, so a low cap can never silently turn the
parity proof into a BudgetExceeded refusal. Real spend is two tiny completions (< $0.01).
"""

import os
import uuid
from decimal import Decimal

import pytest

import app.services.llm_gateway as gateway
from app.core.config import settings
from app.core.llm_pricing import PRICING

pytestmark = pytest.mark.live_llm

# Concrete model ids read from the pricing table so the test stays in sync with the
# priced models (D-08/D-13). PRICING[0] is the anthropic row, PRICING[1] the openai row.
_ANTHROPIC_MODEL = f"anthropic:{PRICING[0].model}"
_OPENAI_MODEL = f"openai:{PRICING[1].model}"

_PARITY_MODELS = [_ANTHROPIC_MODEL, _OPENAI_MODEL]

_KEYS_PRESENT = bool(
    os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("OPENAI_API_KEY")
)


class _CaptureSession:
    """Stand-in AsyncSession: records ledger rows; commit/refresh are no-ops.

    The parity proof reads cost/usage from complete()'s RETURN value, so a real
    Postgres connection is unnecessary here (keeps the test focused on provider parity).
    """

    def __init__(self):
        self.added: list = []

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        return None

    async def refresh(self, row):
        return None


@pytest.fixture
def raised_budgets(monkeypatch):
    """Raise USD + token caps far above two small completions so the Plan-02 pre-check
    never refuses the parity calls (FIX 4). Returns the effective daily USD cap so the
    test can assert it exceeds the summed parity cost. Teardown is automatic via
    monkeypatch (Pitfall 8 discipline)."""
    daily_usd_cap = 5.0
    monkeypatch.setattr(settings, "llm_per_call_usd_cap", 5.0)
    monkeypatch.setattr(settings, "llm_run_usd_cap", 5.0)
    monkeypatch.setattr(settings, "llm_daily_usd_cap", daily_usd_cap)
    monkeypatch.setattr(settings, "llm_per_call_token_cap", 10_000_000)
    monkeypatch.setattr(settings, "llm_run_token_cap", 10_000_000)
    monkeypatch.setattr(settings, "llm_daily_token_cap", 100_000_000)
    return Decimal(str(daily_usd_cap))


@pytest.mark.skipif(
    not _KEYS_PRESENT,
    reason="live provider keys absent (ANTHROPIC_API_KEY + OPENAI_API_KEY)",
)
async def test_two_provider_parity(raised_budgets):
    """The SAME gateway call runs on Anthropic AND OpenAI by config alone; both return a
    non-empty response, positive integer input/output tokens read uniformly from
    usage_metadata, and a non-zero computed cost (Success Criterion 1, PLAT-05)."""
    messages = [{"role": "user", "content": "Reply with the single word: parity"}]
    results = {}

    for model_str in _PARITY_MODELS:
        result = await gateway.complete(
            _CaptureSession(),
            messages,
            operation_type="test.parity",
            run_id=uuid.uuid4().hex,  # unique per call -> clean per-run counter
            model=model_str,
            temperature=0,
            max_tokens=16,
            no_cache=True,  # exercise the real provider on BOTH, never a cache hit
        )
        results[model_str] = result

        # Uniform usage_metadata read: positive integer token counts on every provider.
        assert isinstance(result.input_tokens, int) and result.input_tokens > 0, model_str
        assert isinstance(result.output_tokens, int) and result.output_tokens > 0, model_str
        # Non-empty response content.
        assert result.content, f"empty response from {model_str}"
        # Non-zero computed cost (priced model, real tokens).
        assert result.cost_usd > Decimal("0"), model_str
        # Provider resolved from the config string alone.
        assert result.provider == model_str.split(":", 1)[0]

    # Both providers answered the SAME call shape — provider-agnosticism proven.
    assert set(results) == set(_PARITY_MODELS)

    # The configured daily USD cap comfortably exceeds the summed parity spend, so a low
    # demo cap can never silently turn the parity proof into a BudgetExceeded refusal.
    summed_cost = sum((r.cost_usd for r in results.values()), Decimal("0"))
    assert raised_budgets > summed_cost, (
        f"daily USD cap {raised_budgets} must exceed summed parity cost {summed_cost}"
    )
