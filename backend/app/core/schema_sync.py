from sqlalchemy import inspect, text


def ensure_dev_schema(engine) -> None:
    inspector = inspect(engine)

    if "places" not in inspector.get_table_names():
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS places (
                        id UUID PRIMARY KEY,
                        team_id UUID NOT NULL REFERENCES teams(id),
                        name VARCHAR NOT NULL,
                        use_count INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_places_team_id ON places(team_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_places_name ON places(name)"))

    if "change_batches" not in inspector.get_table_names():
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS change_batches (
                        id UUID PRIMARY KEY,
                        team_id UUID NOT NULL REFERENCES teams(id),
                        user_id UUID NOT NULL REFERENCES users(id),
                        action VARCHAR NOT NULL,
                        entity_type VARCHAR NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_change_batches_team_id ON change_batches(team_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_change_batches_user_id ON change_batches(user_id)"))

    schedule_columns = {col["name"] for col in inspector.get_columns("schedules")} if "schedules" in inspector.get_table_names() else set()
    finance_columns = {col["name"] for col in inspector.get_columns("finance_records")} if "finance_records" in inspector.get_table_names() else set()

    with engine.begin() as conn:
        if "location" not in schedule_columns:
            conn.execute(text("ALTER TABLE schedules ADD COLUMN location VARCHAR"))
        if "location_latitude" not in schedule_columns:
            conn.execute(text("ALTER TABLE schedules ADD COLUMN location_latitude DOUBLE PRECISION"))
        if "location_longitude" not in schedule_columns:
            conn.execute(text("ALTER TABLE schedules ADD COLUMN location_longitude DOUBLE PRECISION"))
        if "is_all_day" not in schedule_columns:
            conn.execute(text("ALTER TABLE schedules ADD COLUMN is_all_day BOOLEAN NOT NULL DEFAULT false"))
        if "deleted_at" not in schedule_columns:
            conn.execute(text("ALTER TABLE schedules ADD COLUMN deleted_at TIMESTAMPTZ"))
        if "deleted_batch_id" not in schedule_columns:
            conn.execute(text("ALTER TABLE schedules ADD COLUMN deleted_batch_id UUID"))
        if "location" not in finance_columns:
            conn.execute(text("ALTER TABLE finance_records ADD COLUMN location VARCHAR"))
        if "location_latitude" not in finance_columns:
            conn.execute(text("ALTER TABLE finance_records ADD COLUMN location_latitude DOUBLE PRECISION"))
        if "location_longitude" not in finance_columns:
            conn.execute(text("ALTER TABLE finance_records ADD COLUMN location_longitude DOUBLE PRECISION"))
        if "deleted_at" not in finance_columns:
            conn.execute(text("ALTER TABLE finance_records ADD COLUMN deleted_at TIMESTAMPTZ"))
        if "deleted_batch_id" not in finance_columns:
            conn.execute(text("ALTER TABLE finance_records ADD COLUMN deleted_batch_id UUID"))
