"""Dashboard aggregation reads (DASH-01/02/03) — on-read composition over Phase-4..9 data.

The exec_history.py discipline VERBATIM: module-level `async def fn(db: AsyncSession)` returning
plain dicts, SQLAlchemy 2.0 select/scalars/func, no raw SQL, no ORM lazy loads, no LLM, no broker.
Every number renders from the server payload (no fabrication) so the UI is server-authoritative.

  - executive(db, *, driver=None): coverage (reuse coverage_dash) + the pass-rate trend
    (exec_history.pass_rate_trend) + a defects-filed-per-day trend + KPI scalars
    (latest pass rate as a PERCENT, open defect count).
  - qa(db): the run history (exec_history.list_runs) + the failed-tests list (verdict IN
    product_failure | aborted) with RUN-RELATIVE TestArtifact refs (kind + stored path; NEVER an
    absolute fs path — the auth-gated URL is built client-side per the Phase-7 contract).
  - developer(db): root-cause groupings (Classification by classification + fingerprint, count
    desc) + an errors-per-day trend + a module breakdown (failure count per flow_id, desc).

CHECKER LOW-1: the verdict vocabulary is passed | flaky | product_failure | aborted — there is NO
'failed' verdict. Failed tests = verdict IN (product_failure, aborted).

CHECKER LOW-2: exec_history.pass_rate_trend returns pass_rate as 0..1. The executive KPI converts
the latest day's pass_rate to a PERCENT (×100) — `kpis.pass_rate_percent` is the 0..100 number the
UI meter renders, so the displayed % and the meter's 0-100 scale agree (the conversion lives HERE,
once, not ambiguously on the client).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.defects import Classification, Defect
from app.models.execution_history import TestArtifact, TestResult
from app.services import coverage_dash, exec_history

# The verdicts that count as a FAILED test (CHECKER LOW-1: there is no 'failed' verdict).
_FAILED_VERDICTS = ("product_failure", "aborted")


async def executive(db: AsyncSession, *, driver=None) -> dict:
    """DASH-01: coverage + pass-rate trend + defects-filed trend + KPIs (pass-rate %, open defects)."""
    coverage = await coverage_dash.coverage(db, driver=driver)
    pass_rate_trend = await exec_history.pass_rate_trend(db)
    defects_trend = await _defects_filed_trend(db)

    # KPI: the latest day's pass rate, converted from 0..1 to a 0..100 PERCENT (LOW-2). 0.0 when
    # there is no run history yet (honest, not fabricated).
    latest_pass_rate = pass_rate_trend[-1]["pass_rate"] if pass_rate_trend else 0.0
    pass_rate_percent = round(latest_pass_rate * 100.0, 1)

    # KPI: "open defects" = Defect rows not rejected (draft + applied are still live work).
    open_defects = int(
        await db.scalar(select(func.count(Defect.id)).where(Defect.status != "rejected")) or 0
    )

    return {
        "coverage": coverage,
        "pass_rate_trend": pass_rate_trend,
        "defects_trend": defects_trend,
        "kpis": {
            "pass_rate_percent": pass_rate_percent,
            "open_defects": open_defects,
        },
    }


async def _defects_filed_trend(db: AsyncSession) -> list[dict]:
    """Per-day count of Defect rows filed, oldest day first (the pass_rate_trend date_trunc idiom)."""
    day = func.date_trunc("day", Defect.created_at).label("day")
    cnt = func.count(Defect.id).label("count")
    rows = (await db.execute(select(day, cnt).group_by(day).order_by(day))).all()
    return [
        {"day": d.date().isoformat() if d is not None else None, "count": int(c)}
        for d, c in rows
    ]


async def qa(db: AsyncSession) -> dict:
    """DASH-02: run history (list_runs) + failed tests + RUN-RELATIVE artifact refs."""
    runs = await exec_history.list_runs(db)

    # Failed tests: every TestResult with a failing verdict, newest first.
    failed_rows = (
        await db.scalars(
            select(TestResult)
            .where(TestResult.verdict.in_(_FAILED_VERDICTS))
            .order_by(TestResult.created_at.desc(), TestResult.id.desc())
        )
    ).all()

    failed_tests: list[dict] = []
    for r in failed_rows:
        # The RUN-RELATIVE artifact refs for this (run, flow) — kind + stored path ONLY. The path
        # is the run-relative string AS STORED; the auth-gated URL is built client-side (Phase-7
        # containment guard owns serving). NEVER an absolute fs path (T-10-09).
        art_rows = (
            await db.scalars(
                select(TestArtifact)
                .where(TestArtifact.run_id == r.run_id, TestArtifact.flow_id == r.flow_id)
                .order_by(TestArtifact.id)
            )
        ).all()
        failed_tests.append(
            {
                "run_id": r.run_id,
                "flow_id": r.flow_id,
                "verdict": r.verdict,
                "attempts": r.attempts,
                "error_text": r.error_text,
                "artifacts": [{"kind": a.kind, "path": a.path} for a in art_rows],
            }
        )

    return {
        "runs": runs,
        "failed_tests": failed_tests,
    }


async def developer(db: AsyncSession) -> dict:
    """DASH-03: root-cause groupings + errors-per-day trend + module failure breakdown."""
    root_cause_groups = await _root_cause_groups(db)
    errors_trend = await _errors_trend(db)
    module_breakdown = await _module_breakdown(db)
    return {
        "root_cause_groups": root_cause_groups,
        "errors_trend": errors_trend,
        "module_breakdown": module_breakdown,
    }


async def _root_cause_groups(db: AsyncSession) -> list[dict]:
    """Group Classification by (classification, fingerprint-via-Defect)... actually by the class +
    a representative fingerprint, count desc (the flaky_leaderboard group-by-count idiom).

    Classification has no fingerprint column (that lives on Defect); group by the class + flow_id
    pairing that the Defect fingerprint keys, joining Defect for the fingerprint + a representative
    defect id. We group on (classification, fingerprint) over the Defect rows (which carry both),
    which is the dedup-keyed root-cause grouping the Dev dashboard renders.
    """
    cnt = func.count(Defect.id).label("count")
    rep_id = func.min(Defect.id).label("rep_defect_id")
    rows = (
        await db.execute(
            select(Defect.classification, Defect.fingerprint, cnt, rep_id)
            .group_by(Defect.classification, Defect.fingerprint)
            .order_by(cnt.desc(), Defect.fingerprint)
        )
    ).all()
    return [
        {
            "classification": cls,
            "fingerprint": fp,
            "count": int(c),
            "rep_defect_id": int(rid),
        }
        for cls, fp, c, rid in rows
    ]


async def _errors_trend(db: AsyncSession) -> list[dict]:
    """Per-day count of Classification rows (errors classified), oldest day first."""
    day = func.date_trunc("day", Classification.created_at).label("day")
    cnt = func.count(Classification.id).label("count")
    rows = (await db.execute(select(day, cnt).group_by(day).order_by(day))).all()
    return [
        {"day": d.date().isoformat() if d is not None else None, "count": int(c)}
        for d, c in rows
    ]


async def _module_breakdown(db: AsyncSession) -> list[dict]:
    """Failure count per flow_id (the "module"), count desc (the group-by-count idiom).

    A failure = a TestResult with a failing verdict (product_failure | aborted). Flows with no
    failures do not appear.
    """
    cnt = func.count(TestResult.id).label("failure_count")
    rows = (
        await db.execute(
            select(TestResult.flow_id, cnt)
            .where(TestResult.verdict.in_(_FAILED_VERDICTS))
            .group_by(TestResult.flow_id)
            .order_by(cnt.desc(), TestResult.flow_id)
        )
    ).all()
    return [{"flow_id": fid, "failure_count": int(c)} for fid, c in rows]
