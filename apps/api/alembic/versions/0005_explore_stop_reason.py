"""explore stop_reason on runs

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-15 12:00:00.000000

APP TABLES ONLY. The LangGraph checkpoint tables (checkpoints, checkpoint_writes,
checkpoint_blobs, checkpoint_migrations) are owned by AsyncPostgresSaver.setup() at app
startup and are deliberately NOT managed here (Pitfall 6).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a nullable stop_reason column to runs (EXPL-05)."""
    op.add_column('runs', sa.Column('stop_reason', sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('runs', 'stop_reason')
