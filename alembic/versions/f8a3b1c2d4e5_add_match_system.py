"""add_match_system

Revision ID: f8a3b1c2d4e5
Revises: e0b29c49a97f
Create Date: 2026-02-25 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f8a3b1c2d4e5'
down_revision: Union[str, None] = 'e0b29c49a97f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Create match table ---
    op.create_table('match',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('team1_id', sa.Integer(), nullable=True),
        sa.Column('team2_id', sa.Integer(), nullable=True),
        sa.Column('team1_mothership_id', sa.Integer(), nullable=True),
        sa.Column('team2_mothership_id', sa.Integer(), nullable=True),
        sa.Column('winner_team_id', sa.Integer(), nullable=True),
        sa.Column('started_at_tick', sa.Integer(), nullable=True),
        sa.Column('ended_at_tick', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('surrender_votes_team1', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''),
        sa.Column('surrender_votes_team2', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''),
        sa.ForeignKeyConstraint(['team1_id'], ['team.id']),
        sa.ForeignKeyConstraint(['team2_id'], ['team.id']),
        sa.ForeignKeyConstraint(['team1_mothership_id'], ['spaceship.id']),
        sa.ForeignKeyConstraint(['team2_mothership_id'], ['spaceship.id']),
        sa.ForeignKeyConstraint(['winner_team_id'], ['team.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # --- Add match_id FK to spaceship ---
    op.add_column('spaceship', sa.Column('match_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_spaceship_match_id', 'spaceship', 'match', ['match_id'], ['id'])
    op.create_index('ix_spaceship_match_id', 'spaceship', ['match_id'])

    # --- Add match_id FK to celestialobject ---
    op.add_column('celestialobject', sa.Column('match_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_celestialobject_match_id', 'celestialobject', 'match', ['match_id'], ['id'])
    op.create_index('ix_celestialobject_match_id', 'celestialobject', ['match_id'])

    # --- Add index on match.status ---
    op.create_index('ix_match_status', 'match', ['status'])


def downgrade() -> None:
    op.drop_index('ix_match_status', table_name='match')
    op.drop_index('ix_celestialobject_match_id', table_name='celestialobject')
    op.drop_constraint('fk_celestialobject_match_id', 'celestialobject', type_='foreignkey')
    op.drop_column('celestialobject', 'match_id')
    op.drop_index('ix_spaceship_match_id', table_name='spaceship')
    op.drop_constraint('fk_spaceship_match_id', 'spaceship', type_='foreignkey')
    op.drop_column('spaceship', 'match_id')
    op.drop_table('match')
