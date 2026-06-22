"""heal_audit table: the auditable per-heal ledger (HEAL-03)

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-22 22:45:00.000000

One row per ingested heal-journal entry (Plan 03 worker ingest): the element key, the
before/after locator chains (JSON — after is nullable for a fail_as_defect), the blended
confidence, the locator-resolution outcome, the live match count, and the run/flow
traceability keys. Chains are JSON, NEVER binary blobs (the execution-history rule carries —
T-08-13). Chains after 0007 (the execution-history tables).

The LangGraph checkpoint tables remain owned by AsyncPostgresSaver.setup() and are NOT
managed here (the 0005/0006/0007 caveat carries).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the heal_audit table (chains after 0007)."""
    op.create_table(
        'heal_audit',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('element_key', sa.String(length=255), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('flow_id', sa.String(length=255), nullable=False),
        # before/after locator chains as JSON lists of {strategy, value} — never blobs.
        sa.Column('before_chain', sa.JSON(), nullable=False),
        # after_chain is nullable: a fail_as_defect produced no healed chain.
        sa.Column('after_chain', sa.JSON(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        # auto_heal | quarantine | fail_as_defect | applied | rejected.
        sa.Column('outcome', sa.String(length=16), nullable=False),
        sa.Column('live_match_count', sa.Integer(), nullable=False),
        # Set by the Plan-05 reject/apply API for false-heal tracking (HEAL-04); NULL on ingest.
        sa.Column('reviewed_outcome', sa.String(length=16), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_heal_audit_element_key'), 'heal_audit', ['element_key'], unique=False)
    op.create_index(op.f('ix_heal_audit_run_id'), 'heal_audit', ['run_id'], unique=False)
    op.create_index(op.f('ix_heal_audit_flow_id'), 'heal_audit', ['flow_id'], unique=False)


def downgrade() -> None:
    """Drop the heal_audit table + indexes in reverse order (back to 0007)."""
    op.drop_index(op.f('ix_heal_audit_flow_id'), table_name='heal_audit')
    op.drop_index(op.f('ix_heal_audit_run_id'), table_name='heal_audit')
    op.drop_index(op.f('ix_heal_audit_element_key'), table_name='heal_audit')
    op.drop_table('heal_audit')
