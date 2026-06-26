"""Per-element heal stats (HEAL-04) — success-rate + false-heal-rate over heal_audit.

Aggregates the `heal_audit` ledger (Plan 03) by element_key into the two HEAL-04 rates, mirroring
the Phase-7 execution-history aggregation style (exec_history.py: SQLAlchemy 2.0 select/func +
group_by — no raw SQL, no string-built queries, T-08-19/V5):

  - heal_success_rate = count(landed heals) / count(all heal attempts)
      A "landed" heal is outcome IN (auto_heal, applied) that an operator did NOT later reject
      (reviewed_outcome != 'rejected') — a rejected heal is a FALSE heal, never a success. Counted
      over every attempt logged for the element.
  - false_heal_rate  = count(rejected-after-a-heal) / count(auto_heal)
      A "false heal" is a heal an operator REJECTED via the Plan-05 review API (which flips
      reviewed_outcome = 'rejected', RESEARCH Pattern 5). The denominator is the auto_heal count
      (the heals that ran unattended — the population a false heal can hide in). When an element
      has zero auto_heal attempts the false_heal_rate is 0.0 (no auto-heals to be false).

Elements with ZERO heal attempts never appear (no divide-by-zero — RESEARCH Pattern 5 guard).
An optional element_key narrows the result to a single element.

NO LLM / graph / broker — a pure DB read over one Postgres table (SC3 stays green).
"""

from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.heal_audit import HealAudit

# The outcomes that count as a landed heal (numerator of heal_success_rate).
_HEALED_OUTCOMES = ("auto_heal", "applied")


async def per_element_heal_stats(
    db: AsyncSession, *, element_key: str | None = None
) -> list[dict]:
    """Aggregate heal_audit by element_key into {element_key, attempts, success/false rates}.

    One SELECT with conditional SUMs (case()/func.sum — parameterized via the ORM, never
    string-built SQL) grouped by element_key:

      - attempts            = count(*)                              (all heal rows for the element)
      - healed              = count(outcome IN (auto_heal, applied) AND not rejected)
      - auto_heals          = count(outcome == 'auto_heal')
      - rejected_heals      = count(reviewed_outcome == 'rejected') (the false-heal signal)

    heal_success_rate = healed / attempts; false_heal_rate = rejected_heals / auto_heals (0.0 when
    there were no auto_heals). An element with zero attempts is impossible here (group_by over
    existing rows only) — there is no divide-by-zero. Optional element_key filters to one element;
    rows are returned element_key-ordered (a stable, testable order).
    """
    attempts = func.count(HealAudit.id).label("attempts")
    # A landed heal is a healed outcome the operator did NOT later reject — a rejected heal is a
    # FALSE heal, never a success (reviewed_outcome != 'rejected', NULL-safe via is_distinct_from).
    healed = func.sum(
        case(
            (
                HealAudit.outcome.in_(_HEALED_OUTCOMES)
                & HealAudit.reviewed_outcome.is_distinct_from("rejected"),
                1,
            ),
            else_=0,
        )
    ).label("healed")
    auto_heals = func.sum(
        case((HealAudit.outcome == "auto_heal", 1), else_=0)
    ).label("auto_heals")
    rejected_heals = func.sum(
        case((HealAudit.reviewed_outcome == "rejected", 1), else_=0)
    ).label("rejected_heals")

    stmt = (
        select(HealAudit.element_key, attempts, healed, auto_heals, rejected_heals)
        .group_by(HealAudit.element_key)
        .order_by(HealAudit.element_key)
    )
    if element_key is not None:
        stmt = stmt.where(HealAudit.element_key == element_key)

    rows = (await db.execute(stmt)).all()

    out: list[dict] = []
    for key, n_attempts, n_healed, n_auto, n_rejected in rows:
        n_attempts = int(n_attempts or 0)
        if n_attempts == 0:
            continue  # belt-and-suspenders: group_by never yields a zero-attempt group
        n_healed = int(n_healed or 0)
        n_auto = int(n_auto or 0)
        n_rejected = int(n_rejected or 0)
        out.append(
            {
                "element_key": key,
                "attempts": n_attempts,
                "heal_success_rate": n_healed / n_attempts,
                "false_heal_rate": (n_rejected / n_auto) if n_auto else 0.0,
            }
        )
    return out
