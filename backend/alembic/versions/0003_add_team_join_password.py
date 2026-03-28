"""add team join password

Revision ID: 0003_add_team_join_password
Revises: 0002_add_user_language
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_add_team_join_password"
down_revision = "0002_add_user_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("join_password", sa.String(length=4), nullable=True))


def downgrade() -> None:
    op.drop_column("teams", "join_password")
