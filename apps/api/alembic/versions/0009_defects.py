"""defects schema: classifications + defects tables + test_results.error_text (DEF-01/02, JIRA-04)

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-27 18:00:00.000000

The defect-intelligence foundation (Phase 9, plan 09-01):

  - `test_results.error_text` (Pitfall 1 / Open-Q1): the Phase-7 persistence gap closed. The
    worker (job.py) computed the tail-capped subprocess `output` then DISCARDED it; the pure
    classifier needs the error TEXT to classify by error type. A nullable Text column on
    test_results is the cleaner join the classifier reads directly (the aborted path leaves it NULL).

  - `classifications`: one row per classified failure — the 3-way class (infrastructure |
    automation | product_defect, String(16) vocab), the 0-100 confidence (Integer), and the full
    cited-evidence snapshot as JSON (none_as_null) the review UI renders. run_id/flow_id indexed
    for the per-run / per-flow joins.

  - `defects`: the draft-review row. status (draft | applied | rejected, server_default 'draft'),
    the stable fingerprint (String(64) index — the `fp-<hash>` dedup label), the nullable jira_key
    (String(32) — populated on apply), the jira_label, and run_id/flow_id (the test<->flow<->
    execution traceability link per JIRA-04, captured here for the Plan-04 pipeline).

Reversibility is a phase gate (test_migration_0009 + the alembic up/down/up command): downgrade()
reverses every op (indexes -> defects -> classifications -> the error_text column), back to 0008.

The LangGraph checkpoint tables remain owned by AsyncPostgresSaver.setup() (the 0005-0008 caveat
carries) and are NOT managed here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add error_text + create classifications + defects (chains after 0008)."""
    # Pitfall 1: persist the last-attempt error text the classifier reads (nullable — aborted/no-text).
    op.add_column('test_results', sa.Column('error_text', sa.Text(), nullable=True))

    op.create_table(
        'classifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('flow_id', sa.String(length=255), nullable=False),
        # infrastructure | automation | product_defect — the deterministic 3-way class (DEF-01).
        sa.Column('classification', sa.String(length=16), nullable=False),
        # 0-100 confidence (Integer, clamped by the pure classifier).
        sa.Column('confidence', sa.Integer(), nullable=False),
        # The full cited-evidence snapshot (error_text/heal-history/infra-health/etc.) as JSON.
        sa.Column('evidence', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_classifications_run_id'), 'classifications', ['run_id'], unique=False)
    op.create_index(op.f('ix_classifications_flow_id'), 'classifications', ['flow_id'], unique=False)

    op.create_table(
        'defects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.String(length=64), nullable=False),
        sa.Column('flow_id', sa.String(length=255), nullable=False),
        sa.Column('classification', sa.String(length=16), nullable=False),
        sa.Column('confidence', sa.Integer(), nullable=False),
        # The stable failure fingerprint (the `fp-<hash>` dedup key, D-05); indexed.
        sa.Column('fingerprint', sa.String(length=64), nullable=False),
        # The Jira LABEL applied on filing (`fp-<hash>`).
        sa.Column('jira_label', sa.String(length=64), nullable=False),
        # The created/updated Jira issue key — NULL until the human (or autonomous gate) files it.
        sa.Column('jira_key', sa.String(length=32), nullable=True),
        # draft | applied | rejected — OFF-by-default autonomy keeps every row in draft (D-04).
        sa.Column('status', sa.String(length=16), server_default='draft', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_defects_run_id'), 'defects', ['run_id'], unique=False)
    op.create_index(op.f('ix_defects_flow_id'), 'defects', ['flow_id'], unique=False)
    op.create_index(op.f('ix_defects_fingerprint'), 'defects', ['fingerprint'], unique=False)


def downgrade() -> None:
    """Reverse every op in order (indexes -> defects -> classifications -> error_text) back to 0008."""
    op.drop_index(op.f('ix_defects_fingerprint'), table_name='defects')
    op.drop_index(op.f('ix_defects_flow_id'), table_name='defects')
    op.drop_index(op.f('ix_defects_run_id'), table_name='defects')
    op.drop_table('defects')
    op.drop_index(op.f('ix_classifications_flow_id'), table_name='classifications')
    op.drop_index(op.f('ix_classifications_run_id'), table_name='classifications')
    op.drop_table('classifications')
    op.drop_column('test_results', 'error_text')
