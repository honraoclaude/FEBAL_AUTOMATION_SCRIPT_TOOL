"""Heal review/stats API schemas (HEAL-03 review surface + HEAL-04 stats).

The quarantine review API (D-05, Plan 05) serves the before/after diff straight off the
`heal_audit` row, and the per-element heal stats off the aggregation service. Two response
shapes, mirroring schemas/execution.py's ORM-readable Pydantic v2 style:

  - HealAuditResponse — one `heal_audit` row, ORM-readable (from_attributes=True): the BEFORE
    chain, the AFTER chain (nullable — a fail_as_defect has no after), the blended confidence,
    the locator outcome + the apply/reject review outcome, and the live match count. The
    before/after diff the review surface renders is THIS record (D-05 / HEAL-03).
  - HealStatsResponse — one element's aggregated rates (HEAL-04): the attempt count, the
    heal-success rate, and the false-heal rate. Plain BaseModel (built from the aggregation
    service's dicts, not an ORM row).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HealAuditResponse(BaseModel):
    """One heal_audit row — the before/after diff + confidence the review surface renders."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    element_key: str
    run_id: str
    flow_id: str
    before_chain: list
    # Nullable: a fail_as_defect produced no healed chain (SQL NULL, not JSON 'null').
    after_chain: list | None
    confidence: float
    # auto_heal | quarantine | fail_as_defect | applied | rejected
    outcome: str
    live_match_count: int
    # Set by apply/reject (the false-heal signal for HEAL-04); NULL until reviewed.
    reviewed_outcome: str | None
    created_at: datetime


class HealStatsResponse(BaseModel):
    """One element's aggregated heal rates (HEAL-04) — per-element success + false-heal."""

    element_key: str
    attempts: int
    heal_success_rate: float
    false_heal_rate: float
