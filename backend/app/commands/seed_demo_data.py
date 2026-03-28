from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services.demo_seed_service import ensure_demo_data


def main() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        stats = ensure_demo_data(db, force=True)
    finally:
        db.close()

    print(
        "Demo seed completed:",
        f"environment={settings.ENVIRONMENT}",
        f"created_teams={stats.created_teams}",
        f"updated_teams={stats.updated_teams}",
        f"created_memberships={stats.created_memberships}",
        f"created_schedules={stats.created_schedules}",
        f"created_finance_records={stats.created_finance_records}",
    )


if __name__ == "__main__":
    main()
