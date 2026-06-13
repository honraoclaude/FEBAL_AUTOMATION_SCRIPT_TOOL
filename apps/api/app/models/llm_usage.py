"""LLM usage ledger model (PLAT-06/PLAT-07, D-09/D-10).

One row per gateway call: who (run_id), what (operation_type), provider/model,
token counts, computed USD cost, and whether it was a cache hit. The COMPUTED
cost is stored (immutable) so future pricing-table edits never rewrite history.

NO prompt/response columns (PLAT-07) — only counts + cost are persisted.
Use Numeric (not Float) for money.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LLMUsage(Base):
    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)  # D-10 per-run grouping
    operation_type: Mapped[str] = mapped_column(String(64), index=True)  # D-10 report grouping
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6))  # COMPUTED, immutable
    cache_hit: Mapped[bool] = mapped_column(Boolean, server_default="false")  # D-12
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
