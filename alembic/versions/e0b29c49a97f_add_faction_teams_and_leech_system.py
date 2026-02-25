"""add_faction_teams_and_leech_system

Revision ID: e0b29c49a97f
Revises: d09b266a2f3a
Create Date: 2026-02-24 22:02:22.495281
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'e0b29c49a97f'
down_revision: Union[str, None] = 'd09b266a2f3a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Create new tables ---
    op.create_table('team',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('faction', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_team_name'), 'team', ['name'], unique=False)
    op.create_table('leechdebuff',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_ship_id', sa.Integer(), nullable=False),
    sa.Column('target_ship_id', sa.Integer(), nullable=False),
    sa.Column('leech_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('damage_per_tick', sa.Float(), nullable=False),
    sa.Column('damage_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('cap_drain_per_tick', sa.Float(), nullable=False),
    sa.Column('ticks_remaining', sa.Integer(), nullable=False),
    sa.Column('created_at_tick', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['source_ship_id'], ['spaceship.id'], ),
    sa.ForeignKeyConstraint(['target_ship_id'], ['spaceship.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_leechdebuff_source_ship_id'), 'leechdebuff', ['source_ship_id'], unique=False)
    op.create_index(op.f('ix_leechdebuff_target_ship_id'), 'leechdebuff', ['target_ship_id'], unique=False)

    # --- Add team_id to existing tables ---
    op.add_column('user', sa.Column('team_id', sa.Integer(), nullable=True))
    op.add_column('spaceship', sa.Column('team_id', sa.Integer(), nullable=True))
    op.add_column('researchprogress', sa.Column('team_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_researchprogress_team_id'), 'researchprogress', ['team_id'], unique=False)

    # --- Add Phase 7 fields to shipmodule ---
    op.add_column('shipmodule', sa.Column('lance_state', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='idle'))
    op.add_column('shipmodule', sa.Column('lance_charge_remaining', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('shipmodule', sa.Column('lance_cooldown_remaining', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('shipmodule', sa.Column('lance_target_ship_id', sa.Integer(), nullable=True))
    op.add_column('shipmodule', sa.Column('stealth_cooldown_remaining', sa.Integer(), nullable=False, server_default='0'))

    # Note: event_type enum expansion is handled at application level (SQLite stores
    # enums as VARCHAR, so no ALTER COLUMN needed for new enum values).


def downgrade() -> None:
    # --- Remove Phase 7 fields from shipmodule ---
    op.drop_column('shipmodule', 'stealth_cooldown_remaining')
    op.drop_column('shipmodule', 'lance_target_ship_id')
    op.drop_column('shipmodule', 'lance_cooldown_remaining')
    op.drop_column('shipmodule', 'lance_charge_remaining')
    op.drop_column('shipmodule', 'lance_state')

    # --- Remove team_id from existing tables ---
    op.drop_index(op.f('ix_researchprogress_team_id'), table_name='researchprogress')
    op.drop_column('researchprogress', 'team_id')
    op.drop_column('spaceship', 'team_id')
    op.drop_column('user', 'team_id')

    # --- Drop new tables ---
    op.drop_index(op.f('ix_leechdebuff_target_ship_id'), table_name='leechdebuff')
    op.drop_index(op.f('ix_leechdebuff_source_ship_id'), table_name='leechdebuff')
    op.drop_table('leechdebuff')
    op.drop_index(op.f('ix_team_name'), table_name='team')
    op.drop_table('team')
