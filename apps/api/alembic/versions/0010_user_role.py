"""users.role column for RBAC (PLAT-04 / D-01)

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-28 19:00:00.000000

The RBAC foundation (Phase 10, plan 10-01):

  - `users.role` (String(16), server_default='admin', NOT NULL): the four-role vocabulary
    `admin | qa_lead | qa_engineer | developer` (10-RESEARCH A2; mirrors the project's
    String(16) status/class-vocab convention — scenario.status, defects.classification).
    The `role` lives on the row (NOT in the JWT) so `require_role` reads it off the User row
    each request — a role change takes effect on the next request, no token reissue, no
    stale-role window (D-01 / A1).

server_default='admin' is the load-bearing choice (Pitfall 6 / Runtime State Inventory): the
column is NOT NULL and EXISTING rows (the Phase-1 seeded admin) must get a valid role with no
separate data backfill — the default makes the seeded admin an Admin exactly as D-01 intends.

Reversibility is a phase gate (test_migration_0010 + the alembic up/down/up command):
downgrade() drops the column, back to 0009.

The LangGraph checkpoint tables remain owned by AsyncPostgresSaver.setup() (the 0005-0008 caveat
carries) and are NOT managed here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add users.role with server_default='admin' (chains after 0009).

    The server_default backfills every existing row — the seeded admin becomes 'admin' — so the
    NOT NULL column is valid without a separate data migration step.
    """
    op.add_column(
        'users',
        sa.Column('role', sa.String(length=16), server_default='admin', nullable=False),
    )


def downgrade() -> None:
    """Drop users.role, back to 0009 (reversible up/down/up phase gate)."""
    op.drop_column('users', 'role')
