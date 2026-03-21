"""add user language

Revision ID: 0002_add_user_language
Revises: 0001_init
Create Date: 2026-03-21
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_add_user_language"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("language", sa.String(), nullable=False, server_default="zh-CN"))


def downgrade() -> None:
    op.drop_column("users", "language")
