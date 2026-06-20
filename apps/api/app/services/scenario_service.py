"""Scenario CRUD + status lifecycle for the review queue (GEN-02 / D-01).

Mirrors run_service conventions: a VALID status set + a `_validate_status` guard (T-03-09
analog), select + db.scalar/db.scalars + await db.commit()/refresh() per operation. Status
integrity lives HERE — every transition goes through `set_status` (guarded by VALID); an
edit goes through `update_gherkin` (which keeps the row in `draft` and flips `edited`).

Codegen reads ONLY status=approved (D-01) — `list_approved` filters status=="approved" IN THE
SQL QUERY (never in Python) so the approved-only invariant cannot be bypassed by a caller.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario import Scenario

# The only valid scenario states — the status machine's whole alphabet (D-01).
VALID = {"draft", "approved", "rejected"}


class ScenarioNotFoundError(Exception):
    """Raised when no Scenario exists for an id."""


def _validate_status(status: str) -> str:
    """Guard a status against VALID; return it unchanged or raise ValueError.

    A tiny pure helper (no abstraction) so the guard is unit-testable without a session.
    """
    if status not in VALID:
        raise ValueError(f"invalid status {status!r}; valid: {sorted(VALID)}")
    return status


async def create_scenario(
    db: AsyncSession,
    *,
    run_id: str,
    flow_id: str,
    feature_name: str,
    gherkin_text: str,
    then_refs: list,
) -> Scenario:
    """Insert a draft scenario row (the only entry into the review queue)."""
    scenario = Scenario(
        run_id=run_id,
        flow_id=flow_id,
        feature_name=feature_name,
        gherkin_text=gherkin_text,
        then_refs=then_refs,
        status="draft",
        edited=False,
        stale=False,
    )
    db.add(scenario)
    await db.commit()
    await db.refresh(scenario)
    return scenario


async def get(db: AsyncSession, scenario_id: int) -> Scenario | None:
    return await db.scalar(select(Scenario).where(Scenario.id == scenario_id))


async def list_scenarios(
    db: AsyncSession, *, status: str | None = None
) -> list[Scenario]:
    """List scenarios, optionally filtered by status (defaults to all)."""
    stmt = select(Scenario).order_by(Scenario.id)
    if status is not None:
        stmt = stmt.where(Scenario.status == status)
    return list((await db.scalars(stmt)).all())


async def set_status(db: AsyncSession, scenario_id: int, status: str) -> Scenario:
    """Transition a scenario's status (guarded by VALID). Raises ScenarioNotFoundError."""
    _validate_status(status)
    scenario = await db.scalar(select(Scenario).where(Scenario.id == scenario_id))
    if scenario is None:
        raise ScenarioNotFoundError(scenario_id)
    scenario.status = status
    await db.commit()
    await db.refresh(scenario)
    return scenario


async def update_gherkin(
    db: AsyncSession, scenario_id: int, gherkin_text: str, then_refs: list
) -> Scenario:
    """Save an edit-in-place: replace gherkin_text + then_refs, flip edited, stay draft (D-02).

    The CALLER re-runs the lint + no-vacuous gates BEFORE this write — an edited scenario
    cannot bypass quality. Raises ScenarioNotFoundError when the row is absent.
    """
    scenario = await db.scalar(select(Scenario).where(Scenario.id == scenario_id))
    if scenario is None:
        raise ScenarioNotFoundError(scenario_id)
    scenario.gherkin_text = gherkin_text
    scenario.then_refs = then_refs
    scenario.edited = True
    scenario.status = "draft"
    await db.commit()
    await db.refresh(scenario)
    return scenario


async def list_approved(db: AsyncSession, run_id: str) -> list[Scenario]:
    """Approved scenarios for a run — the ONLY rows codegen reads (D-01).

    Filters status=="approved" IN THE QUERY (not in Python) so the approved-only invariant
    is enforced at the SQL layer.
    """
    stmt = (
        select(Scenario)
        .where(Scenario.run_id == run_id, Scenario.status == "approved")
        .order_by(Scenario.id)
    )
    return list((await db.scalars(stmt)).all())
