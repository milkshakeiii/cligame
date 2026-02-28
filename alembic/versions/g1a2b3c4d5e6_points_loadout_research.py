"""points_loadout_and_research

Revision ID: g1a2b3c4d5e6
Revises: f8a3b1c2d4e5
Create Date: 2026-02-27 12:00:00.000000

Adds points system, ship claiming/loadout fields, research contributor table,
and drops autopilot columns.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'g1a2b3c4d5e6'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- User: add points ---
    op.add_column('user', sa.Column('points', sa.Float(), nullable=False, server_default='0'))

    # --- Spaceship: add loadout / claiming fields ---
    op.add_column('spaceship', sa.Column('claimed_by_user_id', sa.Integer(), nullable=True))
    op.add_column('spaceship', sa.Column('built_by_user_id', sa.Integer(), nullable=True))
    op.add_column('spaceship', sa.Column('loadout_points_spent', sa.Float(), nullable=False, server_default='0'))
    op.add_column('spaceship', sa.Column('last_damage_by_user_id', sa.Integer(), nullable=True))

    op.create_foreign_key(
        'fk_spaceship_claimed_by_user',
        'spaceship', 'user',
        ['claimed_by_user_id'], ['id'],
    )

    # --- Spaceship: drop autopilot columns ---
    op.drop_column('spaceship', 'autopilot_mode')
    op.drop_column('spaceship', 'autopilot_profile')
    op.drop_column('spaceship', 'autopilot_priority_target_id')

    # --- ResearchContributor table ---
    op.create_table(
        'researchcontributor',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('research_id', sa.Integer(), sa.ForeignKey('researchprogress.id'), nullable=False),
        sa.Column('ship_id', sa.Integer(), sa.ForeignKey('spaceship.id'), nullable=False),
        sa.Column('module_id', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
    )
    op.create_index('ix_researchcontributor_research_id', 'researchcontributor', ['research_id'])


def downgrade() -> None:
    # --- Drop ResearchContributor ---
    op.drop_index('ix_researchcontributor_research_id', table_name='researchcontributor')
    op.drop_table('researchcontributor')

    # --- Restore autopilot columns ---
    op.add_column('spaceship', sa.Column('autopilot_mode', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='off'))
    op.add_column('spaceship', sa.Column('autopilot_profile', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('spaceship', sa.Column('autopilot_priority_target_id', sa.Integer(), nullable=True))

    # --- Drop loadout / claiming fields ---
    op.drop_constraint('fk_spaceship_claimed_by_user', 'spaceship', type_='foreignkey')
    op.drop_column('spaceship', 'last_damage_by_user_id')
    op.drop_column('spaceship', 'loadout_points_spent')
    op.drop_column('spaceship', 'built_by_user_id')
    op.drop_column('spaceship', 'claimed_by_user_id')

    # --- Drop user points ---
    op.drop_column('user', 'points')
