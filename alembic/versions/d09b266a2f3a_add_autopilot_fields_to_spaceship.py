"""add autopilot fields to spaceship

Revision ID: d09b266a2f3a
Revises: 
Create Date: 2026-02-22 18:20:29.331302
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd09b266a2f3a'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('spaceship', sa.Column('autopilot_mode', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='off'))
    op.add_column('spaceship', sa.Column('autopilot_profile', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('spaceship', sa.Column('autopilot_priority_target_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('spaceship', 'autopilot_priority_target_id')
    op.drop_column('spaceship', 'autopilot_profile')
    op.drop_column('spaceship', 'autopilot_mode')
