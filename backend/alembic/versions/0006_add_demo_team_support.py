"""add demo team support

Revision ID: 0006_add_demo_team_support
Revises: 0005_sync_runtime_schema_to_models
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_add_demo_team_support"
down_revision = "0005_sync_runtime_schema_to_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    team_columns = {item["name"] for item in inspector.get_columns("teams")}
    if "is_demo" not in team_columns:
        op.add_column(
            "teams",
            sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    if "demo_team_hides" not in table_names:
        op.create_table(
            "demo_team_hides",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("team_id", "user_id", name="uq_demo_team_hide"),
        )
        op.create_index(op.f("ix_demo_team_hides_team_id"), "demo_team_hides", ["team_id"], unique=False)
        op.create_index(op.f("ix_demo_team_hides_user_id"), "demo_team_hides", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_demo_team_hides_user_id"), table_name="demo_team_hides")
    op.drop_index(op.f("ix_demo_team_hides_team_id"), table_name="demo_team_hides")
    op.drop_table("demo_team_hides")
    op.drop_column("teams", "is_demo")
