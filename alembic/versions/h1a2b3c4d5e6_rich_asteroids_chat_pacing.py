"""rich_asteroids_chat_pacing

Revision ID: h1a2b3c4d5e6
Revises: g1a2b3c4d5e6
Create Date: 2026-03-03 12:00:00.000000

Adds ore_richness to celestialobject, unified stream fields (category,
amount, reason, team_id, username) to event table, and indexes.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h1a2b3c4d5e6'
down_revision: Union[str, None] = 'g1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- CelestialObject: add ore_richness ---
    op.add_column('celestialobject', sa.Column('ore_richness', sa.Float(), nullable=False, server_default='1.0'))

    # --- Event: add unified stream fields ---
    op.add_column('event', sa.Column('category', sa.String(), nullable=False, server_default='action'))
    op.add_column('event', sa.Column('amount', sa.Float(), nullable=True))
    op.add_column('event', sa.Column('reason', sa.String(), nullable=True))
    op.add_column('event', sa.Column('team_id', sa.Integer(), nullable=True))
    op.add_column('event', sa.Column('username', sa.String(), nullable=True))

    # Indexes for efficient queries
    op.create_index('ix_event_category', 'event', ['category'])
    op.create_index('ix_event_team_id', 'event', ['team_id'])

    # Backfill existing points_earned events
    op.execute("UPDATE event SET category='points' WHERE event_type='points_earned'")


def downgrade() -> None:
    op.drop_index('ix_event_team_id', table_name='event')
    op.drop_index('ix_event_category', table_name='event')
    op.drop_column('event', 'username')
    op.drop_column('event', 'team_id')
    op.drop_column('event', 'reason')
    op.drop_column('event', 'amount')
    op.drop_column('event', 'category')
    op.drop_column('celestialobject', 'ore_richness')
