"""add disease_outbreak_reports table

Revision ID: a7d3e9c1b5f2
Revises: e2b6c9d4f8a3
Create Date: 2026-10-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a7d3e9c1b5f2'
down_revision: Union[str, Sequence[str], None] = 'e2b6c9d4f8a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'disease_outbreak_reports',
        sa.Column('don_id', sa.String(length=80), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('disease', sa.Text(), nullable=False),
        sa.Column('disease_key', sa.Text(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('countries', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('ended', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('ends_unplaced', sa.Boolean(), nullable=False),
        sa.Column('published', sa.DateTime(timezone=True), nullable=False),
        sa.Column('modified', sa.DateTime(timezone=True), nullable=True),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('url_name', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('don_id'),
    )
    op.create_index('idx_disease_outbreak_reports_published', 'disease_outbreak_reports', ['published'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_disease_outbreak_reports_published', table_name='disease_outbreak_reports')
    op.drop_table('disease_outbreak_reports')
