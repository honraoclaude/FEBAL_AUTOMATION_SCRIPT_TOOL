"""runs + executions

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-14 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='queued', nullable=False),
        sa.Column('error', sa.String(length=2048), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_runs_run_id'), 'runs', ['run_id'], unique=True)

    op.create_table(
        'executions',
        sa.Column('id', sa.Integer(), nullable=False),
        # FIX 1: indexed run_id is the execute-path poll key (the row finish_execution flips).
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('spec_path', sa.String(length=1024), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='queued', nullable=False),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('output', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_executions_run_id'), 'executions', ['run_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_executions_run_id'), table_name='executions')
    op.drop_table('executions')
    op.drop_index(op.f('ix_runs_run_id'), table_name='runs')
    op.drop_table('runs')
