"""execution-history tables: test_runs / test_results / test_artifacts (EXEC-03/04/05)

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-21 10:00:00.000000

APP TABLES ONLY. The LangGraph checkpoint tables (checkpoints, checkpoint_writes,
checkpoint_blobs, checkpoint_migrations) are owned by AsyncPostgresSaver.setup() at app
startup and are deliberately NOT managed here (the 0005/0006 caveat carries).

W4 decision (a): test_artifacts.kind is screenshot|trace|video ONLY — console/network logs
live INSIDE the Playwright trace (--tracing=on), so there are no console_log/network_log kinds
and no binary columns (paths reference MinIO/workspaces files).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the three execution-history tables (chains after 0006)."""
    op.create_table(
        'test_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('tier', sa.String(length=16), nullable=False),
        sa.Column('selector', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=16), server_default='queued', nullable=False),
        sa.Column('total', sa.Integer(), server_default='0', nullable=False),
        sa.Column('passed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('failed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('flaky', sa.Integer(), server_default='0', nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_test_runs_run_id'), 'test_runs', ['run_id'], unique=True)

    op.create_table(
        'test_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('flow_id', sa.String(length=255), nullable=False),
        sa.Column('verdict', sa.String(length=16), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('exit_codes', sa.JSON(), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_test_results_run_id'), 'test_results', ['run_id'], unique=False)
    op.create_index(op.f('ix_test_results_flow_id'), 'test_results', ['flow_id'], unique=False)

    op.create_table(
        'test_artifacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('flow_id', sa.String(length=255), nullable=False),
        # screenshot | trace | video ONLY (W4 (a): console/network live inside the trace).
        sa.Column('kind', sa.String(length=16), nullable=False),
        # RUN-RELATIVE path (may contain subdir segments) to a MinIO/workspaces file — no blob.
        sa.Column('path', sa.String(length=1024), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_test_artifacts_run_id'), 'test_artifacts', ['run_id'], unique=False)
    op.create_index(op.f('ix_test_artifacts_flow_id'), 'test_artifacts', ['flow_id'], unique=False)


def downgrade() -> None:
    """Drop the three execution-history tables in reverse order."""
    op.drop_index(op.f('ix_test_artifacts_flow_id'), table_name='test_artifacts')
    op.drop_index(op.f('ix_test_artifacts_run_id'), table_name='test_artifacts')
    op.drop_table('test_artifacts')
    op.drop_index(op.f('ix_test_results_flow_id'), table_name='test_results')
    op.drop_index(op.f('ix_test_results_run_id'), table_name='test_results')
    op.drop_table('test_results')
    op.drop_index(op.f('ix_test_runs_run_id'), table_name='test_runs')
    op.drop_table('test_runs')
