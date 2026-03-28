"""sync runtime schema to models

Revision ID: 0005_sync_runtime_schema_to_models
Revises: 0004_add_assistant_runtime_state
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_sync_runtime_schema_to_models"
down_revision = "0004_add_assistant_runtime_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    def index_names(table_name: str) -> set[str]:
        return {item["name"] for item in inspector.get_indexes(table_name)}

    def column_names(table_name: str) -> set[str]:
        return {item["name"] for item in inspector.get_columns(table_name)}

    if "places" not in table_names:
        op.create_table(
            "places",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("use_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("team_id", "name", name="uq_place_team_name"),
        )
        op.create_index(op.f("ix_places_name"), "places", ["name"], unique=False)
        op.create_index(op.f("ix_places_team_id"), "places", ["team_id"], unique=False)
    else:
        existing_indexes = index_names("places")
        if op.f("ix_places_name") not in existing_indexes:
            op.create_index(op.f("ix_places_name"), "places", ["name"], unique=False)
        if op.f("ix_places_team_id") not in existing_indexes:
            op.create_index(op.f("ix_places_team_id"), "places", ["team_id"], unique=False)

    if "change_batches" not in table_names:
        op.create_table(
            "change_batches",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("entity_type", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_change_batches_team_id"), "change_batches", ["team_id"], unique=False)
        op.create_index(op.f("ix_change_batches_user_id"), "change_batches", ["user_id"], unique=False)
    else:
        existing_indexes = index_names("change_batches")
        if op.f("ix_change_batches_team_id") not in existing_indexes:
            op.create_index(op.f("ix_change_batches_team_id"), "change_batches", ["team_id"], unique=False)
        if op.f("ix_change_batches_user_id") not in existing_indexes:
            op.create_index(op.f("ix_change_batches_user_id"), "change_batches", ["user_id"], unique=False)

    schedule_columns = column_names("schedules") if "schedules" in table_names else set()
    if "location" not in schedule_columns:
        op.add_column("schedules", sa.Column("location", sa.String(), nullable=True))
    if "location_latitude" not in schedule_columns:
        op.add_column("schedules", sa.Column("location_latitude", sa.Float(), nullable=True))
    if "location_longitude" not in schedule_columns:
        op.add_column("schedules", sa.Column("location_longitude", sa.Float(), nullable=True))
    if "is_all_day" not in schedule_columns:
        op.add_column("schedules", sa.Column("is_all_day", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    if "deleted_at" not in schedule_columns:
        op.add_column("schedules", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    if "deleted_batch_id" not in schedule_columns:
        op.add_column("schedules", sa.Column("deleted_batch_id", postgresql.UUID(as_uuid=True), nullable=True))

    finance_columns = column_names("finance_records") if "finance_records" in table_names else set()
    if "location" not in finance_columns:
        op.add_column("finance_records", sa.Column("location", sa.String(), nullable=True))
    if "location_latitude" not in finance_columns:
        op.add_column("finance_records", sa.Column("location_latitude", sa.Float(), nullable=True))
    if "location_longitude" not in finance_columns:
        op.add_column("finance_records", sa.Column("location_longitude", sa.Float(), nullable=True))
    if "occurred_at" not in finance_columns:
        op.add_column(
            "finance_records",
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )
    if "deleted_at" not in finance_columns:
        op.add_column("finance_records", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    if "deleted_batch_id" not in finance_columns:
        op.add_column("finance_records", sa.Column("deleted_batch_id", postgresql.UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("finance_records", "deleted_batch_id")
    op.drop_column("finance_records", "deleted_at")
    op.drop_column("finance_records", "occurred_at")
    op.drop_column("finance_records", "location_longitude")
    op.drop_column("finance_records", "location_latitude")
    op.drop_column("finance_records", "location")

    op.drop_column("schedules", "deleted_batch_id")
    op.drop_column("schedules", "deleted_at")
    op.drop_column("schedules", "is_all_day")
    op.drop_column("schedules", "location_longitude")
    op.drop_column("schedules", "location_latitude")
    op.drop_column("schedules", "location")

    op.drop_index(op.f("ix_change_batches_user_id"), table_name="change_batches")
    op.drop_index(op.f("ix_change_batches_team_id"), table_name="change_batches")
    op.drop_table("change_batches")

    op.drop_index(op.f("ix_places_team_id"), table_name="places")
    op.drop_index(op.f("ix_places_name"), table_name="places")
    op.drop_table("places")
