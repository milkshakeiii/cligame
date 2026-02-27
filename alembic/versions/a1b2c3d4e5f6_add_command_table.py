"""add_command_table

Revision ID: a1b2c3d4e5f6
Revises: f8a3b1c2d4e5
Create Date: 2026-02-26 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f8a3b1c2d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('command',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ship_id', sa.Integer(), nullable=True),
        sa.Column('command_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('payload', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='{}'),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='pending'),
        sa.Column('rejection_reason', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('processed_at_tick', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['ship_id'], ['spaceship.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_command_user_id', 'command', ['user_id'])
    op.create_index('ix_command_status', 'command', ['status'])


def downgrade() -> None:
    op.drop_index('ix_command_status', table_name='command')
    op.drop_index('ix_command_user_id', table_name='command')
    op.drop_table('command')
