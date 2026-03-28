"""add assistant runtime state

Revision ID: 0004_add_assistant_runtime_state
Revises: 0003_add_team_join_password
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_add_assistant_runtime_state"
down_revision = "0003_add_team_join_password"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "assistant_undo_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_assistant_undo_batches_team_user"),
    )
    op.create_index(op.f("ix_assistant_undo_batches_team_id"), "assistant_undo_batches", ["team_id"], unique=False)
    op.create_index(op.f("ix_assistant_undo_batches_user_id"), "assistant_undo_batches", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_assistant_undo_batches_user_id"), table_name="assistant_undo_batches")
    op.drop_index(op.f("ix_assistant_undo_batches_team_id"), table_name="assistant_undo_batches")
    op.drop_table("assistant_undo_batches")
    op.drop_table("assistant_sessions")
