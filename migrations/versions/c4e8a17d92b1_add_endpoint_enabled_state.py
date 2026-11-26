"""add endpoint enabled state

Revision ID: c4e8a17d92b1
Revises: 6c7e46e98ca0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4e8a17d92b1"
down_revision = "6c7e46e98ca0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("endpoints", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    with op.batch_alter_table("endpoints", schema=None) as batch_op:
        batch_op.drop_column("enabled")
