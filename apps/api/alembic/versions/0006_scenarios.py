"""scenarios review-queue table (GEN-02 / D-01)

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-20 15:00:00.000000

APP TABLES ONLY. The LangGraph checkpoint tables (checkpoints, checkpoint_writes,
checkpoint_blobs, checkpoint_migrations) are owned by AsyncPostgresSaver.setup() at app
startup and are deliberately NOT managed here (the 0005 caveat carries).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the scenarios review-queue table (chains after 0005)."""
    op.create_table(
        'scenarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('flow_id', sa.String(length=255), nullable=False),
        sa.Column('feature_name', sa.String(length=255), nullable=False),
        sa.Column('gherkin_text', sa.Text(), nullable=False),
        # The sidecar Then→kg_ref mapping the no-vacuous gate consumes (Mechanism 1).
        sa.Column('then_refs', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='draft', nullable=False),
        sa.Column('edited', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('stale', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_scenarios_run_id'), 'scenarios', ['run_id'], unique=False)
    op.create_index(op.f('ix_scenarios_flow_id'), 'scenarios', ['flow_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_scenarios_flow_id'), table_name='scenarios')
    op.drop_index(op.f('ix_scenarios_run_id'), table_name='scenarios')
    op.drop_table('scenarios')
